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

@file:        websocket.py
@date:        29.03.2026
@author:      Claus Schichl
@description: WebSocket Client Plugin - sends alarm packets to a WebSocket server
"""
import logging
import asyncio
import json
import threading
from plugin.pluginBase import PluginBase

# ###################### #
# Custom plugin includes #
import websockets
import websockets.exceptions
# ###################### #

logging.debug("- %s loaded", __name__)


class _WebSocketClient:
    r"""!Manages a persistent, auto-reconnecting WebSocket client connection."""

    def __init__(self, url, max_retries, initial_delay, max_delay):
        self._url = url
        self._max_retries = max_retries
        self._initial_delay = initial_delay
        self._max_delay = max_delay

        self._loop = None
        self._thread = None
        self._queue = None
        self._stop_event = None
        self._ready = threading.Event()

        self._connected = False
        self._send_count = 0
        self._error_count = 0

    def start(self):
        r"""!Start the background thread and wait until the event loop is ready."""
        self._thread = threading.Thread(
            target=self._run_loop, name="WSClientThread", daemon=True
        )
        self._thread.start()
        self._ready.wait(timeout=5)

    def stop(self):
        r"""!Signal the background loop to shut down and wait for it to finish."""
        if self._loop and self._stop_event:
            self._loop.call_soon_threadsafe(self._stop_event.set)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=8)
        logging.debug("WebSocket client stopped")

    def enqueue(self, message):
        r"""!Put a message onto the send queue (non-blocking, thread-safe)."""
        if self._loop and self._queue:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, message)

    @property
    def is_connected(self):
        return self._connected

    def _run_loop(self):
        r"""!Thread target: create event loop and run until stop is requested."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._queue = asyncio.Queue()
        self._stop_event = asyncio.Event()
        self._ready.set()
        self._loop.run_until_complete(self._main())
        self._loop.close()

    async def _main(self):
        r"""!Top-level coroutine: keep trying to connect and send until stopped."""
        attempt = 0
        delay = self._initial_delay

        while not self._stop_event.is_set():
            attempt += 1
            try:
                logging.info("WebSocket connecting to %s (attempt %d)", self._url, attempt)
                async with websockets.connect(self._url) as ws:
                    self._connected = True
                    delay = self._initial_delay   # reset backoff on success
                    logging.info("WebSocket connected to %s", self._url)
                    await self._send_loop(ws)

            except (OSError, websockets.exceptions.WebSocketException) as e:
                self._connected = False
                self._error_count += 1
                logging.warning("WebSocket error: %s", e)

            except Exception as e:
                self._connected = False
                self._error_count += 1
                logging.exception("Unexpected WebSocket error: %s", e)

            finally:
                self._connected = False

            if self._stop_event.is_set():
                break

            if self._max_retries and attempt >= self._max_retries:
                logging.error("WebSocket: max retries (%d) reached, giving up", self._max_retries)
                break

            logging.debug("WebSocket reconnecting in %.1f s", delay)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass

            delay = min(delay * 2, self._max_delay)

    async def _send_loop(self, ws):
        r"""!Drain the queue and forward messages to the open WebSocket connection."""
        while not self._stop_event.is_set():
            try:
                # Wait up to 0.5 s for a message so we can react to stop quickly
                message = await asyncio.wait_for(self._queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                # Heartbeat ping to detect dropped connections early
                try:
                    pong = await ws.ping()
                    await asyncio.wait_for(pong, timeout=5)
                except Exception:
                    logging.warning("WebSocket ping failed – connection lost")
                    return
                continue

            try:
                await ws.send(message)
                self._send_count += 1
                logging.debug("WebSocket sent message #%d", self._send_count)
            except websockets.exceptions.WebSocketException as e:
                # Put message back so it is not lost, then reconnect
                await self._queue.put(message)
                logging.warning("WebSocket send failed, will retry after reconnect: %s", e)
                return


# ===========================================================================
# BOSWatch Plugin
# ===========================================================================

class BoswatchPlugin(PluginBase):
    r"""!WebSocket Client Plugin"""

    def __init__(self, config):
        r"""!Do not change anything here!"""
        super().__init__(__name__, config)

    def onLoad(self):
        r"""!Called by import of the plugin"""
        self._client = None
        url = self.config.get("url")

        if not url:
            logging.error("WebSocket plugin: 'url' is required in config")
            return

        # Parameter aus der Config holen, mit den offiziellen Defaults der README
        max_retries = int(self.config.get("max_retries", default=0))
        initial_delay = float(self.config.get("initial_delay", default=2.0))
        max_delay = float(self.config.get("max_delay", default=60.0))

        self._client = _WebSocketClient(
            url=url,
            max_retries=max_retries,
            initial_delay=initial_delay,
            max_delay=max_delay,
        )
        self._client.start()
        logging.info("WebSocket plugin started → %s", url)

    def onUnload(self):
        r"""!Called by destruction of the plugin"""
        if hasattr(self, '_client') and self._client:
            self._client.stop()
            logging.info("WebSocket plugin stopped.")

    # ------------------------------------------------------------------
    # Alarm handlers (Plugins geben gemäß README immer None zurück)
    # ------------------------------------------------------------------

    def fms(self, bwPacket):
        r"""!Called on FMS alarm"""
        self._send("FMS", bwPacket)

    def pocsag(self, bwPacket):
        r"""!Called on POCSAG alarm"""
        self._send("POCSAG", bwPacket)

    def zvei(self, bwPacket):
        r"""!Called on ZVEI alarm"""
        self._send("ZVEI", bwPacket)

    def msg(self, bwPacket):
        r"""!Called on MSG packet"""
        self._send("MSG", bwPacket)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _base_payload(self, bwPacket):
        r"""!Build the fields common to every alarm type using the official .get() method"""
        return {
            "mode": bwPacket.get("mode"),
            "timestamp": bwPacket.get("timestamp"),
            "serverName": bwPacket.get("serverName"),
            "clientName": bwPacket.get("clientName"),
            "clientIP": bwPacket.get("clientIP"),
            "inputSource": bwPacket.get("inputSource"),
            "frequency": bwPacket.get("frequency"),
        }

    def _send(self, alarm_type, bwPacket):
        r"""!Dynamically collects all fields and enqueues the message."""
        if not hasattr(self, '_client') or not self._client:
            logging.warning("WebSocket plugin not initialized, dropping alarm")
            return

        # 1. Wir versuchen, alle Datenfelder dynamisch zu extrahieren
        # BW3-Core Pakete speichern ihre Daten meist in einem internen Dict namens '_data'
        # oder lassen sich über vars() auslesen.
        payload = {}

        try:
            # Falls das Paket eine interne Datenstruktur hat (Standard in BW3):
            if hasattr(bwPacket, '_data'):
                payload = bwPacket._data.copy()
            else:
                # Fallback: Versuche alle Attribute des Objekts zu nehmen, die nicht mit '_' beginnen (Methoden/Interne Variablen)
                payload = {k: v for k, v in vars(bwPacket).items() if not k.startswith('_')}
        except Exception:
            # Letzter Rettungsanker: Nur die Basisfelder manuell holen, falls obiges fehlschlägt
            logging.debug("Dynamic extraction failed, falling back to manual list")
            fields = ["mode", "timestamp", "serverName", "clientName", "ric", "message", "fms", "status", "tone"]
            for f in fields:
                val = bwPacket.get(f)
                if val is not None:
                    payload[f] = val

        # 2. Metadaten hinzufügen
        payload["alarm_type_plugin"] = alarm_type  # Zur Sicherheit, welcher Handler getriggert wurde

        # 3. Säubern (keine None-Werte) und JSON-Serialisierung
        clean = {k: v for k, v in payload.items() if v is not None}
        message = json.dumps(clean, ensure_ascii=False)

        self._client.enqueue(message)
        logging.debug("WebSocket enqueued dynamic packet: %s", message[:120])
