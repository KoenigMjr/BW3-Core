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

@file:        test_moduleBase.py
@date:        12.10.2026
@author:      Claus Schichl
@description: Unittests for BOSWatch. File have to run as "pytest" unittest
"""
# problem of the pytest fixtures
# pylint: disable=redefined-outer-name
import logging
import pytest

from boswatch import wildcard
from boswatch.configYaml import ConfigYAML
from boswatch.packet import Packet
from module.moduleBase import ModuleBase
from module.template_module import BoswatchModule as TemplateModule


def setup_function(function):
    logging.debug("[TEST] %s.%s", function.__module__, function.__name__)


class ModuleWithWork(ModuleBase):
    r"""!Module which implements all methods"""

    def __init__(self, config):
        self.loaded = False
        self.unloaded = False
        super().__init__(__name__, config)

    def onLoad(self):
        self.loaded = True

    def doWork(self, bwPacket):
        bwPacket.set("testField", "modified")
        return bwPacket

    def onUnload(self):
        self.unloaded = True


class ModuleWithoutWork(ModuleBase):
    r"""!Module which implements no methods"""

    def __init__(self, config):
        super().__init__(__name__, config)


class ModuleWithError(ModuleBase):
    r"""!Module which raises an exception in doWork()"""

    def __init__(self, config):
        super().__init__(__name__, config)

    def doWork(self, bwPacket):
        raise ValueError("test error")


@pytest.fixture
def makeModule():
    r"""!Build a module object and remove it after the test"""
    module = ModuleWithWork(ConfigYAML({"testKey": "testValue"}))
    yield module
    if module in ModuleBase._modulesActive:
        module._cleanup()


@pytest.fixture
def makePacket():
    r"""!Build a BW Packet object"""
    packet = Packet()
    packet.set("mode", "fms")
    packet.set("testField", "original")
    return packet


@pytest.fixture
def emptyWildcards(monkeypatch):
    r"""!Use an empty list of additional wildcards for the test"""
    monkeypatch.setattr(wildcard, "_additionalWildcards", {})


def test_moduleLoad(makeModule):
    r"""!onLoad() is called while creating the module"""
    assert makeModule.loaded is True
    assert makeModule in ModuleBase._modulesActive


def test_moduleConfig(makeModule):
    r"""!The module has access to its config"""
    assert makeModule.config.get("testKey") == "testValue"


def test_moduleCleanup(makeModule):
    r"""!onUnload() is called in the cleanup"""
    makeModule._cleanup()
    assert makeModule.unloaded is True
    assert makeModule not in ModuleBase._modulesActive


def test_moduleRun(makeModule, makePacket):
    r"""!Run the module and get the modified packet"""
    result = makeModule._run(makePacket)
    assert result.get("testField") == "modified"


def test_moduleRunWithoutWork(makePacket):
    r"""!Run a module without doWork() - returns None so the router continues with the unchanged packet"""
    module = ModuleWithoutWork(ConfigYAML())
    assert module._run(makePacket) is None
    module._cleanup()


def test_moduleRunWithError(makePacket):
    r"""!An exception in doWork() is caught and counted"""
    module = ModuleWithError(ConfigYAML())
    module._run(makePacket)
    module._run(makePacket)
    stats = module._getStatistics()
    assert stats["runCount"] == 2
    assert stats["moduleErrorCount"] == 2
    module._cleanup()


def test_moduleStatistics(makeModule, makePacket):
    r"""!Get the statistics after two module runs"""
    makeModule._run(makePacket)
    makeModule._run(makePacket)
    stats = makeModule._getStatistics()
    assert stats["type"] == "module"
    assert stats["runCount"] == 2
    assert stats["moduleErrorCount"] == 0
    assert stats["cumTime"] >= stats["moduleTime"] >= 0


def test_moduleRegisterWildcard(emptyWildcards):
    r"""!Register a new wildcard"""
    ModuleBase.registerWildcard("{TESTWILDCARD}", "testField")
    assert wildcard._additionalWildcards == {"{TESTWILDCARD}": "testField"}


def test_moduleRegisterWildcardWrongFormat(emptyWildcards):
    r"""!Register wildcards without curly brackets"""
    ModuleBase.registerWildcard("TESTWILDCARD}", "testField")
    ModuleBase.registerWildcard("{TESTWILDCARD", "testField")
    ModuleBase.registerWildcard("TESTWILDCARD", "testField")
    assert wildcard._additionalWildcards == {}


def test_moduleRegisterWildcardEmptyField(emptyWildcards):
    r"""!Register a wildcard without a bwPacket field"""
    ModuleBase.registerWildcard("{TESTWILDCARD}", "")
    assert wildcard._additionalWildcards == {}


def test_templateModule(makePacket):
    r"""!The template module runs without errors and returns the unchanged packet"""
    module = TemplateModule(ConfigYAML())
    result = module._run(makePacket)
    assert result.get("testField") == "original"
    assert module._getStatistics()["moduleErrorCount"] == 0
    module._cleanup()
