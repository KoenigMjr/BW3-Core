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

@file:        test_descriptor.py
@date:        12.10.2026
@author:      Bastian Schroll
@description: Unittests for BOSWatch. File have to run as "pytest" unittest
"""
# problem of the pytest fixtures
# pylint: disable=redefined-outer-name
import logging
import pytest
from boswatch.utils import paths
from boswatch import wildcard

from boswatch.configYaml import ConfigYAML
from boswatch.packet import Packet
from module.descriptor import BoswatchModule as Descriptor


def setup_function(function):
    logging.debug("[TEST] %s.%s", function.__module__, function.__name__)


@pytest.fixture
def makeDescriptor():
    r"""!Build a descriptor object with loaded configuration"""
    config = ConfigYAML()
    assert config.loadConfigFile(paths.TEST_PATH + "test_config.yaml") is True
    descriptor = Descriptor(config.get("descriptor_test"))
    return descriptor


@pytest.fixture
def getConfig():
    r"""!Build a config object and fill it with the config data"""
    config = ConfigYAML()
    assert config.loadConfigFile(paths.TEST_PATH + "test_config.yaml") is True
    return config


@pytest.fixture
def emptyWildcards(monkeypatch):
    r"""!Use an empty list of additional wildcards for the test"""
    monkeypatch.setattr(wildcard, "_additionalWildcards", {})


@pytest.fixture
def makePacket():
    r"""!Build a BW Packet object"""
    packet = Packet()
    return packet


def test_descriptorFoundFirst(makeDescriptor, makePacket):
    r"""!Run descriptor on the first entry in list"""
    makePacket.set("tone", "12345")
    makePacket = makeDescriptor.doWork(makePacket)
    assert makePacket.get("description") == "Test 12345"


def test_descriptorFoundSecond(makeDescriptor, makePacket):
    r"""!Run descriptor on the second entry in list"""
    makePacket.set("tone", "23456")
    makePacket = makeDescriptor.doWork(makePacket)
    assert makePacket.get("description") == "Test 23456"


def test_descriptorNotFound(makeDescriptor, makePacket):
    r"""!Run descriptor no matching data found"""
    makePacket.set("tone", "99999")
    makePacket = makeDescriptor.doWork(makePacket)
    assert makePacket.get("description") == "99999"


def test_descriptorScanFieldNotAvailable(makeDescriptor, makePacket):
    r"""!Run descriptor on a non existent scanField"""
    makePacket = makeDescriptor.doWork(makePacket)
    assert makePacket.get("description") is None


def runDescriptor(config, section, packet):
    r"""!Build a descriptor with the given config section and run it on the packet"""
    descriptor = Descriptor(config.get(section))
    packet = descriptor.doWork(packet)
    descriptor._cleanup()
    return packet


def test_descriptorExactBeforeRegex(getConfig, makePacket):
    r"""!An exact match is used even if a regex would also match"""
    makePacket.set("tone", "12345")
    assert runDescriptor(getConfig, "descriptor_regex", makePacket).get("description") == "Exact 12345"


def test_descriptorRegex(getConfig, makePacket):
    r"""!A regex is used if there is no exact match"""
    makePacket.set("tone", "12399")
    assert runDescriptor(getConfig, "descriptor_regex", makePacket).get("description") == "Regex 123"


def test_descriptorRegexGroupSingleQuoted(getConfig, makePacket):
    r"""!A regex group is used in the description - single quoted with one backslash"""
    makePacket.set("tone", "89015")
    assert runDescriptor(getConfig, "descriptor_regex", makePacket).get("description") == "Wache 15"


def test_descriptorRegexGroupDoubleQuoted(getConfig, makePacket):
    r"""!A regex group is used in the description - double quoted with two backslashes"""
    makePacket.set("tone", "89112")
    assert runDescriptor(getConfig, "descriptor_regex", makePacket).get("description") == "Wache 12 (BF)"


def test_descriptorInvalidRegex(getConfig, makePacket):
    r"""!An invalid regex is skipped - the following entries are still checked"""
    makePacket.set("tone", "77712")
    assert runDescriptor(getConfig, "descriptor_regex", makePacket).get("description") == "String flag"


def test_descriptorLeadingZero(getConfig, makePacket):
    r"""!A quoted value with leading zeros is found"""
    makePacket.set("tone", "05678")
    assert runDescriptor(getConfig, "descriptor_regex", makePacket).get("description") == "Leading zero"


def test_descriptorWildcardsInDescription(getConfig, makePacket):
    r"""!Wildcards in the description are replaced with the packet fields"""
    makePacket.set("mode", "zvei")
    makePacket.set("tone", "55555")
    assert runDescriptor(getConfig, "descriptor_regex", makePacket).get("description") == "Alarm zvei 55555"


def test_descriptorMultipleDescriptors(getConfig, makePacket):
    r"""!All descriptors are run on the packet"""
    makePacket.set("tone", "12345")
    makePacket.set("status", "3")
    makePacket = runDescriptor(getConfig, "descriptor_multi", makePacket)
    assert makePacket.get("description") == "Test 12345"
    assert makePacket.get("statusText") == "Einsatz Ab"


def test_descriptorMultipleDescriptorsOneField(getConfig, makePacket):
    r"""!Only the descriptor with an available scanField sets its field"""
    makePacket.set("status", "3")
    makePacket = runDescriptor(getConfig, "descriptor_multi", makePacket)
    assert makePacket.get("description") is None
    assert makePacket.get("statusText") == "Einsatz Ab"


def test_descriptorRegisterWildcard(getConfig, emptyWildcards):
    r"""!The configured wildcard is registered for the descrField"""
    descriptor = Descriptor(getConfig.get("descriptor_multi"))
    assert wildcard._additionalWildcards == {"{STATUSTEXT}": "statusText"}
    descriptor._cleanup()


def test_descriptorCsv(getConfig, makePacket):
    r"""!Find an entry from the CSV file"""
    makePacket.set("tone", "11111")
    assert runDescriptor(getConfig, "descriptor_csv", makePacket).get("description") == "CSV 11111"


def test_descriptorCsvLeadingZero(getConfig, makePacket):
    r"""!Find CSV entries with leading zeros - with and without quotes"""
    makePacket.set("tone", "00123")
    assert runDescriptor(getConfig, "descriptor_csv", makePacket).get("description") == "CSV leading zero"
    makePacket.set("tone", "00456")
    assert runDescriptor(getConfig, "descriptor_csv", makePacket).get("description") == "CSV quoted"


def test_descriptorCsvWithoutRegexFlag(getConfig, makePacket):
    r"""!A CSV entry without isRegex column is an exact entry"""
    makePacket.set("tone", "23456")
    assert runDescriptor(getConfig, "descriptor_csv", makePacket).get("description") == "CSV without flag"


def test_descriptorCsvRegex(getConfig, makePacket):
    r"""!Find a regex entry from the CSV file"""
    makePacket.set("tone", "34567")
    assert runDescriptor(getConfig, "descriptor_csv", makePacket).get("description") == "CSV regex"


def test_descriptorCsvExactBeforeYamlRegex(getConfig, makePacket):
    r"""!An exact CSV entry is used even if a YAML regex would also match"""
    makePacket.set("tone", "12345")
    assert runDescriptor(getConfig, "descriptor_csv", makePacket).get("description") == "CSV exact 12345"
    makePacket.set("tone", "12346")
    assert runDescriptor(getConfig, "descriptor_csv", makePacket).get("description") == "YAML regex"


def test_descriptorCsvNotFound(getConfig, makePacket):
    r"""!A not existing CSV file does not stop the YAML descriptions"""
    makePacket.set("tone", "12345")
    assert runDescriptor(getConfig, "descriptor_csvNotFound", makePacket).get("description") == "YAML 12345"
