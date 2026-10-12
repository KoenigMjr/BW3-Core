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

@file:        test_routerManager.py
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
from boswatch.router.routerManager import RouterManager
from module.moduleBase import ModuleBase


def setup_function(function):
    logging.debug("[TEST] %s.%s", function.__module__, function.__name__)


@pytest.fixture
def getConfig():
    r"""!Build a config object and fill it with the config data"""
    config = ConfigYAML()
    assert config.loadConfigFile(paths.TEST_PATH + "test_config.yaml") is True
    return config


@pytest.fixture
def makeRouterManager():
    r"""!Build a router manager object"""
    return RouterManager()


@pytest.fixture
def makeBuiltRouterManager(getConfig, makeRouterManager):
    r"""!Build a router manager object with the routers of the valid test config"""
    assert makeRouterManager.buildRouters(getConfig.get("routerManager_test")) is True
    return makeRouterManager


@pytest.fixture
def makePacket():
    r"""!Build a BW Packet object"""
    packet = Packet()
    packet.set("mode", "fms")
    return packet


def test_buildRouters(makeBuiltRouterManager):
    r"""!Build all routers of a valid config"""
    assert list(makeBuiltRouterManager._routerDict.keys()) == ["Router1", "Router2"]


def test_buildRoutersRoutePoints(makeBuiltRouterManager):
    r"""!Check the route points of a built router - without name the resource is used as name"""
    routePoints = makeBuiltRouterManager._routerDict["Router1"].routeList
    assert [routePoint.name for routePoint in routePoints] == ["Test Module", "template_plugin", "Router2"]


def test_buildRoutersCallbacks(makeBuiltRouterManager):
    r"""!Modules and plugins get statistics and cleanup callbacks - routers not"""
    module, plugin, router = makeBuiltRouterManager._routerDict["Router1"].routeList
    assert module.statistics and module.cleanup
    assert plugin.statistics and plugin.cleanup
    assert router.statistics is None
    assert router.cleanup is None


def test_buildRoutersDuplicateName(getConfig, makeRouterManager):
    r"""!Build routers with a duplicated router name"""
    assert makeRouterManager.buildRouters(getConfig.get("routerManager_duplicateName")) is False


def test_buildRoutersMissingName(getConfig, makeRouterManager):
    r"""!Build routers where a router has no name"""
    assert makeRouterManager.buildRouters(getConfig.get("routerManager_missingName")) is False


def test_buildRoutersMissingRoute(getConfig, makeRouterManager):
    r"""!Build routers where a router has no route"""
    assert makeRouterManager.buildRouters(getConfig.get("routerManager_missingRoute")) is False


def test_buildRoutersMissingType(getConfig, makeRouterManager):
    r"""!Build routers where a route point has no type"""
    assert makeRouterManager.buildRouters(getConfig.get("routerManager_missingType")) is False


def test_buildRoutersUnknownType(getConfig, makeRouterManager):
    r"""!Build routers where a route point has an unknown type"""
    assert makeRouterManager.buildRouters(getConfig.get("routerManager_unknownType")) is False


def test_buildRoutersModuleNotFound(getConfig, makeRouterManager):
    r"""!Build routers where a module is not available"""
    assert makeRouterManager.buildRouters(getConfig.get("routerManager_moduleNotFound")) is False


def test_buildRoutersUnknownRouter(getConfig, makeRouterManager):
    r"""!Build routers where a route point jumps to a not existing router"""
    assert makeRouterManager.buildRouters(getConfig.get("routerManager_unknownRouter")) is False


def test_buildRoutersFailedClearsRouters(getConfig, makeBuiltRouterManager):
    r"""!A failed build removes the routers of the previous build"""
    assert makeBuiltRouterManager.buildRouters(getConfig.get("routerManager_unknownType")) is False
    assert makeBuiltRouterManager._routerDict == {}


def test_runRoutersSingleName(makeBuiltRouterManager, makePacket):
    r"""!Run a single router given as string"""
    makeBuiltRouterManager.runRouters("Router2", makePacket)
    assert makeBuiltRouterManager._routerDict["Router1"]._getStatistics()["runCount"] == 0
    assert makeBuiltRouterManager._routerDict["Router2"]._getStatistics()["runCount"] == 1


def test_runRoutersList(makeBuiltRouterManager, makePacket):
    r"""!Run routers given as list - Router1 jumps also into Router2"""
    makeBuiltRouterManager.runRouters(["Router1", "Router2"], makePacket)
    assert makeBuiltRouterManager._routerDict["Router1"]._getStatistics()["runCount"] == 1
    assert makeBuiltRouterManager._routerDict["Router2"]._getStatistics()["runCount"] == 2


def test_runRoutersUnknownName(makeBuiltRouterManager, makePacket):
    r"""!Run a not existing router - the existing routers are not run"""
    makeBuiltRouterManager.runRouters("notExistingRouter", makePacket)
    assert makeBuiltRouterManager._routerDict["Router1"]._getStatistics()["runCount"] == 0
    assert makeBuiltRouterManager._routerDict["Router2"]._getStatistics()["runCount"] == 0


def test_cleanup(makeBuiltRouterManager):
    r"""!Run the cleanup of all loaded modules"""
    module = makeBuiltRouterManager._routerDict["Router1"].routeList[0].cleanup.__self__
    assert module in ModuleBase._modulesActive
    makeBuiltRouterManager.cleanup()
    assert module not in ModuleBase._modulesActive


def test_saveStats(getConfig, makeRouterManager, makePacket, tmp_path, monkeypatch):
    r"""!With enabled logging the statistics are saved to a file after the routers run"""
    assert makeRouterManager.buildRouters(getConfig.get("routerManager_saveStats")) is True
    monkeypatch.chdir(tmp_path)
    makeRouterManager.runRouters("Router1", makePacket)
    statsFile = tmp_path / ("stats_" + str(makeRouterManager._startTime) + ".txt")
    assert statsFile.read_text() == ("[Router1]\n"
                                     " - Route points:    3\n"
                                     " - Runs:            1\n"
                                     "[+] Test Module\n"
                                     " - Runs:            1\n"
                                     " - Run errors:      0\n"
                                     "[+] template_plugin\n"
                                     " - Runs:            1\n"
                                     " - Setup errors:    0\n"
                                     " - Alarm errors:    0\n"
                                     " - Teardown errors: 0\n"
                                     "[+] Router2\n"
                                     "\n"
                                     "[Router2]\n"
                                     " - Route points:    1\n"
                                     " - Runs:            1\n"
                                     "[+] template_module\n"
                                     " - Runs:            1\n"
                                     " - Run errors:      0\n"
                                     "\n")
    makeRouterManager.cleanup()


def test_saveStatsOverwrite(getConfig, makeRouterManager, makePacket, tmp_path, monkeypatch):
    r"""!The statistics file is overwritten with the current values on every run"""
    assert makeRouterManager.buildRouters(getConfig.get("routerManager_saveStats")) is True
    monkeypatch.chdir(tmp_path)
    makeRouterManager.runRouters("Router2", makePacket)
    makeRouterManager.runRouters("Router2", makePacket)
    assert len(list(tmp_path.iterdir())) == 1
    statsLines = (tmp_path / ("stats_" + str(makeRouterManager._startTime) + ".txt")).read_text().splitlines()
    assert statsLines.count(" - Runs:            2") == 2
    makeRouterManager.cleanup()


def test_saveStatsDisabled(makeBuiltRouterManager, makePacket, tmp_path, monkeypatch):
    r"""!Without enabled logging no statistics file is written"""
    monkeypatch.chdir(tmp_path)
    makeBuiltRouterManager.runRouters("Router1", makePacket)
    assert list(tmp_path.iterdir()) == []
