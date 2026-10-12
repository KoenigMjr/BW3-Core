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

@file:        test_pluginBase.py
@date:        12.10.2026
@author:      Claus Schichl
@description: Unittests for BOSWatch. File have to run as "pytest" unittest
"""
# problem of the pytest fixtures
# pylint: disable=redefined-outer-name
import logging
import pytest

from boswatch.configYaml import ConfigYAML
from boswatch.packet import Packet
from plugin.pluginBase import PluginBase
from plugin.template_plugin import BoswatchPlugin as TemplatePlugin


def setup_function(function):
    logging.debug("[TEST] %s.%s", function.__module__, function.__name__)


class PluginWithAlarm(PluginBase):
    r"""!Plugin which saves the call order of all methods"""

    def __init__(self, config):
        self.calledMethods = []
        self.errorIn = None
        self.parsedMessage = None
        super().__init__(__name__, config)

    def _call(self, method):
        self.calledMethods.append(method)
        if self.errorIn == method:
            raise ValueError("test error")

    def onLoad(self):
        self._call("onLoad")

    def setup(self):
        self._call("setup")

    def fms(self, bwPacket):
        self.parsedMessage = self.parseWildcards("{MODE}")
        self._call("fms")

    def pocsag(self, bwPacket):
        self._call("pocsag")

    def zvei(self, bwPacket):
        self._call("zvei")

    def msg(self, bwPacket):
        self._call("msg")

    def teardown(self):
        self._call("teardown")

    def onUnload(self):
        self._call("onUnload")


class PluginWithoutAlarm(PluginBase):
    r"""!Plugin which implements no methods"""

    def __init__(self, config):
        super().__init__(__name__, config)


@pytest.fixture
def makePlugin():
    r"""!Build a plugin object and remove it after the test"""
    plugin = PluginWithAlarm(ConfigYAML({"testKey": "testValue"}))
    yield plugin
    if plugin in PluginBase._pluginsActive:
        plugin._cleanup()


def buildPacket(mode):
    r"""!Build a BW Packet object with the given mode"""
    packet = Packet()
    packet.set("mode", mode)
    return packet


def test_pluginLoad(makePlugin):
    r"""!onLoad() is called while creating the plugin"""
    assert makePlugin.calledMethods == ["onLoad"]
    assert makePlugin in PluginBase._pluginsActive


def test_pluginConfig(makePlugin):
    r"""!The plugin has access to its config"""
    assert makePlugin.config.get("testKey") == "testValue"


def test_pluginCleanup(makePlugin):
    r"""!onUnload() is called in the cleanup"""
    makePlugin._cleanup()
    assert makePlugin.calledMethods == ["onLoad", "onUnload"]
    assert makePlugin not in PluginBase._pluginsActive


def test_pluginRunFms(makePlugin):
    r"""!Run the plugin with a FMS packet"""
    makePlugin._run(buildPacket("fms"))
    assert makePlugin.calledMethods == ["onLoad", "setup", "fms", "teardown"]


def test_pluginRunPocsag(makePlugin):
    r"""!Run the plugin with a POCSAG packet"""
    makePlugin._run(buildPacket("pocsag"))
    assert makePlugin.calledMethods == ["onLoad", "setup", "pocsag", "teardown"]


def test_pluginRunZvei(makePlugin):
    r"""!Run the plugin with a ZVEI packet"""
    makePlugin._run(buildPacket("zvei"))
    assert makePlugin.calledMethods == ["onLoad", "setup", "zvei", "teardown"]


def test_pluginRunMsg(makePlugin):
    r"""!Run the plugin with a MSG packet"""
    makePlugin._run(buildPacket("msg"))
    assert makePlugin.calledMethods == ["onLoad", "setup", "msg", "teardown"]


def test_pluginRunUnknownMode(makePlugin):
    r"""!Run the plugin with an unknown mode - only setup() and teardown() are called"""
    makePlugin._run(buildPacket("unknown"))
    assert makePlugin.calledMethods == ["onLoad", "setup", "teardown"]


def test_pluginRunReturnsNone(makePlugin):
    r"""!A plugin run always returns None"""
    assert makePlugin._run(buildPacket("fms")) is None


def test_pluginSetupError(makePlugin):
    r"""!An exception in setup() is counted - alarm and teardown are called anyway"""
    makePlugin.errorIn = "setup"
    makePlugin._run(buildPacket("fms"))
    assert makePlugin.calledMethods == ["onLoad", "setup", "fms", "teardown"]
    assert makePlugin._getStatistics()["setupErrorCount"] == 1


def test_pluginAlarmError(makePlugin):
    r"""!An exception in the alarm is counted - teardown is called anyway"""
    makePlugin.errorIn = "fms"
    makePlugin._run(buildPacket("fms"))
    assert makePlugin.calledMethods == ["onLoad", "setup", "fms", "teardown"]
    assert makePlugin._getStatistics()["alarmErrorCount"] == 1


def test_pluginTeardownError(makePlugin):
    r"""!An exception in teardown() is counted"""
    makePlugin.errorIn = "teardown"
    makePlugin._run(buildPacket("fms"))
    assert makePlugin._getStatistics()["teardownErrorCount"] == 1


def test_pluginStatistics(makePlugin):
    r"""!Get the statistics after two plugin runs"""
    makePlugin._run(buildPacket("fms"))
    makePlugin._run(buildPacket("pocsag"))
    stats = makePlugin._getStatistics()
    assert stats["type"] == "plugin"
    assert stats["runCount"] == 2
    assert stats["setupErrorCount"] == 0
    assert stats["alarmErrorCount"] == 0
    assert stats["teardownErrorCount"] == 0
    assert stats["cumTime"] >= stats["sumTime"] >= 0


def test_pluginParseWildcards(makePlugin):
    r"""!Wildcards are replaced while the alarm is running"""
    makePlugin._run(buildPacket("fms"))
    assert makePlugin.parsedMessage == "fms"


def test_pluginParseWildcardsWithoutRun(makePlugin):
    r"""!Wildcards are not replaced outside of a run"""
    makePlugin._run(buildPacket("fms"))
    assert makePlugin.parseWildcards("{MODE}") == "{MODE}"


def test_pluginWithoutAlarm():
    r"""!A plugin without implemented methods runs all modes without errors"""
    plugin = PluginWithoutAlarm(ConfigYAML())
    for mode in ["fms", "pocsag", "zvei", "msg"]:
        plugin._run(buildPacket(mode))
    assert plugin._getStatistics()["alarmErrorCount"] == 0
    plugin._cleanup()


def test_pluginWithoutAlarmWarning(caplog):
    r"""!A plugin without implemented methods logs a warning with the right mode"""
    caplog.set_level(logging.WARNING)
    plugin = PluginWithoutAlarm(ConfigYAML())
    for mode in ["fms", "pocsag", "zvei", "msg"]:
        plugin._run(buildPacket(mode))
    plugin._cleanup()
    warnings = [record.getMessage().split()[0] for record in caplog.records]
    assert warnings == ["FMS", "POCSAG", "ZVEI", "MSG"]


def test_templatePlugin():
    r"""!The template plugin runs all modes without errors"""
    plugin = TemplatePlugin(ConfigYAML())
    for mode in ["fms", "pocsag", "zvei", "msg"]:
        plugin._run(buildPacket(mode))
    stats = plugin._getStatistics()
    assert stats["setupErrorCount"] == 0
    assert stats["alarmErrorCount"] == 0
    assert stats["teardownErrorCount"] == 0
    plugin._cleanup()
