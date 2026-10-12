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

@file:        http.py
@date:        12.10.2026
@author:      Jan Speller
@description: Http Plugin
"""
import logging
from plugin.pluginBase import PluginBase

# ###################### #
# Custom plugin includes #
import asyncio
from urllib.parse import quote
from aiohttp import ClientSession
from boswatch import wildcard
from boswatch.packet import Packet
# ###################### #

logging.debug("- %s loaded", __name__)


class BoswatchPlugin(PluginBase):
    r"""!Description of the Plugin"""
    def __init__(self, config):
        r"""!Do not change anything here!"""
        super().__init__(__name__, config)  # you can access the config class on 'self.config'

    def fms(self, bwPacket):
        r"""!Called on FMS alarm

        @param bwPacket: bwPacket instance
        Remove if not implemented"""
        urls = self.config.get("fms")
        self._makeRequests(urls)

    def pocsag(self, bwPacket):
        r"""!Called on POCSAG alarm

        @param bwPacket: bwPacket instance
        Remove if not implemented"""
        urls = self.config.get("pocsag")
        self._makeRequests(urls)

    def zvei(self, bwPacket):
        r"""!Called on ZVEI alarm

        @param bwPacket: bwPacket instance
        Remove if not implemented"""
        urls = self.config.get("zvei")
        self._makeRequests(urls)

    def msg(self, bwPacket):
        r"""!Called on MSG packet

        @param bwPacket: bwPacket instance
        Remove if not implemented"""
        urls = self.config.get("msg")
        self._makeRequests(urls)

    def _makeRequests(self, urls):
        """Parses wildcard urls and handles asynchronus requests

        @param urls: array of urls"""
        if not urls:
            logging.debug("no urls configured for this mode")
            return

        urls = [self._parseUrlWildcards(url) for url in urls]
        asyncio.run(self._asyncRequests(urls))

    def _parseUrlWildcards(self, url):
        r"""!Replace the wildcards in an url with url encoded values

        @param url: url with wildcards
        @return url with replaced and encoded wildcards"""
        encodedPacket = Packet(str(self._bwPacket))
        for fieldName, value in encodedPacket._packet.items():
            encodedPacket._packet[fieldName] = quote(str(value), safe="")
        return wildcard.replaceWildcards(url, encodedPacket)

    async def _asyncRequests(self, urls):
        """Handles asynchronus requests

        @param urls: array of urls to send requests to"""
        tasks = []

        async with ClientSession() as session:
            for url in urls:
                task = asyncio.ensure_future(self._fetch(url, session))
                tasks.append(task)

            responses = await asyncio.gather(*tasks, return_exceptions=True)

        errors = [response for response in responses if isinstance(response, Exception)]
        for error in errors:
            logging.error("request failed: %s: %s", type(error).__name__, error)
        if errors:
            raise RuntimeError("{} of {} requests failed".format(len(errors), len(urls)))

    async def _fetch(self, url, session):
        """Fetches requests

        @param url: url

        @param session: Clientsession instance"""
        async with session.get(url) as response:
            logging.info("{} returned [{}]".format(response.url, response.status))
            return await response.read()
