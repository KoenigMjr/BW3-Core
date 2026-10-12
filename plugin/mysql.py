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

@file:        mysql.py
@date:        14.10.2026
@author:      Jan Speller
@description: Mysql Plugin
"""
import logging
from plugin.pluginBase import PluginBase
from boswatch.utils import paths

# ###################### #
# Custom plugin includes #
import mysql.connector
import re
from datetime import datetime

# ###################### #

logging.debug("- %s loaded", __name__)

# packet fields which are already saved in the fixed columns of the table
FIXED_FIELDS = ["timestamp", "mode", "ric", "subric", "subricText", "message", "bitrate", "tone",
                "fms", "service", "country", "location", "vehicle", "status", "direction", "directionText", "tacticalInfo",
                "serverName", "serverVersion", "serverBuildDate", "serverBranch",
                "clientName", "clientIP", "clientVersion", "clientBuildDate", "clientBranch",
                "inputSource", "frequency"]

# columns of the table which are created by init_db.sql - never used for additional fields
FIXED_COLUMNS = ["id", "packetTimestamp", "packetMode",
                 "pocsag_ric", "pocsag_subric", "pocsag_subricText", "pocsag_message", "pocsag_bitrate",
                 "zvei_tone", "fms_fms", "fms_service", "fms_country", "fms_location", "fms_vehicle", "fms_status",
                 "fms_direction", "fms_directionText", "fms_tacticalInfo",
                 "serverName", "serverVersion", "serverBuildDate", "serverBranch",
                 "clientName", "clientIP", "clientVersion", "clientBuildDate", "clientBranch",
                 "inputSource", "frequency"]

# allowed names for additional columns (column names can not be passed as sql parameters)
COLUMN_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


class BoswatchPlugin(PluginBase):
    r"""!Description of the Plugin"""

    def __init__(self, config):
        r"""!Do not change anything here!"""
        super().__init__(__name__, config)  # you can access the config class on 'self.config'

    def onLoad(self):
        r"""!Called by import of the plugin"""
        self.sqlInserts = {
            "pocsag": "INSERT INTO boswatch (packetTimestamp, packetMode, pocsag_ric, pocsag_subric, pocsag_subricText, pocsag_message, pocsag_bitrate, serverName, serverVersion, serverBuildDate, serverBranch, clientName, clientIP, clientVersion, clientBuildDate, clientBranch, inputSource, frequency) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            "zvei": "INSERT INTO boswatch (packetTimestamp, packetMode, zvei_tone, serverName, serverVersion, serverBuildDate, serverBranch, clientName, clientIP, clientVersion, clientBuildDate, clientBranch, inputSource, frequency) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            "fms": "INSERT INTO boswatch (packetTimestamp, packetMode, fms_fms, fms_service, fms_country, fms_location, fms_vehicle, fms_status, fms_direction, fms_directionText, fms_tacticalInfo, serverName, serverVersion, serverBuildDate, serverBranch, clientName, clientIP, clientVersion, clientBuildDate, clientBranch, inputSource, frequency) VALUE (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            "msg": "INSERT INTO boswatch (packetTimestamp, packetMode, serverName, serverVersion, serverBuildDate, serverBranch, clientName, clientIP, clientVersion, clientBuildDate, clientBranch, inputSource, frequency) VALUE (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        }

        self.connection = None
        self.cursor = None
        self.columns = set()  # lower case names of all columns of the table
        self.skippedFields = set()  # additional fields which can not be saved - warn only once
        self.allFields = self.config.get("allFields", default=False) is True  # save all additional fields
        self.additionalFields = self._getConfiguredFields()  # names of the additional fields to save
        self._connect()  # trying to establish connection, no crash if fail

    def setup(self):
        r"""!Called before alarm"""
        # Zero the cursor at the start of each alarm
        self.cursor = None

        if self.connection is None:
            if not self._connect():
                logging.error("MySQL still unavailable – skipping alarm")
                return
        else:
            try:
                self.connection.ping(reconnect=True, attempts=3, delay=2)
            except mysql.connector.Error:
                logging.warning("Ping failed, trying full reconnect...")
                if not self._connect():
                    return

        # Only when the connection is established do we create a fresh cursor for this alarm
        if self.connection:
            try:
                self.cursor = self.connection.cursor()
            except mysql.connector.Error:
                self.cursor = None

    def fms(self, bwPacket):
        r"""!Called on FMS alarm

        @param bwPacket: bwPacket instance"""
        if self.cursor is None:
            logging.warning("MySQL unavailable, fms packet dropped")
            return

        val = (
            datetime.fromtimestamp(float(bwPacket.get("timestamp"))),
            bwPacket.get("mode"),
            bwPacket.get("fms"),
            bwPacket.get("service"),
            bwPacket.get("country"),
            bwPacket.get("location"),
            bwPacket.get("vehicle"),
            bwPacket.get("status"),
            bwPacket.get("direction"),
            bwPacket.get("directionText"),
            bwPacket.get("tacticalInfo"),
            bwPacket.get("serverName"),
            bwPacket.get("serverVersion"),
            bwPacket.get("serverBuildDate"),
            bwPacket.get("serverBranch"),
            bwPacket.get("clientName"),
            bwPacket.get("clientIP"),
            bwPacket.get("clientVersion"),
            bwPacket.get("clientBuildDate"),
            bwPacket.get("clientBranch"),
            bwPacket.get("inputSource"),
            bwPacket.get("frequency")
        )
        self.cursor.execute(self.sqlInserts.get("fms"), val)

    def pocsag(self, bwPacket):
        r"""!Called on POCSAG alarm

        @param bwPacket: bwPacket instance"""
        if self.cursor is None:
            logging.warning("MySQL unavailable, pocsag packet dropped")
            return

        val = (
            datetime.fromtimestamp(float(bwPacket.get("timestamp"))),
            bwPacket.get("mode"),
            bwPacket.get("ric"),
            bwPacket.get("subric"),
            bwPacket.get("subricText"),
            bwPacket.get("message"),
            bwPacket.get("bitrate"),
            bwPacket.get("serverName"),
            bwPacket.get("serverVersion"),
            bwPacket.get("serverBuildDate"),
            bwPacket.get("serverBranch"),
            bwPacket.get("clientName"),
            bwPacket.get("clientIP"),
            bwPacket.get("clientVersion"),
            bwPacket.get("clientBuildDate"),
            bwPacket.get("clientBranch"),
            bwPacket.get("inputSource"),
            bwPacket.get("frequency")
        )
        self.cursor.execute(self.sqlInserts.get("pocsag"), val)

    def zvei(self, bwPacket):
        r"""!Called on ZVEI alarm

        @param bwPacket: bwPacket instance"""
        if self.cursor is None:
            logging.warning("MySQL unavailable, zvei packet dropped")
            return

        val = (
            datetime.fromtimestamp(float(bwPacket.get("timestamp"))),
            bwPacket.get("mode"),
            bwPacket.get("tone"),
            bwPacket.get("serverName"),
            bwPacket.get("serverVersion"),
            bwPacket.get("serverBuildDate"),
            bwPacket.get("serverBranch"),
            bwPacket.get("clientName"),
            bwPacket.get("clientIP"),
            bwPacket.get("clientVersion"),
            bwPacket.get("clientBuildDate"),
            bwPacket.get("clientBranch"),
            bwPacket.get("inputSource"),
            bwPacket.get("frequency")
        )
        self.cursor.execute(self.sqlInserts.get("zvei"), val)

    def msg(self, bwPacket):
        r"""!Called on MSG packet

        @param bwPacket: bwPacket instance"""
        if self.cursor is None:
            logging.warning("MySQL unavailable, msg packet dropped")
            return

        val = (
            datetime.fromtimestamp(float(bwPacket.get("timestamp"))),
            bwPacket.get("mode"),
            bwPacket.get("serverName"),
            bwPacket.get("serverVersion"),
            bwPacket.get("serverBuildDate"),
            bwPacket.get("serverBranch"),
            bwPacket.get("clientName"),
            bwPacket.get("clientIP"),
            bwPacket.get("clientVersion"),
            bwPacket.get("clientBuildDate"),
            bwPacket.get("clientBranch"),
            bwPacket.get("inputSource"),
            bwPacket.get("frequency")
        )
        self.cursor.execute(self.sqlInserts.get("msg"), val)

    def teardown(self):
        r"""!Called after alarm"""
        if self.connection and self.cursor:
            self._storeAdditionalFields()
            try:
                self.connection.commit()
                self.cursor.close()
            except mysql.connector.Error:
                pass
            finally:
                # Ganz wichtig: Nach dem Schließen auf None setzen!
                self.cursor = None

    def onUnload(self):
        r"""!Called by destruction of the plugin"""
        if self.connection:
            try:
                self.connection.close()
            except mysql.connector.Error as e:
                logging.warning("MySQL connection could not be closed: %s", e)
            finally:
                self.connection = None

    def _connect(self):
        r"""Tries to establish MySQL connection. Returns True on success."""
        try:
            self.connection = mysql.connector.connect(
                host=self.config.get("host"),
                user=self.config.get("user"),
                password=self.config.get("password"),
                database=self.config.get("database"),
            )
            # IMPORTANT: Use a local variable for the initialization cursor
            check_cursor = self.connection.cursor()
            check_cursor.execute("SHOW TABLES LIKE 'boswatch'")

            if check_cursor.fetchone() is None:
                with open(paths.ROOT_PATH + 'init_db.sql') as f:
                    for stmnt in f.read().split(';'):
                        clean_stmnt = stmnt.strip()
                        if clean_stmnt:
                            check_cursor.execute(clean_stmnt)
                            self.connection.commit()

            check_cursor.execute("SHOW COLUMNS FROM boswatch")
            self.columns = {str(row[0]).lower() for row in check_cursor.fetchall()}

            check_cursor.close()
            self.connection.get_warnings = True  # warnings of the database are written to the log

            # the columns of configured additional fields are added already now, so a missing
            # right to add columns is noticed while starting and not at the first alarm
            for fieldName in self.additionalFields:
                if fieldName not in FIXED_FIELDS:
                    self._ensureColumn(fieldName)
            # self.cursor intentionally remains None here!
            logging.info("MySQL connection established.")
            return True
        except (mysql.connector.Error, OSError) as e:
            logging.error("MySQL connection failed: %s – running without DB", e)
            self.connection = None
            self.cursor = None  # To be on the safe side, zero it
            return False

    def _getConfiguredFields(self):
        r"""!Read the names of the additional fields from the config

        additionalFields can be a comma separated string or a list.
        With allFields: true the list is not needed and ignored.
        @return list of field names (empty if nothing is configured)"""
        configFields = self.config.get("additionalFields", default="")
        if isinstance(configFields, str):
            configFields = configFields.split(",")
        fieldNames = [str(fieldName).strip() for fieldName in configFields if str(fieldName).strip()]
        if self.allFields and fieldNames:
            logging.warning("MySQL: allFields is set - additionalFields is ignored")
            return []
        return fieldNames

    def _getAdditionalFields(self):
        r"""!Return the additional fields of the current packet which should be saved

        With allFields all fields of the packet which are not saved in a fixed column,
        otherwise only the configured fields.
        @return dict with field name and value"""
        packetFields = vars(self._bwPacket)["_packet"]  # all fields of the packet (see module packetDump)
        if self.allFields:
            fieldNames = [fieldName for fieldName in packetFields if fieldName not in FIXED_FIELDS]
        else:
            fieldNames = self.additionalFields
        return {fieldName: str(packetFields[fieldName]) for fieldName in fieldNames
                if fieldName in packetFields and fieldName not in FIXED_FIELDS}

    def _ensureColumn(self, fieldName):
        r"""!Check that a column for the field exists and add it if not

        @param fieldName: name of the packet field
        @return True if the column can be used"""
        if fieldName in self.skippedFields:
            return False
        if fieldName.lower() in [column.lower() for column in FIXED_COLUMNS]:
            logging.warning("MySQL: field '%s' not saved - the name is used by a fixed column", fieldName)
            self.skippedFields.add(fieldName)
            return False
        if fieldName.lower() in self.columns:
            return True
        if not COLUMN_NAME_PATTERN.match(fieldName):
            logging.warning("MySQL: field '%s' not saved - only letters, digits and _ are allowed in column names", fieldName)
            self.skippedFields.add(fieldName)
            return False
        try:
            cursor = self.connection.cursor()
            cursor.execute("ALTER TABLE boswatch ADD COLUMN `" + fieldName + "` TEXT NULL DEFAULT NULL")
            self._logWarnings(cursor)
            cursor.close()
            self.columns.add(fieldName.lower())
            logging.info("MySQL: added column '%s' to table boswatch", fieldName)
            return True
        except mysql.connector.Error as e:
            logging.warning("MySQL: column for field '%s' could not be added: %s", fieldName, e)
            self.skippedFields.add(fieldName)
            return False

    def _storeAdditionalFields(self):
        r"""!Save the additional fields of the current packet in the row of the last insert"""
        try:
            rowId = self.cursor.lastrowid
            self._logWarnings(self.cursor)  # warnings of the insert
            if not rowId or self._bwPacket is None or not (self.allFields or self.additionalFields):
                return
            fields = {fieldName: value for fieldName, value in self._getAdditionalFields().items()
                      if self._ensureColumn(fieldName)}
            if not fields:
                return
            assignments = ", ".join("`" + fieldName + "` = %s" for fieldName in fields)
            self.cursor.execute("UPDATE boswatch SET " + assignments + " WHERE id = %s",
                                tuple(fields.values()) + (rowId,))
            self._logWarnings(self.cursor)
        except mysql.connector.Error as e:
            logging.error("MySQL: additional fields could not be saved: %s", e)

    @staticmethod
    def _logWarnings(cursor):
        r"""!Write the warnings of the last statement to the log"""
        for level, code, message in cursor.fetchwarnings() or []:
            logging.warning("MySQL %s %s: %s", level, code, message)
