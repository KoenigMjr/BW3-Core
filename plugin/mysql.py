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
@date:        07.05.2026
@author:      Jan Speller
@description: Mysql Plugin
"""
import logging
from plugin.pluginBase import PluginBase

# ###################### #
# Custom plugin includes #
import mysql.connector
from datetime import datetime

# ###################### #

logging.debug("- %s loaded", __name__)


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
            self.connection.close()

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
                with open('init_db.sql') as f:
                    for stmnt in f.read().split(';'):
                        clean_stmnt = stmnt.strip()
                        if clean_stmnt:
                            check_cursor.execute(clean_stmnt)
                            self.connection.commit()

            check_cursor.close()
            # self.cursor intentionally remains None here!
            logging.info("MySQL connection established.")
            return True
        except mysql.connector.Error as e:
            logging.error("MySQL connection failed: %s – running without DB", e)
            self.connection = None
            self.cursor = None  # To be on the safe side, zero it
            return False
