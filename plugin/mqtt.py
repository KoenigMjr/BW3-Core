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

@file:        mqtt.py
@date:        09.10.2026
@author:      Claus Schichl
@description: MQTT plugin - publishes alarms as JSON to an MQTT broker
"""
import logging
import json
import socket
import time
import queue
import threading
import datetime
import collections
from plugin.pluginBase import PluginBase
import paho.mqtt.client as mqtt

logging.debug("- %s loaded", __name__)


# ===========================
# MqttSender-Class
# ===========================

# Outcomes of MqttSender._deliver_once()
_DELIVERED = "delivered"          # the MQTT client owns the message now - never send it again
_NOT_CONNECTED = "not_connected"  # not handed over, nothing was sent - wait for the connection
_REJECTED = "rejected"            # not handed over (e.g. client queue full) - counts as a failed attempt
_INVALID = "invalid"              # can never be sent (e.g. invalid topic) - discard right away


class MqttSender:
    r"""!Encapsulates the connection and delivery to an MQTT broker.

    Every message is handed off to an internal queue and processed by a
    dedicated worker thread (analogous to TelegramSender in telegram.py).
    If the broker is currently unreachable, messages simply stay in the
    queue and are delivered, in order, once the connection is restored.
    If the queue is full, the OLDEST message is dropped so that new alarms
    are not blocked - this is logged explicitly.

    Core rule: every message has exactly ONE owner at any time.
    As long as the plugin owns it, it may be sent again. As soon as paho
    has accepted it (QoS >= 1: stored in paho's outgoing queue), paho owns
    it and retransmits it by itself after a reconnect. The plugin must
    NEVER publish such a message a second time, otherwise the broker
    distributes every copy as a new message (duplicate alarms)."""

    # pause between two attempts while the connection flag is set but paho reports NO_CONN
    _POLL = 0.2

    def __init__(self, broker_address, broker_port, client_id, username=None, password=None,
                 keepalive=60, qos=0, retain=False, status_topic=None,
                 queue_size=200, max_retries=5, initial_delay=2, max_delay=60,
                 confirm_timeout=5, client_factory=None, autostart=True):
        r"""!Creates the sender.

        @param client_factory: optional callable(client_id) returning an MQTT client (used by tests)
        @param autostart: start worker thread and connect (False for tests)"""
        self._stop_event = threading.Event()
        self._connected_event = threading.Event()
        self._lock = threading.Lock()
        self._worker_lock = threading.Lock()
        self._worker = None
        self._pending = 0  # messages not yet finished (queued + the one in hand)
        self._unconfirmed = collections.deque(maxlen=1000)  # QoS >= 1 messages paho still has to get confirmed

        self.broker_address = broker_address
        self.broker_port = broker_port
        self.keepalive = keepalive
        self.qos = qos
        self.retain = retain
        self.status_topic = status_topic
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.confirm_timeout = confirm_timeout

        self._msg_queue = queue.Queue(maxsize=queue_size)

        if client_factory is None:
            def client_factory(cid):
                return mqtt.Client(client_id=cid, callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.client = client_factory(client_id)

        if username:
            self.client.username_pw_set(username, password)

        # Last Will: published by the broker itself if the connection drops
        # ungracefully (e.g. host crash) - must be set before connect().
        if self.status_topic:
            self.client.will_set(self.status_topic, payload="offline", qos=1, retain=True)

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

        # built-in reconnect mechanism of paho with exponential backoff
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)

        # safety net: paho keeps accepted QoS >= 1 messages until the broker confirms them.
        # The plugin only hands messages over while connected, so this limit is normally never reached.
        self.client.max_queued_messages_set(queue_size)

        if autostart:
            self.start()

    def start(self):
        r"""!Starts the worker thread and connects to the broker"""
        self.ensure_worker()
        self._connect()

    def ensure_worker(self):
        r"""!Restarts ONLY the worker thread if it died (self-healing).

        Client, clientId and queue are kept. Creating a second client with the
        same clientId would make the broker kick out the old one, which
        causes endless reconnects and retransmissions."""
        with self._worker_lock:
            if self._stop_event.is_set():
                return
            if self._worker is not None and self._worker.is_alive():
                return
            if self._worker is not None:
                logging.error("MQTT Plugin: worker thread died - restarting it (client and buffered messages are kept)")
            self._worker = threading.Thread(target=self._worker_loop, daemon=True, name="mqtt-sender")
            self._worker.start()

    def enqueue(self, topic, json_payload):
        r"""!Buffers a message for delivery.

        @param topic: MQTT topic
        @param json_payload: already serialized JSON string"""
        with self._lock:
            try:
                self._msg_queue.put_nowait((topic, json_payload))
            except queue.Full:
                try:
                    dropped_topic, _ = self._msg_queue.get_nowait()
                    self._pending -= 1
                    logging.warning("MQTT Plugin: buffer full (max %d) - dropping oldest buffered message (topic '%s') in favor of the new one",
                                    self._msg_queue.maxsize, dropped_topic)
                except queue.Empty:
                    pass  # the worker took one in the meantime, there is room again
                self._msg_queue.put_nowait((topic, json_payload))
            self._pending += 1

    def shutdown(self):
        r"""!Graceful shutdown: drain the queue, wait for open confirmations, go offline, disconnect"""
        logging.info("MQTT Plugin: shutting down connection...")

        # 1. give the worker time to deliver what is still buffered (only possible while connected)
        if self._connected_event.is_set():
            deadline = time.time() + 5
            while self._pending > 0 and time.time() < deadline:
                time.sleep(0.1)

        remaining = self._pending
        if remaining > 0:
            logging.warning("MQTT Plugin: %d unsent messages discarded during shutdown", remaining)

        self._stop_event.set()
        if self._worker is not None:
            self._worker.join(timeout=5)

        # 2. messages paho already accepted but the broker has not confirmed yet
        if self._connected_event.is_set():
            open_count = self._wait_unconfirmed(timeout=2)
            if open_count > 0:
                logging.warning("MQTT Plugin: %d message(s) still unconfirmed by the broker at shutdown", open_count)

        # 3. a clean DISCONNECT suppresses the Last Will, so announce "offline" ourselves
        if self.status_topic and self._connected_event.is_set():
            try:
                info = self.client.publish(self.status_topic, payload="offline", qos=1, retain=True)
                info.wait_for_publish(timeout=2)
            except Exception:
                pass

        # 4. documented order of paho: disconnect() first, then loop_stop()
        try:
            self.client.disconnect()
            self.client.loop_stop()
        except Exception:
            pass
        logging.debug("MQTT Plugin: connection closed")

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #

    def _connect(self):
        r"""!Establishes the connection to the broker asynchronously and starts the network thread"""
        try:
            self.client.connect_async(self.broker_address, self.broker_port, keepalive=self.keepalive)
            self.client.loop_start()
        except Exception as e:
            logging.error("MQTT Plugin: failed to connect to %s:%d: %s", self.broker_address, self.broker_port, e)

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        r"""!paho-mqtt callback on (re-)connect"""
        rc = getattr(reason_code, "value", reason_code)
        if rc == 0:
            logging.info("MQTT Plugin: connected to %s:%d", self.broker_address, self.broker_port)
            self._connected_event.set()
            if self.status_topic:
                client.publish(self.status_topic, payload="online", qos=1, retain=True)
        else:
            logging.error("MQTT Plugin: connection refused (reason_code=%s)", reason_code)
            self._connected_event.clear()

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties=None):
        r"""!paho-mqtt callback on disconnect"""
        self._connected_event.clear()
        rc = getattr(reason_code, "value", reason_code)
        if self._stop_event.is_set() or rc == 0:
            logging.debug("MQTT Plugin: disconnected")
        else:
            logging.warning("MQTT Plugin: connection lost (reason_code=%s) - new messages are buffered until the connection is back; "
                            "messages already accepted by the MQTT client are retransmitted by it after the reconnect", reason_code)

    def _track(self, info):
        r"""!Remembers a QoS >= 1 message that paho still has to get confirmed"""
        self._unconfirmed.append(info)

    def _wait_unconfirmed(self, timeout):
        r"""!Waits (bounded) for open confirmations.

        @return number of messages that are still unconfirmed"""
        deadline = time.time() + timeout
        open_count = 0
        for info in list(self._unconfirmed):
            if self._is_published(info):
                continue
            try:
                info.wait_for_publish(timeout=max(0.0, deadline - time.time()))
            except Exception:
                pass
            if not self._is_published(info):
                open_count += 1
        return open_count

    @staticmethod
    def _is_published(info):
        try:
            return bool(info.is_published())
        except (ValueError, RuntimeError):
            return False

    def _deliver_once(self, topic, json_payload):
        r"""!One delivery attempt - decides who owns the message afterwards.

        @return tuple (outcome, detail)"""
        if not self._connected_event.is_set():
            return _NOT_CONNECTED, "not connected"

        try:
            info = self.client.publish(topic, json_payload, qos=self.qos, retain=self.retain)
        except ValueError as e:  # e.g. invalid topic or QoS - retrying can never help
            return _INVALID, str(e)
        except Exception as e:
            return _REJECTED, str(e)

        rc = info.rc
        mid = getattr(info, "mid", None)

        if rc == mqtt.MQTT_ERR_NO_CONN:
            if self.qos >= 1:
                # The connection dropped between our check and publish(). paho has already stored the
                # message and sends it after the reconnect -> publishing it again would create a duplicate.
                self._track(info)
                logging.info("MQTT Plugin: connection dropped while sending to topic '%s' (MID=%s) - message was accepted by the MQTT client "
                             "and is sent after the reconnect; NOT sending it again", topic, mid)
                return _DELIVERED, "accepted while disconnected"
            # QoS 0 is not stored by paho, nothing was sent - the plugin still owns the message
            return _NOT_CONNECTED, "connection dropped, QoS 0 message was not stored by the MQTT client"

        if rc != mqtt.MQTT_ERR_SUCCESS:  # e.g. QUEUE_SIZE - paho did not accept the message
            return _REJECTED, "publish() returned '%s'" % mqtt.error_string(rc)

        # paho accepted the message
        try:
            info.wait_for_publish(timeout=self.confirm_timeout)
        except (ValueError, RuntimeError) as e:
            if self.qos == 0:
                # paho marks QoS 0 packets that were not written yet as lost on reconnect - nobody owns it anymore
                return _REJECTED, "QoS 0 packet lost before it was written (%s)" % e
            # QoS >= 1 stays stored in paho
            self._track(info)
            return _DELIVERED, "accepted"

        if self._is_published(info):
            logging.debug("MQTT Plugin: message published on topic '%s' (MID=%s, QoS=%d)", topic, mid, self.qos)
        elif self.qos >= 1:
            self._track(info)
            logging.warning("MQTT Plugin: no confirmation within %ds for topic '%s' (MID=%s) - message stays with the MQTT client, "
                            "which retransmits it itself; NOT sending it again", self.confirm_timeout, topic, mid)
        else:
            logging.warning("MQTT Plugin: QoS 0 message for topic '%s' not yet written after %ds (QoS 0 gives no delivery guarantee)",
                            topic, self.confirm_timeout)
        return _DELIVERED, "accepted"

    def _process(self, topic, json_payload):
        r"""!Delivers ONE message and does not return before it is delivered or discarded.

        The message is kept in hand the whole time (instead of being put back at the end
        of the queue), so the order of alarms is preserved during an outage."""
        failures = 0
        delay = self.initial_delay

        while not self._stop_event.is_set():
            outcome, detail = self._deliver_once(topic, json_payload)

            if outcome == _DELIVERED:
                return

            if outcome == _INVALID:
                logging.error("MQTT Plugin: message for topic '%s' cannot be sent and is discarded: %s", topic, detail)
                return

            if outcome == _NOT_CONNECTED:
                # nothing was sent, so this is no failed attempt and does not count against max_retries
                logging.debug("MQTT Plugin: not connected - message for topic '%s' stays buffered", topic)
                if self._connected_event.is_set():
                    self._stop_event.wait(self._POLL)  # flag not yet cleared by on_disconnect
                else:
                    self._connected_event.wait(1)  # wakes up immediately when the connection is back
                continue

            # _REJECTED: the MQTT client did not take the message, so the plugin may try again
            failures += 1
            if failures > self.max_retries:
                logging.error("MQTT Plugin: message for topic '%s' permanently discarded after %d attempts: %s", topic, failures, detail)
                return
            logging.warning("MQTT Plugin: delivery attempt %d for topic '%s' rejected (%s) - retrying in %ds", failures, topic, detail, delay)
            self._stop_event.wait(delay)
            delay = min(delay * 2, self.max_delay)

        logging.warning("MQTT Plugin: message for topic '%s' discarded during shutdown", topic)

    def _worker_loop(self):
        r"""!Takes messages from the queue one by one and delivers them in order"""
        while not self._stop_event.is_set():
            try:
                topic, json_payload = self._msg_queue.get(timeout=1)
            except queue.Empty:
                continue
            try:
                self._process(topic, json_payload)
            except Exception as e:  # the worker must never die because of a single message
                logging.error("MQTT Plugin: unexpected error, message for topic '%s' discarded: %s", topic, e)
                logging.debug("MQTT Plugin: unexpected error", exc_info=True)
            finally:
                with self._lock:
                    self._pending -= 1


# ===========================
# BoswatchPlugin-Class
# ===========================

class BoswatchPlugin(PluginBase):
    r"""!Publishes BOSWatch alarms as JSON payload via MQTT"""

    def __init__(self, config):
        r"""!Do not change anything here!"""
        super().__init__(__name__, config)  # you can access the config class on 'self.config'

    def onLoad(self):
        r"""!Called by import of the plugin"""
        self.brokerAddress = self.config.get("brokerAddress")
        self.brokerPort = int(self.config.get("brokerPort", default=1883))
        self.topicTemplate = self.config.get("topic", default="boswatch/alarm")
        # must be unique per broker connection - two clients with the same id kick each other out
        self.clientId = self.config.get("clientId", default="boswatch-" + socket.gethostname())
        self.username = self.config.get("username", default=None)
        self.password = self.config.get("password", default=None)
        self.qos = int(self.config.get("qos", default=0))
        self.retain = bool(self.config.get("retain", default=False))
        self.keepalive = int(self.config.get("keepalive", default=60))
        self.statusTopic = self.config.get("statusTopic", default=None)
        self.queueSize = int(self.config.get("queueSize", default=200))
        self.maxRetries = int(self.config.get("maxRetries", default=5))
        self.initialDelay = int(self.config.get("initialDelay", default=2))
        self.maxDelay = int(self.config.get("maxDelay", default=60))

        if self.qos not in (0, 1, 2):
            logging.warning("MQTT Plugin: invalid qos value '%s' - using 0", self.qos)
            self.qos = 0

        self.sender = None
        if not self.brokerAddress:
            logging.error("MQTT Plugin: 'brokerAddress' not configured - plugin will not send messages.")
            return
        self._ensure_sender()

    def setup(self):
        r"""!Called before alarm - self-healing: restarts a dead worker or creates a missing sender"""
        self._ensure_sender()

    def fms(self, bwPacket):
        r"""!Called on FMS alarm

        @param bwPacket: bwPacket instance
        Remove if not implemented"""
        self._publish(bwPacket)

    def pocsag(self, bwPacket):
        r"""!Called on POCSAG alarm

        @param bwPacket: bwPacket instance
        Remove if not implemented"""
        self._publish(bwPacket)

    def zvei(self, bwPacket):
        r"""!Called on ZVEI alarm

        @param bwPacket: bwPacket instance
        Remove if not implemented"""
        self._publish(bwPacket)

    def msg(self, bwPacket):
        r"""!Called on MSG packet

        @param bwPacket: bwPacket instance
        Remove if not implemented"""
        self._publish(bwPacket)

    def onUnload(self):
        r"""!Called by destruction of the plugin"""
        if self.sender is not None:
            self.sender.shutdown()

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #

    def _ensure_sender(self):
        r"""!Ensures that a working MqttSender exists (self-healing, analogous to telegram.py).

        An existing sender is never replaced: a second client with the same
        clientId would be kicked out by / would kick out the first one. If only
        the worker thread died, only the worker is restarted."""
        if self.sender is not None:
            self.sender.ensure_worker()
            return

        if not self.brokerAddress:
            return

        try:
            self.sender = MqttSender(
                broker_address=self.brokerAddress,
                broker_port=self.brokerPort,
                client_id=self.clientId,
                username=self.username,
                password=self.password,
                keepalive=self.keepalive,
                qos=self.qos,
                retain=self.retain,
                status_topic=self.statusTopic,
                queue_size=self.queueSize,
                max_retries=self.maxRetries,
                initial_delay=self.initialDelay,
                max_delay=self.maxDelay
            )
            logging.debug("MQTT Plugin: MqttSender initialized")
        except Exception as e:
            logging.error("MQTT Plugin: sender could not be initialized: %s", e)
            self.sender = None

    def _publish(self, bwPacket):
        r"""!Serializes the complete bwPacket to JSON and enqueues it with the sender

        @param bwPacket: bwPacket instance"""
        if self.sender is None:
            logging.warning("MQTT Plugin not configured - packet dropped")
            return

        payload = self._packet_to_dict(bwPacket)
        topic = self.parseWildcards(self.topicTemplate)

        try:
            json_payload = json.dumps(payload, default=self._json_serializer, ensure_ascii=False)
        except Exception as e:
            logging.error("MQTT Plugin: error during JSON serialization: %s", e)
            return

        self.sender.enqueue(topic, json_payload)

    @staticmethod
    def _json_serializer(obj):
        r"""!Fail-safe JSON serializer for non-primitive data types.

        Packet.set() currently only ever stores strings, but this fallback
        defensively covers the case that a future module (e.g. a custom
        extension) writes an exotic object into a field - so a single
        unexpected data type cannot crash the whole plugin.

        @param obj: the object to serialize
        @return: JSON-compatible representation"""
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()
        if isinstance(obj, bytes):
            return obj.decode("utf-8", errors="replace")
        if isinstance(obj, set):
            return list(obj)
        try:
            return str(obj)
        except Exception:
            return repr(obj)

    @staticmethod
    def _packet_to_dict(bwPacket):
        r"""!Extracts the complete content of the bwPacket object as a dict.

        Analogous to the approach in module/packetDump.py: instead of
        picking individual fields, the entire internal state of the packet
        is taken over, so fields added by other modules (Descriptor,
        Multicast, Geocoding, ...) automatically end up in the MQTT payload.

        @param bwPacket: bwPacket instance
        @return: dict with all fields of the packet"""
        if hasattr(bwPacket, '_packet'):
            return bwPacket._packet.copy()
        try:
            return {k: v for k, v in bwPacket.__dict__.items() if not k.startswith('_')}
        except Exception as e:
            logging.warning("MQTT Plugin: could not read packet fields: %s", e)
            return {}
