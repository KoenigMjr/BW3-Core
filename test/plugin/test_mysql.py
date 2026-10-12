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
@date:        14.10.2026
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
from plugin.mysql import FIXED_COLUMNS


def setup_function(function):
    logging.debug("[TEST] %s.%s", function.__module__, function.__name__)


class FakeDatabase:
    r"""!State of the fake database - the test can switch errors on and read what happened"""

    def __init__(self):
        self.tableExists = True
        self.connectFails = False
        self.pingFails = False
        self.closeFails = False
        self.alterFails = False
        self.columns = list(FIXED_COLUMNS)
        self.warnings = []
        self.nextRowId = 1
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
        self.lastrowid = None

    def execute(self, sql, values=None):
        self._lastSql = sql
        self._database.executed.append((sql, values))
        if sql.startswith("INSERT"):
            self.lastrowid = self._database.nextRowId
            self._database.nextRowId += 1
        if sql.startswith("ALTER"):
            if self._database.alterFails:
                raise mysql.connector.Error("ALTER command denied")
            self._database.columns.append(sql.split("`")[1])

    def fetchone(self):
        if "SHOW TABLES" in self._lastSql and self._database.tableExists:
            return ("boswatch",)
        return None

    def fetchall(self):
        if "SHOW COLUMNS" in self._lastSql:
            return [(column,) for column in self._database.columns]
        return []

    def fetchwarnings(self):
        warnings = self._database.warnings
        self._database.warnings = []
        return warnings

    def close(self):
        self._database.closedCursors += 1


class FakeConnection:
    r"""!Connection of the fake database"""

    def __init__(self, database):
        self._database = database
        self.get_warnings = False

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


@pytest.fixture
def makeMysqlAll(getConfig, fakeDatabase):
    r"""!Build a mysql plugin which saves all additional fields and remove it after the test"""
    mysqlPlugin = Mysql(getConfig.get("mysql_allFields"))
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


def getStatements(database, start):
    r"""!Return all executed statements which start with the given text as (sql, values)"""
    return [(sql, values) for sql, values in database.executed if sql.startswith(start)]


def getInserts(database):
    r"""!Return all executed INSERT statements as (sql, values)"""
    return [(sql, values) for sql, values in database.executed if sql.startswith("INSERT")]


def test_mysqlConnect(makeMysql, fakeDatabase):
    r"""!Connect to the database with the values of the config"""
    assert fakeDatabase.connectCalls == [{"host": "testHost", "user": "testUser",
                                          "password": "testPassword", "database": "testDatabase"}]


def test_mysqlTableExists(makeMysql, fakeDatabase):
    r"""!An existing table is not created again"""
    assert fakeDatabase.executed[0][0] == "SHOW TABLES LIKE 'boswatch'"
    assert not any(sql.lower().startswith("create table") for sql, values in fakeDatabase.executed)


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


def test_additionalFieldsDefault(makeMysql, fakeDatabase):
    r"""!Without configured fields only the fields with a fixed column are saved"""
    makeMysql._run(buildPacket("pocsag", {"ric": "1234567", "description": "FF Musterdorf", "address": "Marienplatz 1"}))
    assert len(getInserts(fakeDatabase)) == 1
    assert getStatements(fakeDatabase, "ALTER") == []
    assert getStatements(fakeDatabase, "UPDATE") == []
    assert fakeDatabase.commits == 1


def test_additionalFieldsAll(makeMysqlAll, fakeDatabase):
    r"""!With allFields all additional fields are saved in new columns"""
    makeMysqlAll._run(buildPacket("pocsag", {"ric": "1234567", "description": "FF Musterdorf", "address": "Marienplatz 1"}))
    assert sorted(sql.split("`")[1] for sql, values in getStatements(fakeDatabase, "ALTER")) == ["address", "description"]
    sql, values = getStatements(fakeDatabase, "UPDATE")[0]
    assert sorted(zip(sql.split("`")[1::2], values)) == [("address", "Marienplatz 1"), ("description", "FF Musterdorf")]
    assert values[-1] == 1  # id of the inserted row
    assert fakeDatabase.commits == 1


def test_additionalFieldsConfigured(getConfig, fakeDatabase):
    r"""!With configured fields only these fields are saved - fields of fixed columns are ignored"""
    mysqlPlugin = Mysql(getConfig.get("mysql_additionalFields"))
    mysqlPlugin._run(buildPacket("pocsag", {"ric": "1234567", "description": "FF Musterdorf", "address": "Marienplatz 1"}))
    mysqlPlugin._cleanup()
    assert [sql.split("`")[1] for sql, values in getStatements(fakeDatabase, "ALTER")] == ["description"]
    assert getStatements(fakeDatabase, "UPDATE")[0][1] == ("FF Musterdorf", 1)


def test_additionalFieldsConfiguredOnLoad(getConfig, fakeDatabase):
    r"""!The columns of configured fields are added while loading the plugin - before the first alarm"""
    mysqlPlugin = Mysql(getConfig.get("mysql_additionalFields"))
    assert [sql.split("`")[1] for sql, values in getStatements(fakeDatabase, "ALTER")] == ["description"]
    mysqlPlugin._run(buildPacket("pocsag", {"ric": "1234567", "description": "FF Musterdorf"}))
    mysqlPlugin._cleanup()
    assert len(getStatements(fakeDatabase, "ALTER")) == 1
    assert getStatements(fakeDatabase, "UPDATE")[0][1] == ("FF Musterdorf", 1)


def test_additionalFieldsAllOnLoad(makeMysqlAll, fakeDatabase):
    r"""!With allFields no column is added while loading the plugin - the fields are not known yet"""
    assert getStatements(fakeDatabase, "ALTER") == []


def test_additionalFieldsList(getConfig, fakeDatabase):
    r"""!The fields can also be configured as yaml list"""
    mysqlPlugin = Mysql(getConfig.get("mysql_additionalFieldsList"))
    mysqlPlugin._run(buildPacket("pocsag", {"ric": "1234567", "description": "FF Musterdorf", "address": "Marienplatz 1"}))
    mysqlPlugin._cleanup()
    assert [sql.split("`")[1] for sql, values in getStatements(fakeDatabase, "ALTER")] == ["description"]
    assert getStatements(fakeDatabase, "UPDATE")[0][1] == ("FF Musterdorf", 1)


def test_additionalFieldsAllAndConfigured(getConfig, fakeDatabase, caplog):
    r"""!With allFields the configured fields are ignored - all additional fields are saved"""
    caplog.set_level(logging.WARNING)
    mysqlPlugin = Mysql(getConfig.get("mysql_allAndAdditionalFields"))
    assert any("additionalFields is ignored" in record.getMessage() for record in caplog.records)
    assert getStatements(fakeDatabase, "ALTER") == []  # no columns while loading like allFields
    mysqlPlugin._run(buildPacket("pocsag", {"ric": "1234567", "description": "FF Musterdorf", "address": "Marienplatz 1"}))
    mysqlPlugin._cleanup()
    assert sorted(sql.split("`")[1] for sql, values in getStatements(fakeDatabase, "ALTER")) == ["address", "description"]


def test_additionalFieldsConfiguredAlterDenied(getConfig, fakeDatabase, caplog):
    r"""!A missing right to add columns is logged already while loading the plugin"""
    caplog.set_level(logging.WARNING)
    fakeDatabase.alterFails = True
    mysqlPlugin = Mysql(getConfig.get("mysql_additionalFields"))
    assert any("description" in record.getMessage() and "could not be added" in record.getMessage()
               for record in caplog.records)
    mysqlPlugin._cleanup()


def test_additionalFieldsExistingColumn(getConfig, fakeDatabase):
    r"""!An existing column is used - also with other upper and lower case"""
    fakeDatabase.columns.append("Description")
    mysqlPlugin = Mysql(getConfig.get("mysql_allFields"))
    mysqlPlugin._run(buildPacket("zvei", {"tone": "12345", "description": "FF Musterdorf"}))
    mysqlPlugin._cleanup()
    assert getStatements(fakeDatabase, "ALTER") == []
    assert getStatements(fakeDatabase, "UPDATE")[0][1] == ("FF Musterdorf", 1)


def test_additionalFieldsColumnAddedOnce(makeMysqlAll, fakeDatabase):
    r"""!A new column is added only once"""
    makeMysqlAll._run(buildPacket("zvei", {"tone": "12345", "description": "first"}))
    makeMysqlAll._run(buildPacket("zvei", {"tone": "12345", "description": "second"}))
    assert len(getStatements(fakeDatabase, "ALTER")) == 1
    assert [values for sql, values in getStatements(fakeDatabase, "UPDATE")] == [("first", 1), ("second", 2)]


def test_additionalFieldsNone(makeMysqlAll, fakeDatabase):
    r"""!A packet without additional fields needs no update"""
    makeMysqlAll._run(buildPacket("zvei", {"tone": "12345"}))
    assert getStatements(fakeDatabase, "ALTER") == []
    assert getStatements(fakeDatabase, "UPDATE") == []


def test_additionalFieldsInvalidName(makeMysqlAll, fakeDatabase):
    r"""!A field with characters which are not allowed in column names is not saved"""
    makeMysqlAll._run(buildPacket("zvei", {"tone": "12345", "bad name`; DROP TABLE boswatch": "x", "description": "ok"}))
    assert [sql.split("`")[1] for sql, values in getStatements(fakeDatabase, "ALTER")] == ["description"]
    assert getStatements(fakeDatabase, "UPDATE")[0][1] == ("ok", 1)


def test_additionalFieldsFixedColumnName(makeMysqlAll, fakeDatabase):
    r"""!A field with the name of a fixed column does not overwrite this column"""
    makeMysqlAll._run(buildPacket("zvei", {"tone": "12345", "id": "99", "pocsag_ric": "7654321"}))
    assert getStatements(fakeDatabase, "ALTER") == []
    assert getStatements(fakeDatabase, "UPDATE") == []


def test_additionalFieldsAlterDenied(makeMysqlAll, fakeDatabase):
    r"""!Without the right to add columns the alarm is saved anyway"""
    fakeDatabase.alterFails = True
    makeMysqlAll._run(buildPacket("zvei", {"tone": "12345", "description": "FF Musterdorf"}))
    makeMysqlAll._run(buildPacket("zvei", {"tone": "12345", "description": "FF Musterdorf"}))
    stats = makeMysqlAll._getStatistics()
    assert len(getInserts(fakeDatabase)) == 2
    assert fakeDatabase.commits == 2
    assert len(getStatements(fakeDatabase, "ALTER")) == 1  # not tried again
    assert getStatements(fakeDatabase, "UPDATE") == []
    assert stats["teardownErrorCount"] == 0


def test_additionalFieldsDatabaseWarnings(makeMysql, fakeDatabase, caplog):
    r"""!Warnings of the database are written to the log"""
    caplog.set_level(logging.WARNING)
    fakeDatabase.warnings = [("Warning", 1265, "Data truncated for column 'zvei_tone' at row 1")]
    makeMysql._run(buildPacket("zvei", {"tone": "123456"}))
    assert any("1265" in record.getMessage() and "Data truncated" in record.getMessage() for record in caplog.records)
