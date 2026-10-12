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

@file:        test_regexFilter.py
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
from module.filter.regexFilter import BoswatchModule as RegexFilter


def setup_function(function):
    logging.debug("[TEST] %s.%s", function.__module__, function.__name__)


@pytest.fixture
def getConfig():
    r"""!Build a config object and fill it with the config data"""
    config = ConfigYAML()
    assert config.loadConfigFile(paths.TEST_PATH + "test_config.yaml") is True
    return config


@pytest.fixture
def makeRegexFilter(getConfig):
    r"""!Build a regex filter object with loaded configuration"""
    regexFilter = RegexFilter(getConfig.get("regexFilter_test"))
    yield regexFilter
    regexFilter._cleanup()


@pytest.fixture
def makePacket():
    r"""!Build a BW Packet object"""
    packet = Packet()
    return packet


def test_regexFilterFirstFilter(makeRegexFilter, makePacket):
    r"""!A packet which passes the first filter"""
    makePacket.set("mode", "zvei")
    makePacket.set("tone", "65123")
    assert makeRegexFilter.doWork(makePacket) is None


def test_regexFilterAllChecks(makeRegexFilter, makePacket):
    r"""!A packet which passes all checks of the second filter"""
    makePacket.set("mode", "fms")
    makePacket.set("status", "3")
    assert makeRegexFilter.doWork(makePacket) is None


def test_regexFilterOneCheckFailed(makeRegexFilter, makePacket):
    r"""!If one check of a filter fails the filter fails"""
    makePacket.set("mode", "fms")
    makePacket.set("status", "4")
    assert makeRegexFilter.doWork(makePacket) is False


def test_regexFilterLastFilter(makeRegexFilter, makePacket):
    r"""!A packet which passes only the last filter"""
    makePacket.set("mode", "pocsag")
    makePacket.set("ric", "0000002")
    assert makeRegexFilter.doWork(makePacket) is None


def test_regexFilterAllFiltersFailed(makeRegexFilter, makePacket):
    r"""!A packet which passes no filter"""
    makePacket.set("mode", "pocsag")
    makePacket.set("ric", "0000004")
    assert makeRegexFilter.doWork(makePacket) is False


def test_regexFilterMissingField(makeRegexFilter, makePacket):
    r"""!A check with a missing field in the packet fails"""
    makePacket.set("mode", "fms")
    assert makeRegexFilter.doWork(makePacket) is False


def test_regexFilterEmptyField(makeRegexFilter, makePacket):
    r"""!A check with an empty field in the packet fails"""
    makePacket.set("mode", "zvei")
    makePacket.set("tone", "")
    assert makeRegexFilter.doWork(makePacket) is False


def test_regexFilterWithoutFilters(getConfig, makePacket):
    r"""!Without filters all packets are stopped"""
    regexFilter = RegexFilter(getConfig.get("regexFilter_empty"))
    makePacket.set("mode", "fms")
    assert regexFilter.doWork(makePacket) is False
    regexFilter._cleanup()
