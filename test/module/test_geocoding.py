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

@file:        test_geocoding.py
@date:        12.10.2026
@author:      Claus Schichl
@description: Unittests for BOSWatch. File have to run as "pytest" unittest
"""
# problem of the pytest fixtures
# pylint: disable=redefined-outer-name
import logging
import pytest
import geocoder
from boswatch.utils import paths

from boswatch import wildcard
from boswatch.configYaml import ConfigYAML
from boswatch.packet import Packet
from module.geocoding import BoswatchModule as Geocoding

# fixed coordinates which are returned by the fake geocoding provider
TEST_LATLNG = [48.1374, 11.5755]


def setup_function(function):
    logging.debug("[TEST] %s.%s", function.__module__, function.__name__)


class FakeResult:
    r"""!Result of the fake geocoding provider"""

    def __init__(self, latlng):
        self.latlng = latlng


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
def fakeProvider(monkeypatch, emptyWildcards):
    r"""!Replace the geocoding providers - no network access in the tests
    @return list of the provider calls as (provider, address, key)"""
    providerCalls = []

    def fakeMapbox(address, key=None):
        providerCalls.append(("mapbox", address, key))
        return FakeResult(TEST_LATLNG)

    def fakeGoogle(address, key=None):
        providerCalls.append(("google", address, key))
        return FakeResult(TEST_LATLNG)

    monkeypatch.setattr(geocoder, "mapbox", fakeMapbox)
    monkeypatch.setattr(geocoder, "google", fakeGoogle)
    return providerCalls


@pytest.fixture
def fakeProviderNoResult(monkeypatch, emptyWildcards):
    r"""!Replace the geocoding provider with one which finds no coordinates"""
    monkeypatch.setattr(geocoder, "mapbox", lambda address, key=None: FakeResult(None))


@pytest.fixture
def makeGeocoding(getConfig):
    r"""!Build a geocoding object with mapbox as provider"""
    geocoding = Geocoding(getConfig.get("geocoding_mapbox"))
    yield geocoding
    geocoding._cleanup()


def buildPacket(mode, message=None):
    r"""!Build a BW Packet object with the given mode and message"""
    packet = Packet()
    packet.set("mode", mode)
    if message is not None:
        packet.set("message", message)
    return packet


def getErrors(caplog):
    r"""!Return all logged messages with level ERROR or higher"""
    return [record.getMessage() for record in caplog.records if record.levelno >= logging.ERROR]


def test_geocodingNotPocsag(fakeProvider, makeGeocoding):
    r"""!Packets which are not POCSAG are not changed"""
    packet = makeGeocoding.doWork(buildPacket("fms", "Adresse: Marienplatz 1, München"))
    assert packet.get("address") is None
    assert fakeProvider == []


def test_geocodingMapbox(fakeProvider, makeGeocoding):
    r"""!Find the address and get the coordinates from mapbox"""
    packet = makeGeocoding.doWork(buildPacket("pocsag", "Adresse: Marienplatz 1, München"))
    assert packet.get("address") == "Marienplatz 1, München"
    assert packet.get("lat") == str(TEST_LATLNG[0])
    assert packet.get("lon") == str(TEST_LATLNG[1])
    assert fakeProvider == [("mapbox", "Marienplatz 1, München", "testToken")]


def test_geocodingGoogle(fakeProvider, getConfig):
    r"""!Find the address and get the coordinates from google"""
    geocoding = Geocoding(getConfig.get("geocoding_google"))
    packet = geocoding.doWork(buildPacket("pocsag", "Adresse: Marienplatz 1, München"))
    geocoding._cleanup()
    assert packet.get("lat") == str(TEST_LATLNG[0])
    assert fakeProvider == [("google", "Marienplatz 1, München", "testToken")]


def test_geocodingUnknownProvider(fakeProvider, getConfig):
    r"""!With an unknown provider only the address is set"""
    geocoding = Geocoding(getConfig.get("geocoding_unknownProvider"))
    packet = geocoding.doWork(buildPacket("pocsag", "Adresse: Marienplatz 1, München"))
    geocoding._cleanup()
    assert packet.get("address") == "Marienplatz 1, München"
    assert packet.get("lat") is None
    assert fakeProvider == []


def test_geocodingWildcards(fakeProvider, makeGeocoding):
    r"""!The wildcards for address and coordinates are registered"""
    makeGeocoding.doWork(buildPacket("pocsag", "Adresse: Marienplatz 1, München"))
    assert wildcard._additionalWildcards == {"{ADDRESS}": "address", "{LAT}": "lat", "{LON}": "lon"}


def test_geocodingNoAddress(fakeProvider, makeGeocoding):
    r"""!A message without address is not changed"""
    packet = makeGeocoding.doWork(buildPacket("pocsag", "Brand Wohnhaus"))
    assert packet.get("address") is None
    assert fakeProvider == []


def test_geocodingWithoutMessage(fakeProvider, makeGeocoding):
    r"""!A POCSAG packet without message is not changed"""
    packet = makeGeocoding.doWork(buildPacket("pocsag"))
    assert packet.get("address") is None
    assert fakeProvider == []


def test_geocodingAddressNotFound(fakeProviderNoResult, makeGeocoding):
    r"""!If the provider finds no coordinates only the address is set"""
    packet = makeGeocoding.doWork(buildPacket("pocsag", "Adresse: Nirgendwo 1"))
    assert packet.get("address") == "Nirgendwo 1"
    assert packet.get("lat") is None


def test_geocodingTwoRunsNoError(fakeProvider, makeGeocoding, caplog):
    r"""!A second run does not log errors"""
    makeGeocoding.doWork(buildPacket("pocsag", "Adresse: Marienplatz 1, München"))
    caplog.set_level(logging.ERROR)
    makeGeocoding.doWork(buildPacket("pocsag", "Adresse: Marienplatz 2, München"))
    assert getErrors(caplog) == []


def test_geocodingNoAddressNoError(fakeProvider, makeGeocoding, caplog):
    r"""!A message without address does not log errors"""
    caplog.set_level(logging.ERROR)
    makeGeocoding.doWork(buildPacket("pocsag", "Brand Wohnhaus"))
    assert getErrors(caplog) == []


def test_geocodingWithoutMessageNoError(fakeProvider, makeGeocoding, caplog):
    r"""!A POCSAG packet without message does not log errors"""
    caplog.set_level(logging.ERROR)
    makeGeocoding.doWork(buildPacket("pocsag"))
    assert getErrors(caplog) == []


def test_geocodingAddressNotFoundNoError(fakeProviderNoResult, makeGeocoding, caplog):
    r"""!An address without coordinates does not log errors"""
    caplog.set_level(logging.ERROR)
    makeGeocoding.doWork(buildPacket("pocsag", "Adresse: Nirgendwo 1"))
    assert getErrors(caplog) == []
