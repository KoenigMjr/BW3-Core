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
@date:        02.09.2026
@author:      Claus Schichl
@description: MQTT plugin - publishes alarms as JSON to an MQTT broker
"""
import logging
import json
import time
import queue
import threading
import datetime
from plugin.pluginBase import PluginBase
import paho.mqtt.client as mqtt

logging.debug("- %s loaded", __name__)


# ===========================
# MqttSender-Class
# ===========================

class MqttSender:
    r"""!Encapsulates the connection and delivery to an MQTT broker.

    Every message is handed off to an internal queue and processed by a
    dedicated worker thread (analogous to TelegramSender in telegram.py).
    If the broker is currently unreachable, messages simply stay in the
    queue and are delivered once the connection is restored
    (zero-packet-loss within the bounds of the configured queue size).
    If the queue is full, the OLDEST message is dropped so that new alarms
    are not blocked - this is logged explicitly."""

    def __init__(self, broker_address, broker_port, client_id, username=None, password=None,
                 keepalive=60, qos=0, retain=False, status_topic=None,
                 queue_size=200, max_retries=5, initial_delay=2, max_delay=60):
        self._stop_event = threading.Event()

        self.broker_address = broker_address
        self.broker_port = broker_port
        self.keepalive = keepalive
        self.qos = qos
        self.retain = retain
        self.status_topic = status_topic
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay

        self._connected = False
        self._msg_queue = queue.Queue(maxsize=queue_size)

        self.client = mqtt.Client(
            client_id=client_id,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2
        )
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

        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

        self._connect()

    def enqueue(self, topic, json_payload):
        r"""!Buffers a message for delivery.

        @param topic: MQTT topic
        @param json_payload: already serialized JSON string"""
        try:
            self._msg_queue.put_nowait((topic, json_payload, 0))
        except queue.Full:
            try:
                dropped_topic, _, _ = self._msg_queue.get_nowait()
                self._msg_queue.put_nowait((topic, json_payload, 0))
                logging.warning("MQTT Plugin: buffer full (max %d) - dropping oldest buffered message (topic '%s') in favor of the new one",
                                self._msg_queue.maxsize, dropped_topic)
            except queue.Empty:  # pragma: no cover - race, practically unreachable
                logging.error("MQTT Plugin: message for topic '%s' discarded (buffer full)", topic)

    def is_alive(self):
        r"""!Checks whether the worker thread is still running.

        @return True or False"""
        return self._worker.is_alive()

    def shutdown(self):
        r"""!Graceful shutdown with queue drain (analogous to TelegramSender.shutdown)"""
        logging.info("MQTT Plugin: shutting down connection...")
        self._stop_event.set()

        timeout = time.time() + 5
        while not self._msg_queue.empty() and time.time() < timeout:
            time.sleep(0.1)

        remaining = self._msg_queue.qsize()
        if remaining > 0:
            logging.warning("MQTT Plugin: %d unsent messages discarded during shutdown", remaining)

        if self.status_topic and self._connected:
            try:
                info = self.client.publish(self.status_topic, payload="offline", qos=1, retain=True)
                info.wait_for_publish(timeout=2)
            except Exception:
                pass

        self._worker.join(timeout=5)
        try:
            self.client.loop_stop()
            self.client.disconnect()
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
            self._connected = True
            if self.status_topic:
                client.publish(self.status_topic, payload="online", qos=1, retain=True)
        else:
            logging.error("MQTT Plugin: connection refused (reason_code=%s)", reason_code)
            self._connected = False

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties=None):
        r"""!paho-mqtt callback on connection loss"""
        logging.warning("MQTT Plugin: connection lost (reason_code=%s) - buffered messages are waiting for reconnect", reason_code)
        self._connected = False

    def _requeue(self, topic, json_payload, retry_count):
        r"""!Puts a message back into the queue after a failed delivery attempt"""
        try:
            self._msg_queue.put_nowait((topic, json_payload, retry_count))
        except queue.Full:
            logging.error("MQTT Plugin: message for topic '%s' discarded while requeuing (buffer full)", topic)

    def _worker_loop(self):
        r"""!Processes the queue sequentially: connected -> send, otherwise buffer & wait"""
        delay = self.initial_delay
        while not self._stop_event.is_set():
            try:
                topic, json_payload, retry_count = self._msg_queue.get(timeout=1)
            except queue.Empty:
                continue

            if not self._connected:
                logging.debug("MQTT Plugin: not connected - message for topic '%s' stays buffered", topic)
                self._requeue(topic, json_payload, retry_count)
                time.sleep(min(delay, self.max_delay))
                continue

            try:
                result = self.client.publish(topic, json_payload, qos=self.qos, retain=self.retain)
                if result.rc != mqtt.MQTT_ERR_SUCCESS:
                    raise RuntimeError(f"publish() returned error code {result.rc}")

                result.wait_for_publish(timeout=5)
                if not result.is_published():
                    raise RuntimeError("no delivery confirmation within 5s")

                logging.debug("MQTT Plugin: message published on topic '%s' (MID=%s, QoS=%d)", topic, result.mid, self.qos)
                delay = self.initial_delay

            except Exception as e:
                if retry_count >= self.max_retries:
                    logging.error("MQTT Plugin: message for topic '%s' permanently discarded after %d attempts: %s", topic, self.max_retries, e)
                else:
                    logging.warning("MQTT Plugin: delivery attempt for topic '%s' failed (%d/%d): %s", topic, retry_count + 1, self.max_retries, e)
                    self._requeue(topic, json_payload, retry_count + 1)
                    time.sleep(min(delay, self.max_delay))
                    delay = min(delay * 2, self.max_delay)


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
        self.clientId = self.config.get("clientId", default="boswatch")
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
        self._ensure_sender()

    def setup(self):
        r"""!Called before alarm - recreates the sender if needed (self-healing)"""
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
        r"""!Ensures that a MqttSender instance exists - checking-with-hasattr pattern
        analogous to telegram.py's _ensure_sender()"""
        if self.sender is not None and self.sender.is_alive():
            return

        if not self.brokerAddress:
            logging.error("MQTT Plugin: 'brokerAddress' not configured - plugin will not send messages.")
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
