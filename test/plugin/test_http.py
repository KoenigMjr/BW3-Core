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

@file:        test_http.py
@date:        12.10.2026
@author:      Claus Schichl
@description: Unittests for BOSWatch. File have to run as "pytest" unittest
"""
# problem of the pytest fixtures
# pylint: disable=redefined-outer-name
import logging
import threading
import pytest
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlsplit, parse_qs

from boswatch.configYaml import ConfigYAML
from boswatch.packet import Packet
from plugin.http import BoswatchPlugin as Http


def setup_function(function):
    logging.debug("[TEST] %s.%s", function.__module__, function.__name__)


class RequestHandler(BaseHTTPRequestHandler):
    r"""!Request handler of the test server - saves the path of every request"""

    def do_GET(self):
        self.server.receivedPaths.append(self.path)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass  # no output of the test server on the console


@pytest.fixture
def getHttpServer():
    r"""!Build and serve a local http server on a free port
    @return base url of the server and list of the received paths"""
    httpServer = ThreadingHTTPServer(("localhost", 0), RequestHandler)
    httpServer.receivedPaths = []
    threading.Thread(target=httpServer.serve_forever, daemon=True).start()
    yield "http://localhost:" + str(httpServer.server_address[1]), httpServer.receivedPaths
    httpServer.shutdown()
    httpServer.server_close()


def runHttp(config, packet):
    r"""!Build a http plugin with the given config, run it with the packet
    @return statistics of the plugin"""
    httpPlugin = Http(ConfigYAML(config))
    httpPlugin._run(packet)
    httpPlugin._cleanup()
    return httpPlugin._getStatistics()


def buildPacket(mode, fields=None):
    r"""!Build a BW Packet object with the given mode and fields"""
    packet = Packet()
    packet.set("mode", mode)
    for fieldName, value in (fields or {}).items():
        packet.set(fieldName, value)
    return packet


def test_httpFms(getHttpServer):
    r"""!Send the urls of a FMS alarm"""
    baseUrl, receivedPaths = getHttpServer
    runHttp({"fms": [baseUrl + "/fms"]}, buildPacket("fms"))
    assert receivedPaths == ["/fms"]


def test_httpPocsag(getHttpServer):
    r"""!Send the urls of a POCSAG alarm"""
    baseUrl, receivedPaths = getHttpServer
    runHttp({"pocsag": [baseUrl + "/pocsag"]}, buildPacket("pocsag"))
    assert receivedPaths == ["/pocsag"]


def test_httpZvei(getHttpServer):
    r"""!Send the urls of a ZVEI alarm"""
    baseUrl, receivedPaths = getHttpServer
    runHttp({"zvei": [baseUrl + "/zvei"]}, buildPacket("zvei"))
    assert receivedPaths == ["/zvei"]


def test_httpMsg(getHttpServer):
    r"""!Send the urls of a MSG packet"""
    baseUrl, receivedPaths = getHttpServer
    runHttp({"msg": [baseUrl + "/msg"]}, buildPacket("msg"))
    assert receivedPaths == ["/msg"]


def test_httpMultipleUrls(getHttpServer):
    r"""!Send all urls of an alarm"""
    baseUrl, receivedPaths = getHttpServer
    stats = runHttp({"pocsag": [baseUrl + "/first", baseUrl + "/second"]}, buildPacket("pocsag"))
    assert sorted(receivedPaths) == ["/first", "/second"]
    assert stats["alarmErrorCount"] == 0


def test_httpOnlyUrlsOfMode(getHttpServer):
    r"""!Only the urls of the packet mode are sent"""
    baseUrl, receivedPaths = getHttpServer
    runHttp({"fms": [baseUrl + "/fms"], "pocsag": [baseUrl + "/pocsag"]}, buildPacket("pocsag"))
    assert receivedPaths == ["/pocsag"]


def test_httpWildcards(getHttpServer):
    r"""!Wildcards in the url are replaced"""
    baseUrl, receivedPaths = getHttpServer
    runHttp({"pocsag": [baseUrl + "/alarm?mode={MODE}&ric={RIC}"]}, buildPacket("pocsag", {"ric": "1234567"}))
    assert receivedPaths == ["/alarm?mode=pocsag&ric=1234567"]


def test_httpWildcardSpecialCharacters(getHttpServer):
    r"""!A wildcard value with special characters of urls arrives completely"""
    baseUrl, receivedPaths = getHttpServer
    runHttp({"pocsag": [baseUrl + "/alarm?msg={MSG}&ric={RIC}"]},
            buildPacket("pocsag", {"ric": "1234567", "message": "Brand & Rauch #1 ?"}))
    query = parse_qs(urlsplit(receivedPaths[0]).query)
    assert query["msg"] == ["Brand & Rauch #1 ?"]
    assert query["ric"] == ["1234567"]


def test_httpModeWithoutUrls(getHttpServer):
    r"""!A packet of a mode without configured urls is no alarm error"""
    baseUrl, receivedPaths = getHttpServer
    stats = runHttp({"pocsag": [baseUrl + "/pocsag"]}, buildPacket("zvei"))
    assert receivedPaths == []
    assert stats["alarmErrorCount"] == 0


def test_httpUnreachableUrl(getHttpServer):
    r"""!An unreachable url is counted as error - the other urls are sent anyway"""
    baseUrl, receivedPaths = getHttpServer
    stats = runHttp({"pocsag": ["http://localhost:1/unreachable", baseUrl + "/reachable"]}, buildPacket("pocsag"))
    assert receivedPaths == ["/reachable"]
    assert stats["alarmErrorCount"] == 1
