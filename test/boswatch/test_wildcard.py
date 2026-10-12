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

@file:        test_wildcard.py
@date:        12.10.2026
@author:      Claus Schichl
@description: Unittests for BOSWatch. File have to run as "pytest" unittest
"""
# problem of the pytest fixtures
# pylint: disable=redefined-outer-name
import logging
import time
import pytest

from boswatch import wildcard
from boswatch.packet import Packet

# fixed timestamp for the time wildcards
TEST_TIMESTAMP = 1700000000.0


def setup_function(function):
    logging.debug("[TEST] %s.%s", function.__module__, function.__name__)


def buildPacket(mode):
    r"""!Build a BW Packet object with all fields of the given mode"""
    packet = Packet()
    packet.set("timestamp", TEST_TIMESTAMP)
    packet.set("mode", mode)
    packet.set("serverName", "testServer")
    packet.set("serverVersion", "3.0.0")
    packet.set("serverBuildDate", "01.01.2026")
    packet.set("serverBranch", "testServerBranch")
    packet.set("clientName", "testClient")
    packet.set("clientIP", "127.0.0.1")
    packet.set("clientVersion", "3.0.1")
    packet.set("clientBuildDate", "02.01.2026")
    packet.set("clientBranch", "testClientBranch")
    packet.set("inputSource", "sdr")
    packet.set("frequency", "85000000")
    if mode == "fms":
        packet.set("fms", "93377141")
        packet.set("service", "testService")
        packet.set("country", "testCountry")
        packet.set("location", "testLocation")
        packet.set("vehicle", "testVehicle")
        packet.set("status", "3")
        packet.set("direction", "0")
        packet.set("directionText", "testDirectionText")
        packet.set("tacticalInfo", "III")
    if mode == "pocsag":
        packet.set("bitrate", "1200")
        packet.set("ric", "1234567")
        packet.set("subric", "1")
        packet.set("subricText", "a")
        packet.set("message", "testPocsagMessage")
    if mode == "zvei":
        packet.set("tone", "12345")
    if mode == "msg":
        packet.set("message", "testMsgMessage")
    return packet


@pytest.fixture
def emptyWildcards(monkeypatch):
    r"""!Use an empty list of additional wildcards for the test"""
    monkeypatch.setattr(wildcard, "_additionalWildcards", {})


def test_replaceFormattingWildcards():
    r"""!Replace the formatting wildcards"""
    message = wildcard.replaceWildcards("{BR}{LPAR}{RPAR}", buildPacket("fms"))
    assert message == "\r\n()"


def test_replaceTimeWildcards():
    r"""!Replace the time wildcards with the timestamp of the packet"""
    message = wildcard.replaceWildcards("{TIME}|{TIMES}", buildPacket("fms"))
    expectedTime = time.strftime("%d.%m.%Y %H:%M:%S", time.localtime(TEST_TIMESTAMP))
    assert message == expectedTime + "|" + str(TEST_TIMESTAMP)


def test_replaceServerWildcards():
    r"""!Replace the server wildcards"""
    message = wildcard.replaceWildcards("{SNAME}|{SVERS}|{SDATE}|{SBRCH}", buildPacket("fms"))
    assert message == "testServer|3.0.0|01.01.2026|testServerBranch"


def test_replaceClientWildcards():
    r"""!Replace the client wildcards"""
    message = wildcard.replaceWildcards("{CNAME}|{CIP}|{CVERS}|{CDATE}|{CBRCH}", buildPacket("fms"))
    assert message == "testClient|127.0.0.1|3.0.1|02.01.2026|testClientBranch"


def test_replaceBoswatchWildcards():
    r"""!Replace the boswatch wildcards"""
    message = wildcard.replaceWildcards("{INSRC}|{FREQ}|{MODE}", buildPacket("fms"))
    assert message == "sdr|85000000|fms"


def test_replaceFmsWildcards():
    r"""!Replace the FMS wildcards"""
    message = wildcard.replaceWildcards("{FMS}|{SERV}|{COUNT}|{LOC}|{VEHC}|{STAT}|{DIR}|{DIRT}|{TACI}", buildPacket("fms"))
    assert message == "93377141|testService|testCountry|testLocation|testVehicle|3|0|testDirectionText|III"


def test_replacePocsagWildcards():
    r"""!Replace the POCSAG wildcards"""
    message = wildcard.replaceWildcards("{BIT}|{RIC}|{SRIC}|{SRICT}|{MSG}", buildPacket("pocsag"))
    assert message == "1200|1234567|1|a|testPocsagMessage"


def test_replaceZveiWildcards():
    r"""!Replace the ZVEI wildcards"""
    message = wildcard.replaceWildcards("{TONE}", buildPacket("zvei"))
    assert message == "12345"


def test_replaceMsgWildcards():
    r"""!Replace the MSG wildcards"""
    message = wildcard.replaceWildcards("{MSG}", buildPacket("msg"))
    assert message == "testMsgMessage"


def test_replaceWildcardsOfOtherMode():
    r"""!Wildcards of another mode are not replaced"""
    message = wildcard.replaceWildcards("{RIC}|{TONE}|{MSG}", buildPacket("fms"))
    assert message == "{RIC}|{TONE}|{MSG}"


def test_replaceWildcardsMissingField():
    r"""!Wildcards with a missing field in the packet are not replaced"""
    packet = Packet()
    packet.set("mode", "fms")
    message = wildcard.replaceWildcards("{FMS}|{SNAME}|{MODE}", packet)
    assert message == "{FMS}|{SNAME}|fms"


def test_replaceUnknownWildcard():
    r"""!Unknown wildcards and text without wildcards stay unchanged"""
    message = wildcard.replaceWildcards("Text {UNKNOWN} Text", buildPacket("fms"))
    assert message == "Text {UNKNOWN} Text"


def test_replaceWildcardMultipleTimes():
    r"""!A wildcard which is used multiple times is replaced everywhere"""
    message = wildcard.replaceWildcards("{MODE}-{MODE}", buildPacket("zvei"))
    assert message == "zvei-zvei"


def test_registerWildcard(emptyWildcards):
    r"""!Register a new wildcard and replace it in all modes"""
    wildcard.registerWildcard("{TESTWILDCARD}", "testField")
    for mode in ["fms", "pocsag", "zvei", "msg"]:
        packet = buildPacket(mode)
        packet.set("testField", "testValue")
        assert wildcard.replaceWildcards("{TESTWILDCARD}", packet) == "testValue"


def test_registerWildcardMissingField(emptyWildcards):
    r"""!A registered wildcard with a missing field in the packet is not replaced"""
    wildcard.registerWildcard("{TESTWILDCARD}", "testField")
    assert wildcard.replaceWildcards("{TESTWILDCARD}", buildPacket("fms")) == "{TESTWILDCARD}"


def test_registerWildcardDouble(emptyWildcards):
    r"""!A wildcard which is registered twice keeps the first field"""
    wildcard.registerWildcard("{TESTWILDCARD}", "firstField")
    wildcard.registerWildcard("{TESTWILDCARD}", "secondField")
    packet = buildPacket("fms")
    packet.set("firstField", "firstValue")
    packet.set("secondField", "secondValue")
    assert wildcard.replaceWildcards("{TESTWILDCARD}", packet) == "firstValue"
