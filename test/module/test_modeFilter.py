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

@file:        test_modeFilter.py
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
from module.filter.modeFilter import BoswatchModule as ModeFilter


def setup_function(function):
    logging.debug("[TEST] %s.%s", function.__module__, function.__name__)


@pytest.fixture
def getConfig():
    r"""!Build a config object and fill it with the config data"""
    config = ConfigYAML()
    assert config.loadConfigFile(paths.TEST_PATH + "test_config.yaml") is True
    return config


@pytest.fixture
def makeModeFilter(getConfig):
    r"""!Build a mode filter object with loaded configuration"""
    modeFilter = ModeFilter(getConfig.get("modeFilter_test"))
    yield modeFilter
    modeFilter._cleanup()


def buildPacket(mode):
    r"""!Build a BW Packet object with the given mode"""
    packet = Packet()
    packet.set("mode", mode)
    return packet


def test_modeFilterAllowedFirst(makeModeFilter):
    r"""!The first allowed mode passes the filter"""
    assert makeModeFilter.doWork(buildPacket("fms")) is None


def test_modeFilterAllowedSecond(makeModeFilter):
    r"""!The second allowed mode passes the filter"""
    assert makeModeFilter.doWork(buildPacket("zvei")) is None


def test_modeFilterDenied(makeModeFilter):
    r"""!Not allowed modes are stopped by the filter"""
    assert makeModeFilter.doWork(buildPacket("pocsag")) is False
    assert makeModeFilter.doWork(buildPacket("msg")) is False


def test_modeFilterPacketWithoutMode(makeModeFilter):
    r"""!A packet without mode is stopped by the filter"""
    assert makeModeFilter.doWork(Packet()) is False


def test_modeFilterWithoutAllowed(getConfig):
    r"""!Without allowed modes all packets are stopped by the filter"""
    modeFilter = ModeFilter(getConfig.get("modeFilter_empty"))
    for mode in ["fms", "pocsag", "zvei", "msg"]:
        assert modeFilter.doWork(buildPacket(mode)) is False
    modeFilter._cleanup()
