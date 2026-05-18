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

@file:        packetDump.py
@date:        10.06.2026
@author:      Claus Schichl
@description: Spy that reveals the COMPLETE Object
"""
import logging
from module.moduleBase import ModuleBase
import pprint

logging.debug("- %s loaded", __name__)


class BoswatchModule(ModuleBase):
    r"""!Ein Diagnose-Modul, das den kompletten Inhalt des bwPacket-Objekts im Log ausgibt."""

    def __init__(self, config):
        r"""!Do not change anything here!"""
        super().__init__(__name__, config)  # you can access the config class on 'self.config'

    def onLoad(self):
        r"""!Called by import of the plugin"""
        self.title = self.config.get("title", default="Packet Dump")

    def doWork(self, bwPacket):
        r"""!start an run of the module.

        @param bwPacket: A BOSWatch packet instance
        Gibt das Paket unverändert weiter, loggt aber den aktuellen Zustand.
        """
        logging.debug("======= [DEBUG DUMP: %s] =======", self.title)

        try:
            # vars(bwPacket) extrahiert alle Attribute und internen Dicts des Objekts, damit wir auch die dynamisch hinzugefügten Multicast-Felder sehen.
            packet_details = vars(bwPacket)
            logging.debug("\n" + pprint.pformat(packet_details))
        except Exception as e:
            # Failsafe, falls vars() bei sehr speziellen Objekten fehlschlägt
            logging.warning(f"Konnte Paket-Details nicht vollständig auslesen: {e}")
            logging.debug("\n" + pprint.pformat(bwPacket))

        logging.debug("==========================================")

        return bwPacket

    def onUnload(self):
        r"""!Called by destruction of the plugin
        Remove if not implemented"""
        pass
