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

@file:        test_doubleFilter.py
@date:        12.10.2026
@author:      Claus Schichl
@description: Unittests for BOSWatch. File have to run as "pytest" unittest
"""
# problem of the pytest fixtures
# pylint: disable=redefined-outer-name
import logging
import pytest
from boswatch.utils import paths

from boswatch.configYaml import ConfigYAML
from boswatch.packet import Packet
from module.filter.doubleFilter import BoswatchModule as DoubleFilter


def setup_function(function):
    logging.debug("[TEST] %s.%s", function.__module__, function.__name__)


@pytest.fixture
def getConfig():
    r"""!Build a config object and fill it with the config data"""
    config = ConfigYAML()
    assert config.loadConfigFile(paths.TEST_PATH + "test_config.yaml") is True
    return config


@pytest.fixture
def makeDoubleFilter(getConfig):
    r"""!Build a double filter object with loaded configuration"""
    doubleFilter = DoubleFilter(getConfig.get("doubleFilter_test"))
    yield doubleFilter
    doubleFilter._cleanup()


def buildPacket(timestamp, fields):
    r"""!Build a BW Packet object with the given timestamp and fields"""
    packet = Packet()
    packet.set("timestamp", timestamp)
    for fieldName, value in fields.items():
        packet.set(fieldName, value)
    return packet


def test_doubleFilterFirstPacket(makeDoubleFilter):
    r"""!The first packet passes the filter"""
    assert makeDoubleFilter.doWork(buildPacket(1000, {"mode": "fms", "fms": "93377141"})) is None


def test_doubleFilterDuplicate(makeDoubleFilter):
    r"""!A duplicate within the ignore time is stopped - uses the packet timestamps and not the current time"""
    assert makeDoubleFilter.doWork(buildPacket(1000, {"mode": "fms", "fms": "93377141"})) is None
    assert makeDoubleFilter.doWork(buildPacket(1005, {"mode": "fms", "fms": "93377141"})) is False


def test_doubleFilterDuplicateIgnoreTimeLimit(makeDoubleFilter):
    r"""!A duplicate exactly at the end of the ignore time is still stopped"""
    assert makeDoubleFilter.doWork(buildPacket(1000, {"mode": "fms", "fms": "93377141"})) is None
    assert makeDoubleFilter.doWork(buildPacket(1010, {"mode": "fms", "fms": "93377141"})) is False


def test_doubleFilterDuplicateAfterIgnoreTime(makeDoubleFilter):
    r"""!A duplicate after the ignore time passes the filter"""
    assert makeDoubleFilter.doWork(buildPacket(1000, {"mode": "fms", "fms": "93377141"})) is None
    assert makeDoubleFilter.doWork(buildPacket(1011, {"mode": "fms", "fms": "93377141"})) is None


def test_doubleFilterDuplicateNotAdded(makeDoubleFilter):
    r"""!A stopped duplicate is not added to the list - the ignore time starts with the first packet"""
    assert makeDoubleFilter.doWork(buildPacket(1000, {"mode": "fms", "fms": "93377141"})) is None
    assert makeDoubleFilter.doWork(buildPacket(1008, {"mode": "fms", "fms": "93377141"})) is False
    assert makeDoubleFilter.doWork(buildPacket(1015, {"mode": "fms", "fms": "93377141"})) is None


def test_doubleFilterDifferentPacket(makeDoubleFilter):
    r"""!A different packet within the ignore time passes the filter"""
    assert makeDoubleFilter.doWork(buildPacket(1000, {"mode": "fms", "fms": "93377141"})) is None
    assert makeDoubleFilter.doWork(buildPacket(1001, {"mode": "fms", "fms": "93377142"})) is None


def test_doubleFilterZvei(makeDoubleFilter):
    r"""!ZVEI packets are compared by the tone"""
    assert makeDoubleFilter.doWork(buildPacket(1000, {"mode": "zvei", "tone": "12345"})) is None
    assert makeDoubleFilter.doWork(buildPacket(1001, {"mode": "zvei", "tone": "12345"})) is False
    assert makeDoubleFilter.doWork(buildPacket(1002, {"mode": "zvei", "tone": "12346"})) is None


def test_doubleFilterPocsagDefaultFields(makeDoubleFilter):
    r"""!POCSAG packets are compared by ric and subric as default"""
    assert makeDoubleFilter.doWork(buildPacket(1000, {"mode": "pocsag", "ric": "1234567", "subric": "1", "message": "first"})) is None
    assert makeDoubleFilter.doWork(buildPacket(1001, {"mode": "pocsag", "ric": "1234567", "subric": "2", "message": "first"})) is None
    assert makeDoubleFilter.doWork(buildPacket(1002, {"mode": "pocsag", "ric": "1234567", "subric": "1", "message": "second"})) is False


def test_doubleFilterPocsagFieldsConfig(getConfig):
    r"""!POCSAG packets are compared by the configured fields"""
    doubleFilter = DoubleFilter(getConfig.get("doubleFilter_pocsagFields"))
    assert doubleFilter.doWork(buildPacket(1000, {"mode": "pocsag", "ric": "1234567", "subric": "1", "message": "first"})) is None
    assert doubleFilter.doWork(buildPacket(1001, {"mode": "pocsag", "ric": "1234567", "subric": "2", "message": "first"})) is False
    assert doubleFilter.doWork(buildPacket(1002, {"mode": "pocsag", "ric": "1234567", "subric": "1", "message": "second"})) is None
    doubleFilter._cleanup()


def test_doubleFilterMsg(makeDoubleFilter):
    r"""!MSG packets are not supported and stopped by the filter"""
    assert makeDoubleFilter.doWork(buildPacket(1000, {"mode": "msg", "message": "test"})) is False


def test_doubleFilterMaxEntry(makeDoubleFilter):
    r"""!If the list is full the oldest packet is removed"""
    for fms in ["93377141", "93377142", "93377143", "93377144"]:
        assert makeDoubleFilter.doWork(buildPacket(1000, {"mode": "fms", "fms": fms})) is None
    assert makeDoubleFilter.doWork(buildPacket(1001, {"mode": "fms", "fms": "93377141"})) is None
    assert makeDoubleFilter.doWork(buildPacket(1002, {"mode": "fms", "fms": "93377144"})) is False


def test_doubleFilterModesSeparated(makeDoubleFilter):
    r"""!Every mode has its own list - packets of other modes do not remove entries"""
    assert makeDoubleFilter.doWork(buildPacket(1000, {"mode": "fms", "fms": "93377141"})) is None
    for tone in ["12345", "12346", "12347", "12348"]:
        assert makeDoubleFilter.doWork(buildPacket(1001, {"mode": "zvei", "tone": tone})) is None
    assert makeDoubleFilter.doWork(buildPacket(1002, {"mode": "fms", "fms": "93377141"})) is False


def test_doubleFilterDefaultConfig(getConfig):
    r"""!Without config the ignore time is 10 seconds"""
    doubleFilter = DoubleFilter(getConfig.get("doubleFilter_default"))
    assert doubleFilter.doWork(buildPacket(1000, {"mode": "fms", "fms": "93377141"})) is None
    assert doubleFilter.doWork(buildPacket(1010, {"mode": "fms", "fms": "93377141"})) is False
    assert doubleFilter.doWork(buildPacket(1021, {"mode": "fms", "fms": "93377141"})) is None
    doubleFilter._cleanup()
