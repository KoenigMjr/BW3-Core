#!/usr/bin/python
# -*- coding: utf-8 -*-
r"""!
    ____  ____  ______       __      __       __       _____
   / __ )/ __ \/ ___/ |     / /___ _/ /______/ /_     |__  /
  / __  / / / /\__ \| | /| / / __ `/ __/ ___/ __ \     /_ <
 / /_/ / /_/ /___/ /| |/ |/ / /_/ / /_/ /__/ / / /   ___/ /
/_____/\____//____/ |__/|__/\__,_/\__/\___/_/ /_/   /____/
                German BOS Information Script
                     by Bastian Schroll

@file:        test_mysql.py
@date:        12.10.2026
@author:      Claus Schichl
@description: Unittests for BOSWatch. File have to run as "pytest" unittest
"""
# problem of the pytest fixtures
# pylint: disable=redefined-outer-name
import logging
import pytest
import mysql.connector
from boswatch.utils import paths

from boswatch.configYaml import ConfigYAML
from boswatch.packet import Packet
from plugin.mysql import BoswatchPlugin as Mysql


def setup_function(function):
    logging.debug("[TEST] %s.%s", function.__module__, function.__name__)


class FakeDatabase:
    r"""!State of the fake database - the test can switch errors on and read what happened"""

    def __init__(self):
        self.tableExists = True
        self.connectFails = False
        self.pingFails = False
        self.closeFails = False
        self.connectCalls = []
        self.executed = []
        self.commits = 0
        self.closedCursors = 0
        self.closedConnections = 0


class FakeCursor:
    r"""!Cursor of the fake database"""

    def __init__(self, database):
        self._database = database
        self._lastSql = ""

    def execute(self, sql, values=None):
        self._lastSql = sql
        self._database.executed.append((sql, values))

    def fetchone(self):
        if "SHOW TABLES" in self._lastSql and self._database.tableExists:
            return ("boswatch",)
        return None

    def close(self):
        self._database.closedCursors += 1


class FakeConnection:
    r"""!Connection of the fake database"""

    def __init__(self, database):
        self._database = database

    def cursor(self):
        return FakeCursor(self._database)

    def ping(self, reconnect=False, attempts=1, delay=0):
        if self._database.pingFails:
            raise mysql.connector.Error("ping failed")

    def commit(self):
        self._database.commits += 1

    def close(self):
        if self._database.closeFails:
            raise mysql.connector.Error("connection already lost")
        self._database.closedConnections += 1


@pytest.fixture
def fakeDatabase(monkeypatch):
    r"""!Replace mysql.connector.connect - no database needed in the tests
    @return state of the fake database"""
    database = FakeDatabase()

    def fakeConnect(**kwargs):
        database.connectCalls.append(kwargs)
        if database.connectFails:
            raise mysql.connector.Error("database not reachable")
        return FakeConnection(database)

    monkeypatch.setattr(mysql.connector, "connect", fakeConnect)
    return database


@pytest.fixture
def getConfig():
    r"""!Build a config object and fill it with the config data"""
    config = ConfigYAML()
    assert config.loadConfigFile(paths.TEST_PATH + "test_config.yaml") is True
    return config


@pytest.fixture
def makeMysql(getConfig, fakeDatabase):
    r"""!Build a mysql plugin with the test config and remove it after the test"""
    mysqlPlugin = Mysql(getConfig.get("mysql_test"))
    yield mysqlPlugin
    if mysqlPlugin in Mysql._pluginsActive:
        mysqlPlugin._cleanup()


def buildPacket(mode, fields=None):
    r"""!Build a BW Packet object with the given mode and fields"""
    packet = Packet()
    packet.set("timestamp", 1700000000.0)
    packet.set("mode", mode)
    for fieldName, value in (fields or {}).items():
        packet.set(fieldName, value)
    return packet


def getInserts(database):
    r"""!Return all executed INSERT statements as (sql, values)"""
    return [(sql, values) for sql, values in database.executed if sql.startswith("INSERT")]


def test_mysqlConnect(makeMysql, fakeDatabase):
    r"""!Connect to the database with the values of the config"""
    assert fakeDatabase.connectCalls == [{"host": "testHost", "user": "testUser",
                                          "password": "testPassword", "database": "testDatabase"}]


def test_mysqlTableExists(makeMysql, fakeDatabase):
    r"""!An existing table is not created again"""
    assert [sql for sql, values in fakeDatabase.executed] == ["SHOW TABLES LIKE 'boswatch'"]


def test_mysqlCreateTable(getConfig, fakeDatabase):
    r"""!A missing table is created with init_db.sql"""
    fakeDatabase.tableExists = False
    mysqlPlugin = Mysql(getConfig.get("mysql_test"))
    mysqlPlugin._cleanup()
    assert any(sql.lower().startswith("create table boswatch") for sql, values in fakeDatabase.executed)
    assert fakeDatabase.commits >= 1


def test_mysqlCreateTableOtherWorkingDirectory(getConfig, fakeDatabase, tmp_path, monkeypatch):
    r"""!The table is also created if BOSWatch is started from another directory"""
    fakeDatabase.tableExists = False
    monkeypatch.chdir(tmp_path)
    mysqlPlugin = Mysql(getConfig.get("mysql_test"))
    mysqlPlugin._cleanup()
    assert any(sql.lower().startswith("create table boswatch") for sql, values in fakeDatabase.executed)


def test_mysqlFms(makeMysql, fakeDatabase):
    r"""!Insert a FMS packet"""
    makeMysql._run(buildPacket("fms", {"fms": "93377141", "status": "3"}))
    sql, values = getInserts(fakeDatabase)[0]
    assert "fms_fms" in sql
    assert values[1:3] == ("fms", "93377141")
    assert values[7] == "3"


def test_mysqlPocsag(makeMysql, fakeDatabase):
    r"""!Insert a POCSAG packet"""
    makeMysql._run(buildPacket("pocsag", {"ric": "1234567", "subric": "1", "message": "Brand"}))
    sql, values = getInserts(fakeDatabase)[0]
    assert "pocsag_ric" in sql
    assert values[1:4] == ("pocsag", "1234567", "1")
    assert values[5] == "Brand"


def test_mysqlZvei(makeMysql, fakeDatabase):
    r"""!Insert a ZVEI packet"""
    makeMysql._run(buildPacket("zvei", {"tone": "12345"}))
    sql, values = getInserts(fakeDatabase)[0]
    assert "zvei_tone" in sql
    assert values[1:3] == ("zvei", "12345")


def test_mysqlMsg(makeMysql, fakeDatabase):
    r"""!Insert a MSG packet"""
    makeMysql._run(buildPacket("msg"))
    sql, values = getInserts(fakeDatabase)[0]
    assert values[1] == "msg"


def test_mysqlValuesMatchColumns(makeMysql, fakeDatabase):
    r"""!Every insert has as many values as placeholders"""
    for mode in ["fms", "pocsag", "zvei", "msg"]:
        makeMysql._run(buildPacket(mode))
    for sql, values in getInserts(fakeDatabase):
        assert sql.count("%s") == len(values)


def test_mysqlTimestamp(makeMysql, fakeDatabase):
    r"""!The packet timestamp is saved as datetime"""
    makeMysql._run(buildPacket("zvei", {"tone": "12345"}))
    assert getInserts(fakeDatabase)[0][1][0].timestamp() == 1700000000.0


def test_mysqlCommitAfterAlarm(makeMysql, fakeDatabase):
    r"""!The insert is committed and the cursor is closed after the alarm"""
    makeMysql._run(buildPacket("zvei", {"tone": "12345"}))
    assert fakeDatabase.commits == 1
    assert fakeDatabase.closedCursors == 2  # cursor of the table check and of the alarm
    assert makeMysql.cursor is None


def test_mysqlUnavailableOnLoad(getConfig, fakeDatabase):
    r"""!A not reachable database while loading the plugin is no error - the alarms are skipped"""
    fakeDatabase.connectFails = True
    mysqlPlugin = Mysql(getConfig.get("mysql_test"))
    mysqlPlugin._run(buildPacket("zvei", {"tone": "12345"}))
    mysqlPlugin._cleanup()
    stats = mysqlPlugin._getStatistics()
    assert getInserts(fakeDatabase) == []
    assert stats["setupErrorCount"] == 0
    assert stats["alarmErrorCount"] == 0
    assert stats["teardownErrorCount"] == 0


def test_mysqlReconnect(getConfig, fakeDatabase):
    r"""!The plugin connects to the database again if it is reachable later"""
    fakeDatabase.connectFails = True
    mysqlPlugin = Mysql(getConfig.get("mysql_test"))
    fakeDatabase.connectFails = False
    mysqlPlugin._run(buildPacket("zvei", {"tone": "12345"}))
    mysqlPlugin._cleanup()
    assert len(getInserts(fakeDatabase)) == 1


def test_mysqlPingFailed(makeMysql, fakeDatabase):
    r"""!If the connection is lost the plugin connects again before the alarm"""
    fakeDatabase.pingFails = True
    makeMysql._run(buildPacket("zvei", {"tone": "12345"}))
    assert len(fakeDatabase.connectCalls) == 2
    assert len(getInserts(fakeDatabase)) == 1


def test_mysqlUnloadClosesConnection(makeMysql, fakeDatabase):
    r"""!The connection is closed while unloading the plugin"""
    makeMysql._cleanup()
    assert fakeDatabase.closedConnections == 1


def test_mysqlUnloadLostConnection(makeMysql, fakeDatabase):
    r"""!An error while closing a lost connection does not stop the unloading"""
    fakeDatabase.closeFails = True
    makeMysql._cleanup()
    assert makeMysql not in Mysql._pluginsActive
