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

@file:        test_telegram.py
@date:        12.10.2026
@author:      Claus Schichl
@description: Unittests for BOSWatch. File have to run as "pytest" unittest
"""
# problem of the pytest fixtures
# pylint: disable=redefined-outer-name
import logging
import re
import threading
import time
import pytest
import requests
from boswatch.utils import paths

from boswatch.configYaml import ConfigYAML
from boswatch.packet import Packet
from plugin.telegram import BoswatchPlugin as Telegram
from plugin.telegram import TelegramSender

# all characters which have to be escaped in MarkdownV2
MARKDOWN_SPECIAL_CHARS = r'_*[]()~`>#+-=|{}.!'


def setup_function(function):
    logging.debug("[TEST] %s.%s", function.__module__, function.__name__)


class FakeResponse:
    r"""!Response of the fake telegram api"""

    def __init__(self, statusCode, retryAfter=None):
        self.status_code = statusCode
        self._retryAfter = retryAfter

    def json(self):
        if self._retryAfter is None:
            return {}
        return {"parameters": {"retry_after": self._retryAfter}}


@pytest.fixture
def fakeTelegramApi(monkeypatch):
    r"""!Replace requests.post - no network access in the tests
    @return list of the sent requests as (url, data)"""
    sentRequests = []

    def fakePost(url, data=None, timeout=None):
        sentRequests.append((url, data))
        return FakeResponse(200)

    monkeypatch.setattr(requests, "post", fakePost)
    return sentRequests


@pytest.fixture
def scriptedTelegramApi(monkeypatch):
    r"""!Replace requests.post with answers from a script - no network access in the tests
    The test puts FakeResponse objects or exceptions in the script list, they are returned
    one after another. If the script is empty, every request is successful.
    @return list of the sent requests as (time, data) and the script list"""
    sentRequests = []
    script = []

    def fakePost(url, data=None, timeout=None):
        sentRequests.append((time.time(), data))
        answer = script.pop(0) if script else FakeResponse(200)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(requests, "post", fakePost)
    return sentRequests, script


@pytest.fixture
def getConfig():
    r"""!Build a config object and fill it with the config data"""
    config = ConfigYAML()
    assert config.loadConfigFile(paths.TEST_PATH + "test_config.yaml") is True
    return config


@pytest.fixture
def makeTelegram(getConfig, fakeTelegramApi):
    r"""!Build a telegram plugin with the test config and remove it after the test"""
    telegram = Telegram(getConfig.get("telegram_test"))
    yield telegram
    telegram._cleanup()


@pytest.fixture
def makeSender(fakeTelegramApi):
    r"""!Build a telegram sender and shut it down after the test"""
    sender = TelegramSender("testToken", [111])
    yield sender
    sender.shutdown()


def waitForRequests(sentRequests, count, timeout=5):
    r"""!Wait until the given number of requests was sent
    @return True or False if the timeout is reached"""
    endTime = time.time() + timeout
    while len(sentRequests) < count:
        if time.time() > endTime:
            return False
        time.sleep(0.01)
    return True


def buildPacket(mode, fields=None):
    r"""!Build a BW Packet object with the given mode and fields"""
    packet = Packet()
    packet.set("mode", mode)
    for fieldName, value in (fields or {}).items():
        packet.set(fieldName, value)
    return packet


def isValidMarkdown(text):
    r"""!Check that every MarkdownV2 special character is escaped with a backslash"""
    escaped = False
    for char in text:
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char in MARKDOWN_SPECIAL_CHARS:
            return False
    return not escaped


def test_escapeTextEmpty():
    r"""!An empty text stays empty"""
    assert TelegramSender._escape_text("", "HTML") == ""
    assert TelegramSender._escape_text(None, "HTML") == ""


def test_escapeTextWithoutParseMode():
    r"""!Without parse mode the text is not changed"""
    assert TelegramSender._escape_text("<b>Brand</b> & *Rauch*", None) == "<b>Brand</b> & *Rauch*"


def test_escapeTextHtmlAllowedTags():
    r"""!Allowed HTML tags are kept - special characters are escaped"""
    text = TelegramSender._escape_text("<b>Brand</b> & <i>Rauch</i>", "HTML")
    assert text == "<b>Brand</b> &amp; <i>Rauch</i>"


def test_escapeTextHtmlNotAllowedTags():
    r"""!Not allowed HTML tags and lonely brackets are escaped"""
    text = TelegramSender._escape_text("<script>1 < 2</script>", "HTML")
    assert text == "&lt;script&gt;1 &lt; 2&lt;/script&gt;"


def test_escapeTextMarkdown():
    r"""!All MarkdownV2 special characters are escaped"""
    text = TelegramSender._escape_text("Brand_1 *B3* (Wohnhaus) 1.OG!", "MarkdownV2")
    assert text == r"Brand\_1 \*B3\* \(Wohnhaus\) 1\.OG\!"
    assert isValidMarkdown(text)


def test_escapeTextShortenLongText():
    r"""!A text longer than the telegram limit is shortened"""
    text = TelegramSender._escape_text("a" * 5000, None)
    assert len(text) <= 4096
    assert text.startswith("a" * 4000)


def test_escapeTextShortenLongTextMarkdown():
    r"""!A shortened MarkdownV2 text is still valid MarkdownV2"""
    text = TelegramSender._escape_text("a" * 5000, "MarkdownV2")
    assert len(text) <= 4096
    assert isValidMarkdown(text)


def test_escapeTextShortenLongTextHtml():
    r"""!A shortened HTML text does not end with a cut HTML entity"""
    text = TelegramSender._escape_text("x" + "&" * 2000, "HTML")
    assert len(text) <= 4096
    assert not re.search(r"&(?!amp;|lt;|gt;)", text)


def test_senderMessageToAllChats(fakeTelegramApi):
    r"""!A message is sent to all chat ids"""
    sender = TelegramSender("testToken", [111, 222])
    sender.send_message("Test")
    assert waitForRequests(fakeTelegramApi, 2)
    sender.shutdown()
    assert sorted(data["chat_id"] for url, data in fakeTelegramApi) == [111, 222]
    assert all(url == "https://api.telegram.org/bottestToken/sendMessage" for url, data in fakeTelegramApi)
    assert all(data["text"] == "Test" for url, data in fakeTelegramApi)


def test_senderParseMode(fakeTelegramApi):
    r"""!The parse mode is sent with the message"""
    sender = TelegramSender("testToken", [111], parse_mode="HTML")
    sender.send_message("<b>Test</b>")
    assert waitForRequests(fakeTelegramApi, 1)
    sender.shutdown()
    assert fakeTelegramApi[0][1] == {"chat_id": 111, "text": "<b>Test</b>", "parse_mode": "HTML"}


def test_senderLocation(makeSender, fakeTelegramApi):
    r"""!A valid location is sent as location"""
    makeSender.send_location("48.1374", "11.5755")
    assert waitForRequests(fakeTelegramApi, 1)
    assert fakeTelegramApi[0] == ("https://api.telegram.org/bottestToken/sendLocation",
                                  {"chat_id": 111, "latitude": 48.1374, "longitude": 11.5755})


def test_senderLocationInvalid(makeSender, fakeTelegramApi):
    r"""!Invalid locations are not sent"""
    makeSender.send_location("91", "11.5")
    makeSender.send_location("48.1", "-181")
    makeSender.send_location("abc", "11.5")
    makeSender.send_location(None, "11.5")
    makeSender.send_message("marker")
    assert waitForRequests(fakeTelegramApi, 1)
    time.sleep(0.1)
    assert [data.get("text") for url, data in fakeTelegramApi] == ["marker"]


def test_pluginFms(makeTelegram, fakeTelegramApi):
    r"""!Send a FMS alarm with the configured message"""
    makeTelegram._run(buildPacket("fms", {"fms": "93377141"}))
    assert waitForRequests(fakeTelegramApi, 2)
    assert [data["text"] for url, data in fakeTelegramApi] == ["FMS 93377141", "FMS 93377141"]


def test_pluginPocsagDefaultMessage(getConfig, fakeTelegramApi):
    r"""!Send a POCSAG alarm with the default message"""
    telegram = Telegram(getConfig.get("telegram_default"))
    telegram._run(buildPacket("pocsag", {"ric": "1234567", "subric": "1", "message": "Brand"}))
    assert waitForRequests(fakeTelegramApi, 1)
    telegram._cleanup()
    assert fakeTelegramApi[0][1]["text"] == "1234567(1)\nBrand"


def test_pluginZvei(makeTelegram, fakeTelegramApi):
    r"""!Send a ZVEI alarm with the configured message"""
    makeTelegram._run(buildPacket("zvei", {"tone": "12345"}))
    assert waitForRequests(fakeTelegramApi, 2)
    assert fakeTelegramApi[0][1]["text"] == "ZVEI 12345"


def test_pluginMsg(makeTelegram, fakeTelegramApi):
    r"""!Send a MSG packet with the configured message"""
    makeTelegram._run(buildPacket("msg", {"message": "Test"}))
    assert waitForRequests(fakeTelegramApi, 2)
    assert fakeTelegramApi[0][1]["text"] == "MSG Test"


def test_pluginHtmlMessage(getConfig, fakeTelegramApi):
    r"""!Formatting of the message template is kept - the content of the wildcards is escaped"""
    telegram = Telegram(getConfig.get("telegram_html"))
    telegram._run(buildPacket("pocsag", {"ric": "1234567", "message": "Brand & Rauch"}))
    assert waitForRequests(fakeTelegramApi, 1)
    telegram._cleanup()
    assert fakeTelegramApi[0][1]["text"] == "<b>1234567</b> Brand &amp; Rauch"


def test_pluginCoordinates(makeTelegram, fakeTelegramApi):
    r"""!With enabled coordinates a POCSAG alarm with lat and lon also sends the location"""
    makeTelegram._run(buildPacket("pocsag", {"ric": "1234567", "message": "Brand", "lat": "48.1374", "lon": "11.5755"}))
    assert waitForRequests(fakeTelegramApi, 4)
    sentMethods = sorted(url.rsplit("/", 1)[1] for url, data in fakeTelegramApi)
    assert sentMethods == ["sendLocation", "sendLocation", "sendMessage", "sendMessage"]


def test_pluginStartupMessage(getConfig, fakeTelegramApi):
    r"""!The startup message is sent while loading the plugin"""
    telegram = Telegram(getConfig.get("telegram_startup"))
    assert waitForRequests(fakeTelegramApi, 1)
    telegram._cleanup()
    assert fakeTelegramApi[0][1]["text"] == "Server up and running!"


def test_pluginMissingConfig(getConfig, fakeTelegramApi):
    r"""!Without botToken or chatIds no message is sent and no alarm error is counted"""
    for section in ["telegram_missingToken", "telegram_missingChatIds"]:
        telegram = Telegram(getConfig.get(section))
        telegram._run(buildPacket("fms", {"fms": "93377141"}))
        telegram._cleanup()
        assert telegram._getStatistics()["alarmErrorCount"] == 0
    time.sleep(0.1)
    assert fakeTelegramApi == []


def test_workerRetryServerError(scriptedTelegramApi):
    r"""!A server error is retried until the message is sent"""
    sentRequests, script = scriptedTelegramApi
    script.extend([FakeResponse(500), FakeResponse(502)])
    sender = TelegramSender("testToken", [111], initial_delay=0.01)
    sender.send_message("Test")
    assert waitForRequests(sentRequests, 3)
    sender.shutdown()
    assert [data["text"] for sendTime, data in sentRequests] == ["Test", "Test", "Test"]


def test_workerRetryNetworkError(scriptedTelegramApi):
    r"""!A network error is retried until the message is sent"""
    sentRequests, script = scriptedTelegramApi
    script.append(requests.ConnectionError("no network"))
    sender = TelegramSender("testToken", [111], initial_delay=0.01)
    sender.send_message("Test")
    assert waitForRequests(sentRequests, 2)
    sender.shutdown()


def test_workerPermanentError(scriptedTelegramApi):
    r"""!A client error (e.g. wrong token or chat id) is not retried"""
    sentRequests, script = scriptedTelegramApi
    script.append(FakeResponse(400))
    sender = TelegramSender("testToken", [111], initial_delay=0.01)
    sender.send_message("Test")
    sender.send_message("marker")
    assert waitForRequests(sentRequests, 2)
    time.sleep(0.1)
    sender.shutdown()
    assert [data["text"] for sendTime, data in sentRequests] == ["Test", "marker"]


def test_workerMaxRetries(scriptedTelegramApi):
    r"""!A message is discarded after max_retries failed retries"""
    sentRequests, script = scriptedTelegramApi
    script.extend([FakeResponse(500)] * 10)
    sender = TelegramSender("testToken", [111], max_retries=2, initial_delay=0.01)
    sender.send_message("Test")
    assert waitForRequests(sentRequests, 3)
    time.sleep(0.2)
    sender.shutdown()
    assert len(sentRequests) == 3


def test_workerBackoff(scriptedTelegramApi):
    r"""!The waiting time between the retries is doubled"""
    sentRequests, script = scriptedTelegramApi
    script.extend([FakeResponse(500)] * 3)
    sender = TelegramSender("testToken", [111], initial_delay=0.1)
    sender.send_message("Test")
    assert waitForRequests(sentRequests, 4)
    sender.shutdown()
    sendTimes = [sendTime for sendTime, data in sentRequests]
    assert sendTimes[1] - sendTimes[0] >= 0.1
    assert sendTimes[2] - sendTimes[1] >= 0.2
    assert sendTimes[3] - sendTimes[2] >= 0.4


def test_workerRateLimit(scriptedTelegramApi):
    r"""!With a rate limit the waiting time of the telegram api is used instead of the backoff"""
    sentRequests, script = scriptedTelegramApi
    script.append(FakeResponse(429, retryAfter=0.2))
    sender = TelegramSender("testToken", [111], initial_delay=30)
    sender.send_message("Test")
    assert waitForRequests(sentRequests, 2, timeout=10)
    sender.shutdown()
    assert sentRequests[1][0] - sentRequests[0][0] >= 0.2


def test_workerQueueFull(scriptedTelegramApi, monkeypatch):
    r"""!If the queue is full new messages are discarded"""
    sentRequests, script = scriptedTelegramApi
    releaseApi = threading.Event()
    fakePost = requests.post

    def blockingPost(url, data=None, timeout=None):
        releaseApi.wait(5)  # the worker hangs on the first message until the queue is full
        return fakePost(url, data, timeout)

    monkeypatch.setattr(requests, "post", blockingPost)
    sender = TelegramSender("testToken", [111])
    sender.send_message("first")
    while not sender.msg_queue.empty():
        time.sleep(0.01)  # wait until the worker took the first message
    for number in range(101):
        sender.send_message(str(number))
    assert sender.msg_queue.full()
    releaseApi.set()
    assert waitForRequests(sentRequests, 101)
    time.sleep(0.1)
    sender.shutdown()
    assert len(sentRequests) == 101
    assert sentRequests[-1][1]["text"] == "99"


def test_workerShutdownSendsQueue(scriptedTelegramApi, monkeypatch):
    r"""!Messages which are still in the queue are sent while shutting down"""
    sentRequests, script = scriptedTelegramApi
    fakePost = requests.post

    def slowPost(url, data=None, timeout=None):
        time.sleep(0.1)  # slow api - the messages are still in the queue on shutdown
        return fakePost(url, data, timeout)

    monkeypatch.setattr(requests, "post", slowPost)
    sender = TelegramSender("testToken", [111])
    for text in ["first", "second", "third"]:
        sender.send_message(text)
    sender.shutdown()
    assert [data["text"] for sendTime, data in sentRequests] == ["first", "second", "third"]
