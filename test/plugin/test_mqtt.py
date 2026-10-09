#!/usr/bin/python
# -*- coding: utf-8 -*-
r"""!
Tests for plugin/mqtt.py - no broker needed.

The delivery logic is tested with a fake MQTT client. One additional test
pins the behaviour of the real paho-mqtt library on which the duplicate fix
relies (QoS >= 1 messages are kept by paho on NO_CONN, QoS 0 are not).
"""
import logging
import threading
import time
from unittest import mock

import paho.mqtt.client as mqtt

from plugin import mqtt as plugin_mqtt
from plugin.mqtt import MqttSender, BoswatchPlugin


# ------------------------------------------------------------------ #
# helpers
# ------------------------------------------------------------------ #

class FakeInfo:
    r"""!Stand-in for paho's MQTTMessageInfo"""

    def __init__(self, rc=mqtt.MQTT_ERR_SUCCESS, mid=1, published=True, wait_exc=None):
        self.rc = rc
        self.mid = mid
        self._published = published
        self._wait_exc = wait_exc

    def wait_for_publish(self, timeout=None):
        if self._wait_exc is not None:
            raise self._wait_exc

    def is_published(self):
        return self._published


class FakeClient:
    r"""!Stand-in for paho.mqtt.client.Client - records everything"""

    def __init__(self):
        self.results = []  # queued results for publish(): FakeInfo or an Exception to raise
        self.calls = []    # (topic, payload, qos, retain)
        self.events = []   # ordered list of ("publish", topic) / ("disconnect",) / ("loop_stop",)
        self.will = None
        self.max_queued = None

    def username_pw_set(self, *a, **k):
        pass

    def will_set(self, *a, **k):
        self.will = (a, k)

    def reconnect_delay_set(self, *a, **k):
        pass

    def max_queued_messages_set(self, n):
        self.max_queued = n

    def connect_async(self, *a, **k):
        pass

    def loop_start(self):
        pass

    def loop_stop(self):
        self.events.append(("loop_stop",))

    def disconnect(self):
        self.events.append(("disconnect",))

    def publish(self, topic, payload=None, qos=0, retain=False):
        self.calls.append((topic, payload, qos, retain))
        self.events.append(("publish", topic))
        if self.results:
            res = self.results.pop(0)
            if isinstance(res, Exception):
                raise res
            return res
        return FakeInfo(mid=len(self.calls))


def make_sender(qos=1, fake=None, **kwargs):
    fake = fake or FakeClient()
    params = dict(qos=qos, initial_delay=0, max_delay=0, max_retries=3, client_factory=lambda cid: fake, autostart=False)
    params.update(kwargs)
    sender = MqttSender("broker", 1883, "cid", **params)
    sender._POLL = 0
    return sender, fake


def wait_until(condition, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return condition()


# ------------------------------------------------------------------ #
# the duplicate bug: paho owns an accepted message, the plugin must not publish it again
# ------------------------------------------------------------------ #

def test_missing_confirmation_does_not_publish_again(caplog):
    sender, fake = make_sender(qos=1)
    sender._connected_event.set()
    fake.results = [FakeInfo(published=False, mid=7)]  # accepted, but no PUBACK within the timeout

    with caplog.at_level(logging.DEBUG):
        sender._process("t/1", "{}")

    assert len(fake.calls) == 1
    assert "NOT sending it again" in caplog.text
    assert "retransmits it itself" in caplog.text
    assert "MID=7" in caplog.text
    assert len(sender._unconfirmed) == 1


def test_qos1_no_conn_does_not_publish_again(caplog):
    sender, fake = make_sender(qos=1)
    sender._connected_event.set()
    fake.results = [FakeInfo(rc=mqtt.MQTT_ERR_NO_CONN, mid=9)]  # paho already stored it

    with caplog.at_level(logging.INFO):
        sender._process("t/1", "{}")

    assert len(fake.calls) == 1
    assert "accepted by the MQTT client" in caplog.text
    assert "NOT sending it again" in caplog.text
    assert len(sender._unconfirmed) == 1


def test_qos2_no_conn_does_not_publish_again():
    sender, fake = make_sender(qos=2)
    sender._connected_event.set()
    fake.results = [FakeInfo(rc=mqtt.MQTT_ERR_NO_CONN)]

    sender._process("t/1", "{}")

    assert len(fake.calls) == 1


# ------------------------------------------------------------------ #
# real rejections stay with the plugin and are repeated
# ------------------------------------------------------------------ #

def test_qos0_no_conn_is_retried_and_costs_no_attempt():
    sender, fake = make_sender(qos=0, max_retries=1)
    sender._connected_event.set()
    # more NO_CONN answers than max_retries - must still be delivered, nothing was consumed
    fake.results = [FakeInfo(rc=mqtt.MQTT_ERR_NO_CONN)] * 4 + [FakeInfo()]

    sender._process("t/1", "{}")

    assert len(fake.calls) == 5


def test_queue_size_is_retried_then_delivered(caplog):
    sender, fake = make_sender(qos=1)
    sender._connected_event.set()
    fake.results = [FakeInfo(rc=mqtt.MQTT_ERR_QUEUE_SIZE), FakeInfo(rc=mqtt.MQTT_ERR_QUEUE_SIZE), FakeInfo()]

    with caplog.at_level(logging.WARNING):
        sender._process("t/1", "{}")

    assert len(fake.calls) == 3
    assert "delivery attempt 1" in caplog.text
    assert "delivery attempt 2" in caplog.text
    assert "QUEUE_SIZE" in caplog.text or "queue" in caplog.text.lower()


def test_other_error_code_is_retried():
    sender, fake = make_sender(qos=1)
    sender._connected_event.set()
    fake.results = [FakeInfo(rc=mqtt.MQTT_ERR_PROTOCOL), FakeInfo()]

    sender._process("t/1", "{}")

    assert len(fake.calls) == 2


def test_qos0_lost_before_written_is_retried():
    sender, fake = make_sender(qos=0)
    sender._connected_event.set()
    fake.results = [FakeInfo(wait_exc=RuntimeError("Connection lost")), FakeInfo()]

    sender._process("t/1", "{}")

    assert len(fake.calls) == 2


def test_discard_after_max_retries(caplog):
    sender, fake = make_sender(qos=1, max_retries=3)
    sender._connected_event.set()
    fake.results = [FakeInfo(rc=mqtt.MQTT_ERR_QUEUE_SIZE)] * 10

    with caplog.at_level(logging.WARNING):
        sender._process("t/1", "{}")

    assert len(fake.calls) == 4  # first attempt + 3 retries
    assert "permanently discarded after 4 attempts" in caplog.text


def test_invalid_topic_is_discarded_without_retry(caplog):
    sender, fake = make_sender(qos=1)
    sender._connected_event.set()
    fake.results = [ValueError("Invalid topic")]

    with caplog.at_level(logging.ERROR):
        sender._process("t/#", "{}")

    assert len(fake.calls) == 1
    assert "cannot be sent and is discarded" in caplog.text


def test_not_connected_sends_nothing():
    sender, fake = make_sender(qos=1)  # connection flag stays cleared
    outcome, _ = sender._deliver_once("t/1", "{}")

    assert outcome == plugin_mqtt._NOT_CONNECTED
    assert fake.calls == []


# ------------------------------------------------------------------ #
# queue behaviour
# ------------------------------------------------------------------ #

def test_order_is_preserved_during_an_outage():
    sender, fake = make_sender(qos=1)
    for i in range(3):
        sender.enqueue("t/%d" % i, "{}")
    sender.ensure_worker()
    time.sleep(0.3)  # worker is running but there is no connection
    assert fake.calls == []

    sender._connected_event.set()

    assert wait_until(lambda: len(fake.calls) == 3)
    assert [c[0] for c in fake.calls] == ["t/0", "t/1", "t/2"]
    sender._stop_event.set()


def test_drop_oldest_when_buffer_is_full(caplog):
    sender, _ = make_sender(qos=1, queue_size=2)

    with caplog.at_level(logging.WARNING):
        sender.enqueue("t/1", "{}")
        sender.enqueue("t/2", "{}")
        sender.enqueue("t/3", "{}")

    assert [sender._msg_queue.get_nowait()[0] for _ in range(2)] == ["t/2", "t/3"]
    assert sender._pending == 2
    assert "dropping oldest buffered message (topic 't/1')" in caplog.text


def test_shutdown_drains_queue_before_going_offline():
    sender, fake = make_sender(qos=1, status_topic="s/status")
    sender._connected_event.set()
    for i in range(3):
        sender.enqueue("t/%d" % i, "{}")
    sender.ensure_worker()

    sender.shutdown()

    published = [e[1] for e in fake.events if e[0] == "publish"]
    assert published == ["t/0", "t/1", "t/2", "s/status"]
    # documented paho order: disconnect() before loop_stop()
    assert fake.events[-2:] == [("disconnect",), ("loop_stop",)]


def test_shutdown_while_disconnected_reports_discarded_messages(caplog):
    sender, fake = make_sender(qos=1)
    sender.enqueue("t/1", "{}")

    with caplog.at_level(logging.WARNING):
        sender.shutdown()

    assert fake.calls == []
    assert "1 unsent messages discarded during shutdown" in caplog.text


def test_clean_disconnect_is_not_logged_as_connection_loss(caplog):
    sender, _ = make_sender()
    sender._stop_event.set()

    with caplog.at_level(logging.DEBUG):
        sender._on_disconnect(None, None, None, 0)

    assert "connection lost" not in caplog.text


def test_unexpected_disconnect_is_logged_honestly(caplog):
    sender, _ = make_sender()
    sender._connected_event.set()

    with caplog.at_level(logging.WARNING):
        sender._on_disconnect(None, None, None, 7)

    assert "connection lost" in caplog.text
    assert "retransmitted by it after the reconnect" in caplog.text
    assert not sender._connected_event.is_set()


# ------------------------------------------------------------------ #
# self-healing must never create a second client (same clientId)
# ------------------------------------------------------------------ #

def test_ensure_worker_restarts_only_the_worker():
    created = []

    def factory(cid):
        created.append(cid)
        return FakeClient()

    sender, _ = make_sender(client_factory=factory)
    sender.ensure_worker()
    old_client = sender.client
    sender._worker.join(0)

    dead = threading.Thread(target=lambda: None)
    dead.start()
    dead.join()
    sender._worker = dead  # simulate a crashed worker

    sender.ensure_worker()

    assert sender._worker is not dead and sender._worker.is_alive()
    assert sender.client is old_client
    assert created == ["cid"]  # exactly one client was ever created
    sender._stop_event.set()


def test_plugin_setup_reuses_existing_sender():
    plugin = object.__new__(BoswatchPlugin)
    plugin.brokerAddress = "broker"
    plugin.sender = mock.Mock()

    with mock.patch.object(plugin_mqtt, "MqttSender") as sender_class:
        plugin.setup()
        plugin.setup()

    sender_class.assert_not_called()
    assert plugin.sender.ensure_worker.call_count == 2


# ------------------------------------------------------------------ #
# pins the paho behaviour the fix relies on (needs no broker)
# ------------------------------------------------------------------ #

def test_paho_keeps_qos1_but_not_qos0_when_not_connected():
    client = mqtt.Client(client_id="t", callback_api_version=mqtt.CallbackAPIVersion.VERSION2)

    info1 = client.publish("t/1", "x", qos=1)
    info0 = client.publish("t/0", "x", qos=0)

    assert info1.rc == mqtt.MQTT_ERR_NO_CONN
    assert info0.rc == mqtt.MQTT_ERR_NO_CONN
    assert info1.mid in client._out_messages        # QoS 1: paho keeps it and sends it after the connect
    assert info0.mid not in client._out_messages    # QoS 0: gone - the plugin has to keep it
