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

@file:        test_multicast.py
@date:        14.10.2026
@author:      Claus Schichl
@description: Unittests for BOSWatch. File have to run as "pytest" unittest
"""
# problem of the pytest fixtures
# pylint: disable=redefined-outer-name
import logging
import socket
import threading
import time
import pytest
from boswatch.utils import paths

from boswatch import wildcard
from boswatch.configYaml import ConfigYAML
from boswatch.packet import Packet
from module.multicast import BoswatchModule as Multicast
from module.filter.regexFilter import BoswatchModule as RegexFilter

# frequencies and RICs of the test packets
FREQ_1 = "173.050M"
FREQ_2 = "173.075M"
TONE_RIC_1 = "0234567"
TONE_RIC_2 = "0345678"
TEXT_RIC = "0456789"
DELIMITER_RIC = "0288088"
NETIDENT_RIC = "0000001"


def setup_function(function):
    logging.debug("[TEST] %s.%s", function.__module__, function.__name__)


@pytest.fixture
def getConfig():
    r"""!Build a config object and fill it with the config data"""
    config = ConfigYAML()
    assert config.loadConfigFile(paths.TEST_PATH + "test_config.yaml") is True
    return config


@pytest.fixture
def sentTriggers(monkeypatch):
    r"""!Replace the wakeup trigger - no packets to a running BOSWatch server in the tests
    Also uses an empty list of additional wildcards for the test.
    @return list of the sent triggers as (frequency, fallback ric)"""
    triggers = []
    monkeypatch.setattr(Multicast, "_send_wakeup_trigger", lambda self, freq, ric: triggers.append((freq, ric)))
    monkeypatch.setattr(wildcard, "_additionalWildcards", {})
    return triggers


@pytest.fixture
def makeMulticast(getConfig, sentTriggers):
    r"""!Build multicast modules with a config section and remove them after the test"""
    modules = []

    def build(section="multicast_default"):
        module = Multicast(getConfig.get(section))
        modules.append(module)
        return module

    yield build
    for module in modules:
        module._cleanup()


def buildPacket(ric, message="", freq=FREQ_1, mode="pocsag", fields=None):
    r"""!Build a BW Packet object like the POCSAG decoder - a tone-RIC has an empty message"""
    packet = Packet()
    packet.set("timestamp", 1700000000.0)
    packet.set("mode", mode)
    packet.set("frequency", freq)
    packet.set("ric", ric)
    packet.set("subric", "1")
    packet.set("message", message)
    for fieldName, value in (fields or {}).items():
        packet.set(fieldName, value)
    return packet


def buildTriggerPacket(ric=TONE_RIC_1):
    r"""!Build a trigger packet like _send_wakeup_trigger() - with the marking of a control packet"""
    return buildPacket(ric, Multicast._MAGIC_WAKEUP_MSG, fields={
        "clientName": "MulticastTrigger", "multicastMode": "control", "multicastRole": "trigger",
        "multicastRecipientIndex": "0", "multicastRecipientCount": "0"})


def getField(packets, fieldName):
    r"""!Return the values of a field of all packets"""
    return [packet.get(fieldName) for packet in packets]


def waitFor(condition, timeout=5):
    r"""!Wait until the condition is true
    @return True or False if the timeout is reached"""
    endTime = time.time() + timeout
    while not condition():
        if time.time() > endTime:
            return False
        time.sleep(0.05)
    return True


def stopCleanupThread(multicast):
    r"""!Stop the cleanup thread, so only doWork() handles the timeout"""
    multicast._running = False
    assert waitFor(lambda: not multicast._cleanup_thread.is_alive())


# ============================================================
# CONFIG AND INSTANCES
# ============================================================

def test_multicastDefaultConfig(makeMulticast):
    r"""!Default values of the config"""
    multicast = makeMulticast()
    assert multicast._auto_clear_timeout == 10
    assert multicast._hard_timeout == 30
    assert multicast._delimiter_rics == []
    assert multicast._text_rics == []
    assert multicast._netident_rics == []
    assert multicast._trigger_ric is None
    assert (multicast._trigger_host, multicast._trigger_port) == ("127.0.0.1", 8080)


def test_multicastConfig(makeMulticast):
    r"""!Comma separated RIC lists with and without spaces are read"""
    multicast = makeMulticast("multicast_config")
    assert multicast._auto_clear_timeout == 5
    assert multicast._hard_timeout == 15
    assert multicast._delimiter_rics == ["0288088", "0288089"]
    assert multicast._text_rics == ["0456789", "0456790"]
    assert multicast._netident_rics == ["0000001"]
    assert multicast._trigger_ric == "9999998"
    assert (multicast._trigger_host, multicast._trigger_port) == ("127.0.0.2", 8090)


def test_multicastInstancesIsolated(makeMulticast):
    r"""!Every instance has its own buffer"""
    first = makeMulticast()
    second = makeMulticast()
    assert first.doWork(buildPacket(TONE_RIC_1)) is False
    result = second.doWork(buildPacket(TEXT_RIC, "B3 WOHNHAUS"))
    assert getField(result, "multicastMode") == ["single"]


def test_multicastTwoInstancesNoWildcardError(makeMulticast, caplog):
    r"""!Two instances do not log errors because of the same wildcards"""
    caplog.set_level(logging.ERROR)
    for multicast in [makeMulticast(), makeMulticast()]:
        multicast.doWork(buildPacket(TEXT_RIC, "B3 WOHNHAUS"))
    assert [record.getMessage() for record in caplog.records if record.levelno >= logging.ERROR] == []


def test_multicastUnload(getConfig, sentTriggers):
    r"""!The cleanup thread stops after unloading"""
    multicast = Multicast(getConfig.get("multicast_default"))
    multicast._cleanup()
    assert waitFor(lambda: not multicast._cleanup_thread.is_alive())


# ============================================================
# TONE-RICS AND TEXT-RICS
# ============================================================

def test_multicastNotPocsag(makeMulticast):
    r"""!Packets which are not POCSAG are not changed"""
    multicast = makeMulticast()
    assert multicast.doWork(buildPacket("", mode="fms")) is None


def test_multicastNotPocsagWithWaitingPackets(makeMulticast, sentTriggers):
    r"""!A packet of another mode is not lost if incomplete packets are waiting - both are returned"""
    multicast = makeMulticast("multicast_autoClear")
    multicast.doWork(buildPacket(TONE_RIC_1))
    assert waitFor(lambda: sentTriggers)
    result = multicast.doWork(buildPacket("", mode="fms"))
    assert getField(result, "mode") == ["pocsag", "fms"]
    assert getField(result, "multicastMode") == ["incomplete", None]


def test_multicastSingleAlarm(makeMulticast):
    r"""!A text without buffered tone-RICs is a single alarm"""
    multicast = makeMulticast()
    result = multicast.doWork(buildPacket(TEXT_RIC, "B3 WOHNHAUS"))
    assert len(result) == 1
    packet = result[0]
    assert (packet.get("ric"), packet.get("message")) == (TEXT_RIC, "B3 WOHNHAUS")
    assert (packet.get("multicastMode"), packet.get("multicastRole")) == ("single", "single")
    assert (packet.get("multicastSourceRic"), packet.get("multicastRecipientCount"),
            packet.get("multicastRecipientIndex")) == (TEXT_RIC, "1", "1")
    assert packet.get("ric_list") == TEXT_RIC


def test_multicastToneRicBuffered(makeMulticast):
    r"""!A tone-RIC is buffered and stops the router"""
    multicast = makeMulticast()
    assert multicast.doWork(buildPacket(TONE_RIC_1)) is False
    assert multicast.doWork(buildPacket(TONE_RIC_2)) is False


def test_multicastComplete(makeMulticast):
    r"""!The text is distributed to all buffered tone-RICs"""
    multicast = makeMulticast()
    multicast.doWork(buildPacket(TONE_RIC_1))
    multicast.doWork(buildPacket(TONE_RIC_2))
    result = multicast.doWork(buildPacket(TEXT_RIC, "B3 WOHNHAUS"))
    assert getField(result, "ric") == [TONE_RIC_1, TONE_RIC_2]
    assert getField(result, "message") == ["B3 WOHNHAUS", "B3 WOHNHAUS"]
    assert getField(result, "multicastMode") == ["complete", "complete"]
    assert getField(result, "multicastRole") == ["recipient", "recipient"]
    assert getField(result, "multicastSourceRic") == [TEXT_RIC, TEXT_RIC]
    assert getField(result, "multicastRecipientCount") == ["2", "2"]
    assert getField(result, "multicastRecipientIndex") == ["1", "2"]
    assert getField(result, "ric_list") == [TONE_RIC_1 + ", " + TONE_RIC_2] * 2


def test_multicastCompleteTimestamps(makeMulticast):
    r"""!The timestamps of the recipients are shifted by one millisecond for unique database entries"""
    multicast = makeMulticast()
    multicast.doWork(buildPacket(TONE_RIC_1))
    multicast.doWork(buildPacket(TONE_RIC_2))
    result = multicast.doWork(buildPacket(TEXT_RIC, "B3 WOHNHAUS"))
    assert [float(timestamp) for timestamp in getField(result, "timestamp")] == [1700000000.0, 1700000000.001]


def test_multicastCompleteKeepsFields(makeMulticast):
    r"""!Fields of the tone-RICs from other modules are kept and aggregated as list"""
    multicast = makeMulticast()
    multicast.doWork(buildPacket(TONE_RIC_1, fields={"description": "FF Musterstadt"}))
    multicast.doWork(buildPacket(TONE_RIC_2, fields={"description": "BF Beispiel"}))
    result = multicast.doWork(buildPacket(TEXT_RIC, "B3 WOHNHAUS"))
    assert getField(result, "description") == ["FF Musterstadt", "BF Beispiel"]
    assert getField(result, "description_list") == ["FF Musterstadt, BF Beispiel"] * 2


def test_multicastBufferEmptyAfterComplete(makeMulticast):
    r"""!After the distribution the next text is a single alarm"""
    multicast = makeMulticast()
    multicast.doWork(buildPacket(TONE_RIC_1))
    multicast.doWork(buildPacket(TEXT_RIC, "B3 WOHNHAUS"))
    result = multicast.doWork(buildPacket(TEXT_RIC, "B2 PKW"))
    assert getField(result, "multicastMode") == ["single"]


def test_multicastTextRics(makeMulticast):
    r"""!With configured text-RICs only these RICs distribute their text"""
    multicast = makeMulticast("multicast_textRics")
    multicast.doWork(buildPacket(TONE_RIC_1))
    other = multicast.doWork(buildPacket("0111111", "PROBEALARM"))
    assert getField(other, "multicastMode") == ["single"]
    result = multicast.doWork(buildPacket(TEXT_RIC, "B3 WOHNHAUS"))
    assert getField(result, "ric") == [TONE_RIC_1]
    assert getField(result, "multicastMode") == ["complete"]


def test_multicastTextRicWithoutToneRics(makeMulticast):
    r"""!A configured text-RIC without buffered tone-RICs is a single alarm"""
    multicast = makeMulticast("multicast_textRics")
    result = multicast.doWork(buildPacket(TEXT_RIC, "B3 WOHNHAUS"))
    assert getField(result, "multicastMode") == ["single"]


def test_multicastFrequenciesSeparated(makeMulticast):
    r"""!Tone-RICs of one frequency are not mixed with texts of another frequency"""
    multicast = makeMulticast()
    multicast.doWork(buildPacket(TONE_RIC_1, freq=FREQ_1))
    other = multicast.doWork(buildPacket(TEXT_RIC, "B2 PKW", freq=FREQ_2))
    assert getField(other, "multicastMode") == ["single"]
    result = multicast.doWork(buildPacket(TEXT_RIC, "B3 WOHNHAUS", freq=FREQ_1))
    assert getField(result, "ric") == [TONE_RIC_1]


def test_multicastWildcards(makeMulticast):
    r"""!The multicast and list wildcards are registered"""
    multicast = makeMulticast()
    multicast.doWork(buildPacket(TONE_RIC_1))
    multicast.doWork(buildPacket(TEXT_RIC, "B3 WOHNHAUS"))
    for wildcardName in ["{MCAST_MODE}", "{MCAST_ROLE}", "{MCAST_SOURCE}", "{MCAST_COUNT}", "{MCAST_INDEX}", "{RIC_LIST}"]:
        assert wildcardName in wildcard._additionalWildcards


# ============================================================
# DELIMITER, NETIDENT, TIMEOUT AND TRIGGER
# ============================================================

def test_multicastNetident(makeMulticast):
    r"""!A netident packet is marked and passed"""
    multicast = makeMulticast("multicast_control")
    result = multicast.doWork(buildPacket(NETIDENT_RIC))
    assert getField(result, "ric") == [NETIDENT_RIC]
    assert getField(result, "multicastMode") == ["control"]
    assert getField(result, "multicastRole") == ["netident"]
    assert getField(result, "multicastRecipientIndex") == ["0"]
    assert getField(result, "multicastRecipientCount") == ["0"]


def test_multicastDelimiter(makeMulticast):
    r"""!A delimiter packet is marked and passed"""
    multicast = makeMulticast("multicast_control")
    result = multicast.doWork(buildPacket(DELIMITER_RIC))
    assert getField(result, "ric") == [DELIMITER_RIC]
    assert getField(result, "multicastMode") == ["control"]
    assert getField(result, "multicastRole") == ["delimiter"]
    assert getField(result, "multicastRecipientIndex") == ["0"]
    assert getField(result, "multicastRecipientCount") == ["0"]


def test_multicastDelimiterClearsBuffer(makeMulticast):
    r"""!A delimiter sends buffered tone-RICs as incomplete - the delimiter itself is always passed after them"""
    multicast = makeMulticast("multicast_control")
    multicast.doWork(buildPacket(TONE_RIC_1))
    multicast.doWork(buildPacket(TONE_RIC_2))
    result = multicast.doWork(buildPacket(DELIMITER_RIC))
    assert getField(result, "ric") == [TONE_RIC_1, TONE_RIC_2, DELIMITER_RIC]
    assert getField(result, "multicastMode") == ["incomplete", "incomplete", "control"]
    assert getField(result, "message") == ["", "", ""]
    assert getField(result, "multicastSourceRic") == [TONE_RIC_1, TONE_RIC_1, DELIMITER_RIC]


def test_multicastAutoClearInDoWork(makeMulticast):
    r"""!Without the cleanup thread the next packet sends the buffered tone-RICs as incomplete after the timeout"""
    multicast = makeMulticast("multicast_autoClear")
    stopCleanupThread(multicast)
    multicast.doWork(buildPacket(TONE_RIC_1))
    time.sleep(1.2)
    result = multicast.doWork(buildPacket(TONE_RIC_2))
    assert getField(result, "ric") == [TONE_RIC_1]
    assert getField(result, "multicastMode") == ["incomplete"]


def test_multicastAutoClearTrigger(makeMulticast, sentTriggers):
    r"""!After the timeout the cleanup thread sends a trigger - the trigger packet gets the incomplete packets"""
    multicast = makeMulticast("multicast_autoClear")
    multicast.doWork(buildPacket(TONE_RIC_1))
    assert waitFor(lambda: sentTriggers)
    assert sentTriggers == [(FREQ_1, TONE_RIC_1)]
    result = multicast.doWork(buildPacket(TONE_RIC_1, Multicast._MAGIC_WAKEUP_MSG))
    assert getField(result, "ric") == [TONE_RIC_1]
    assert getField(result, "multicastMode") == ["incomplete"]


def test_multicastTriggerWithoutQueue(makeMulticast):
    r"""!A trigger packet without waiting packets is stopped - it is no alarm"""
    multicast = makeMulticast()
    assert multicast.doWork(buildPacket(TONE_RIC_1, Multicast._MAGIC_WAKEUP_MSG)) is False


def test_multicastTriggerOtherRic(makeMulticast):
    r"""!A trigger packet with another RIC than the configured trigger RIC is stopped - it is no alarm"""
    multicast = makeMulticast("multicast_triggerRic")
    assert multicast.doWork(buildPacket(TONE_RIC_1, Multicast._MAGIC_WAKEUP_MSG)) is False


def test_multicastTriggerPacket(monkeypatch):
    r"""!The trigger is a valid BOSWatch packet which is sent to the configured server"""
    monkeypatch.setattr(wildcard, "_additionalWildcards", {})
    rawServer = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    rawServer.bind(("127.0.0.1", 0))
    rawServer.listen(1)
    received = []

    def serverThread():
        connection, _ = rawServer.accept()
        connection.settimeout(3)
        length = int(connection.recv(10).decode("utf-8").strip())
        data = b""
        while len(data) < length:
            data += connection.recv(length - len(data))
        received.append(data.decode("utf-8"))
        connection.sendall(b"5         [ack]")
        connection.close()

    thread = threading.Thread(target=serverThread, daemon=True)
    thread.start()
    multicast = Multicast(ConfigYAML({"triggerRic": "9999998", "triggerPort": rawServer.getsockname()[1]}))
    multicast._send_wakeup_trigger(FREQ_1, TONE_RIC_1)
    thread.join(5)
    multicast._cleanup()
    rawServer.close()
    packet = Packet(received[0])
    assert received[0] == str(packet)  # same format as a packet sent by the client
    assert (packet.get("mode"), packet.get("ric"), packet.get("frequency")) == ("pocsag", "9999998", FREQ_1)
    assert packet.get("message") == Multicast._MAGIC_WAKEUP_MSG
    assert (packet.get("multicastMode"), packet.get("multicastRole")) == ("control", "trigger")
    assert (packet.get("multicastRecipientIndex"), packet.get("multicastRecipientCount")) == ("0", "0")


# ============================================================
# FILTER EXAMPLES OF THE DOCUMENTATION
# ============================================================

def test_multicastIndexFilterOnlyAlarms(makeMulticast):
    r"""!The filter for one packet per alarm (index 1) lets no control packets pass"""
    multicast = makeMulticast("multicast_control")
    packets = []
    packets += multicast.doWork(buildPacket(DELIMITER_RIC))
    packets += multicast.doWork(buildPacket(NETIDENT_RIC))
    multicast.doWork(buildPacket(TONE_RIC_1))
    multicast.doWork(buildPacket(TONE_RIC_2))
    packets += multicast.doWork(buildPacket(TEXT_RIC, "B3 WOHNHAUS"))
    packets += multicast.doWork(buildPacket(TEXT_RIC, "B2 PKW"))
    packets.append(buildTriggerPacket())
    indexFilter = RegexFilter(ConfigYAML([{"name": "one packet per alarm",
                                           "checks": [{"field": "multicastRecipientIndex", "regex": "^1$"}]}]))
    passed = [packet for packet in packets if indexFilter.doWork(packet) is not False]
    indexFilter._cleanup()
    passedAlarms = [(packet.get("ric"), packet.get("multicastMode")) for packet in passed]
    assert passedAlarms == [(TONE_RIC_1, "complete"), (TEXT_RIC, "single")]


def test_multicastTriggerFilterExample():
    r"""!The filter of the documentation for routers without multicast module stops only the trigger packet"""
    triggerFilter = RegexFilter(ConfigYAML([{"name": "Kein Trigger",
                                             "checks": [{"field": "clientName", "regex": "^(?!MulticastTrigger$)"}]}]))
    normalPacket = buildPacket("", mode="fms", fields={"clientName": "BOSWatch-Client"})
    assert triggerFilter.doWork(normalPacket) is None
    assert triggerFilter.doWork(buildTriggerPacket()) is False
    triggerFilter._cleanup()
