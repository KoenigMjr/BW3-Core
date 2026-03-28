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

@file:        template_plugin.py
@date:        28.03.2026
@author:      Claus Schichl
@description: Watchdog for Healthcheck.io
"""
import logging
import threading
import requests
from plugin.pluginBase import PluginBase

# ###################### #
# Custom plugin includes #

# ###################### #

logging.debug("- %s loaded", __name__)


class BoswatchPlugin(PluginBase):
    r"""Überwachung der Log-Aktivität via Healthchecks.io"""
    def __init__(self, config):
        r"""!Do not change anything here!"""
        super().__init__(__name__, config)  # you can access the config class on 'self.config'

    def _reset_watchdog(self):
        """Stoppt den aktuellen Timer und startet einen neuen"""
        if self.timer:
            self.timer.cancel()

        self.timer = threading.Timer(self.timeout, self._on_timeout)
        self.timer.daemon = True  # Damit der Thread BOSWatch nicht am Beenden hindert
        self.timer.start()

    def _on_timeout(self):
        """Wird aufgerufen, wenn x Sekunden lang kein Paket kam"""
        logging.warning("WATCHDOG: Seit %s Sekunden keine Aktivität! Sende KEIN Signal.", self.timeout)
        # Wir senden hier absichtlich NICHTS an Healthchecks.io.
        # Healthchecks.io schlägt Alarm, weil der regelmäßige "Ping" ausbleibt.

    def _send_ping(self):
        """Sendet den 'Alles OK' Ping an Healthchecks.io"""
        try:
            requests.get(self.url, timeout=10)
            logging.debug("WATCHDOG: Ping an Healthchecks.io gesendet.")
        except Exception as e:
            logging.error("WATCHDOG: Fehler beim Ping: %s", e)

    def onLoad(self):
        r"""!Called by import of the plugin"""
        self.timer = None
        # Konfiguration aus der yaml laden
        self.url = self.config.get("ping_url")
        # Standard: 125 Sekunden (2 Min 5 Sek)
        self.timeout = int(self.config.get("timeout", default=125))
        pass

    def setup(self):
        r"""!Called before alarm"""
        self._reset_watchdog()
        pass

    def fms(self, bwPacket):
        r"""!Called on FMS alarm

        @param bwPacket: bwPacket instance
        Remove if not implemented"""
        self._send_ping()
        self._reset_watchdog()
        pass

    def pocsag(self, bwPacket):
        r"""!Called on POCSAG alarm

        @param bwPacket: bwPacket instance
        Remove if not implemented"""
        self._send_ping()
        self._reset_watchdog()
        pass

    def zvei(self, bwPacket):
        r"""!Called on ZVEI alarm

        @param bwPacket: bwPacket instance
        Remove if not implemented"""
        self._send_ping()
        self._reset_watchdog()
        pass

    def msg(self, bwPacket):
        r"""!Called on MSG packet

        @param bwPacket: bwPacket instance
        Remove if not implemented"""
        self._send_ping()
        self._reset_watchdog()
        pass

    def teardown(self):
        r"""!Called after alarm
        Remove if not implemented"""
        pass

    def onUnload(self):
        r"""!Called by destruction of the plugin
        Remove if not implemented"""
        if self.timer:
            self.timer.cancel()
        pass
