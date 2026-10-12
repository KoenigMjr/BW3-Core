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

@file:        telegram.py
@date:        12.10.2026
@author:      Claus Schichl
@description: Telegram-Plugin
"""

import logging
import time
import threading
import queue
import requests
import re
from plugin.pluginBase import PluginBase

# Setup logging
logger = logging.getLogger(__name__)


# ===========================
# TelegramSender-Class
# ===========================

class TelegramSender:
    def __init__(self, bot_token, chat_ids, max_retries=None, initial_delay=None, max_delay=None, parse_mode=None):
        self._stop_event = threading.Event()
        self.bot_token = bot_token
        self.chat_ids = chat_ids
        self.max_retries = max_retries if max_retries is not None else 5
        self.initial_delay = initial_delay if initial_delay is not None else 2
        self.max_delay = max_delay if max_delay is not None else 300
        self.parse_mode = parse_mode

        # one queue and one worker thread per chat:
        # - the messages of a chat are sent in the right order, also after a retry
        # - a failing chat does not delay the messages to the other chats
        self.msg_queues = {}
        self._workers = {}
        for chat_id in self.chat_ids:
            if chat_id in self.msg_queues:
                continue  # a chat id configured twice gets only one worker
            self.msg_queues[chat_id] = queue.Queue(maxsize=100)  # max 100 messages per chat
            self._workers[chat_id] = threading.Thread(target=self._worker_loop, args=(chat_id,),
                                                      name=f"Telegram({chat_id})", daemon=True)
            self._workers[chat_id].start()

    def send_message(self, text):
        clean_text = self._escape_text(text, self.parse_mode)
        for chat_id in self.msg_queues:
            try:
                self.msg_queues[chat_id].put(("text", clean_text), block=False)
            except queue.Full:
                logger.error(f"Message queue full for chat_id {chat_id}, message discarded: {clean_text[:50]}...")

    def send_location(self, latitude, longitude):
        try:
            # Use validated float values, not original strings
            lat = float(latitude)
            lon = float(longitude)
            # check Telegram API Limits
            if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                logger.error(f"Invalid coordinates: lat={lat}, lon={lon} (out of range)")
                return
        except (TypeError, ValueError) as e:
            logger.error(f"Invalid coordinate format: {e}, location skipped")
            return

        for chat_id in self.msg_queues:
            try:
                self.msg_queues[chat_id].put(("location", {"latitude": lat, "longitude": lon}), block=False)
            except queue.Full:
                logger.error(f"Location queue full for chat_id {chat_id}, location discarded: {lat}, {lon}")

    @staticmethod
    def _escape_text(text, parse_mode):
        if not text:
            return ""
        if parse_mode == "HTML":
            protected_tags = {}
            tag_pattern = r'<(/?)(\w+)>'
            allowed = ["b", "strong", "i", "em", "code", "pre", "u", "s"]

            def protect_tag(match):
                tag_full = match.group(0)
                tag_name = match.group(2)
                if tag_name in allowed:
                    placeholder = f"__TAG_{len(protected_tags)}__"
                    protected_tags[placeholder] = tag_full
                    return placeholder
                return tag_full

            text = re.sub(tag_pattern, protect_tag, text)
            text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            for placeholder, original_tag in protected_tags.items():
                text = text.replace(placeholder, original_tag)
        elif parse_mode == "MarkdownV2":
            # Escape all MarkdownV2 special characters (Telegram API requirement)
            # See: https://core.telegram.org/bots/api#markdownv2-style
            escape_chars = r'_*[]()~`>#+-=|{}.!'
            text = "".join(['\\' + char if char in escape_chars else char for char in text])
        return TelegramSender._shorten_text(text, parse_mode)

    @staticmethod
    def _shorten_text(text, parse_mode):
        r"""!Shorten an escaped text to the telegram limit of 4096 characters
        without cutting an escape sequence or an HTML entity"""
        if len(text) <= 4096:
            return text
        suffix = "\\[\\.\\.\\.\\]" if parse_mode == "MarkdownV2" else "[...]"
        text = text[:4096 - len(suffix)]
        if parse_mode == "MarkdownV2":
            # an odd number of backslashes at the end would escape the suffix
            if (len(text) - len(text.rstrip("\\"))) % 2:
                text = text[:-1]
        elif parse_mode == "HTML":
            # remove a cut HTML entity at the end
            lastAmp = text.rfind("&")
            if lastAmp != -1 and ";" not in text[lastAmp:]:
                text = text[:lastAmp]
        return text + suffix

    def _worker_loop(self, chat_id):
        r"""!Send the messages of one chat one after another

        A failed message stays at the head of the queue and is retried until it is
        sent, it fails permanently or max_retries is reached - so the order is kept.
        The waiting time between the retries grows exponentially while the chat
        is not reachable and is reset after the next successful message."""
        msg_queue = self.msg_queues[chat_id]
        delay = self.initial_delay
        while True:
            item = msg_queue.get()  # blocking without timeout - no cpu usage while idle
            if item is None:
                return  # shutdown: all messages before were sent
            msg_type, content = item
            retry_count = 0
            while True:
                try:
                    success, permanent_failure, custom_delay, error_details = self._send_to_telegram(msg_type, chat_id, content)
                except Exception as e:
                    success, permanent_failure, custom_delay, error_details = False, False, None, str(e)
                if success:
                    delay = self.initial_delay
                    break
                if permanent_failure or retry_count >= self.max_retries:
                    logger.warning(f"Discarding message for {chat_id}: {error_details}")
                    break
                wait_time = custom_delay if custom_delay is not None else delay
                if self._stop_event.wait(wait_time):
                    logger.warning(f"Discarding message for {chat_id}: shutdown while waiting for retry")
                    return
                retry_count += 1
                delay = min(delay * 2, self.max_delay)

    def _send_to_telegram(self, msg_type, chat_id, content):
        url = f"https://api.telegram.org/bot{self.bot_token}/"
        url += "sendMessage" if msg_type == "text" else "sendLocation"
        payload = {'chat_id': chat_id}

        if msg_type == "text":
            payload['text'] = content
            if self.parse_mode:
                payload['parse_mode'] = self.parse_mode
        else:
            payload.update(content)

        try:
            response = requests.post(url, data=payload, timeout=10)
            if response.status_code == 200:
                logger.info(f"Successfully sent to Chat-ID {chat_id}")
                return True, False, None, None

            # Rate limiting
            if response.status_code == 429:
                retry_after = response.json().get("parameters", {}).get("retry_after", 5)
                logger.warning(f"Rate limited for {chat_id}, retry after {retry_after}s")
                return False, False, retry_after, f"Rate Limit (retry after {retry_after}s)"

            return False, response.status_code < 500, None, f"HTTP {response.status_code}"
        except Exception as e:
            return False, False, None, str(e)

    def shutdown(self):
        r"""!Graceful shutdown with queue draining"""
        logger.info("Shutting down Telegram sender...")
        # let the worker send the remaining messages before it is stopped
        timeout = time.time() + 5
        for chat_id, msg_queue in self.msg_queues.items():
            try:
                msg_queue.put(None, timeout=max(0, timeout - time.time()))  # stop mark behind the last message
            except queue.Full:
                pass
        for worker in self._workers.values():
            worker.join(timeout=max(0, timeout - time.time()))
        self._stop_event.set()  # interrupt a worker which is still waiting for a retry
        for worker in self._workers.values():
            worker.join(timeout=1)
        remaining = sum(1 for msg_queue in self.msg_queues.values() for item in list(msg_queue.queue) if item is not None)
        if remaining > 0:
            logger.warning(f"{remaining} messages in queue discarded during shutdown")


# ===========================
# BoswatchPlugin-Class
# ===========================

logging.debug("- %s loaded", __name__)


class BoswatchPlugin(PluginBase):
    r"""!Description of the Plugin"""
    def __init__(self, config):
        r"""!Do not change anything here!"""
        super().__init__(__name__, config)  # you can access the config class on 'self.config'

    def _ensure_sender(self):
        r""" checking with hasattr if self.sender already exists"""
        if not hasattr(self, 'sender') or self.sender is None:
            token = self.config.get("botToken")
            ids = self.config.get("chatIds", default=[])

            if token and ids:
                self.sender = TelegramSender(
                    bot_token=token,
                    chat_ids=ids,
                    max_retries=self.config.get("max_retries"),
                    initial_delay=self.config.get("initial_delay"),
                    max_delay=self.config.get("max_delay"),
                    parse_mode=self.config.get("parse_mode")
                )
                logger.debug("TelegramSender initialized via Self-Healing")
            else:
                missing = []
                if not token:
                    missing.append("botToken")
                if not ids:
                    missing.append("chatIds")
                logger.error(f"Telegram configuration incomplete! Missing: {', '.join(missing)}. Plugin will not send messages.")

    def _has_sender(self):
        r"""Check if sender is available and properly initialized"""
        return hasattr(self, 'sender') and self.sender is not None

    def onLoad(self):
        r"""!Called by import of the plugin"""
        self._ensure_sender()
        if not self._has_sender():
            logger.warning("Telegram plugin loaded but not configured.  Messages will be discarded.")
        else:
            startup = self.config.get("startup_message")
            if startup and startup.strip():
                self.sender.send_message(startup)

    def setup(self):
        r"""!Called before alarm"""
        # ensure sender exists before alarms are processed
        self._ensure_sender()

    def fms(self, bwPacket):
        r"""!Called on FMS alarm"""
        if self._has_sender():
            msg = self.parseWildcards(self.config.get("message_fms", default="{FMS}"))
            self.sender.send_message(msg)

    def pocsag(self, bwPacket):
        r"""!Called on POCSAG alarm"""
        if self._has_sender():
            msg = self.parseWildcards(self.config.get("message_pocsag", default="{RIC}({SRIC})\n{MSG}"))
            self.sender.send_message(msg)

            if self.config.get("coordinates", default=False):
                lat = bwPacket.get("lat")
                lon = bwPacket.get("lon")
                if lat is not None and lon is not None:
                    self.sender.send_location(lat, lon)

    def zvei(self, bwPacket):
        r"""!Called on ZVEI alarm"""
        if self._has_sender():
            msg = self.parseWildcards(self.config.get("message_zvei", default="{TONE}"))
            self.sender.send_message(msg)

    def msg(self, bwPacket):
        r"""!Called on MSG packet"""
        if self._has_sender():
            msg = self.parseWildcards(self.config.get("message_msg", default="{MSG}"))
            self.sender.send_message(msg)

    def teardown(self):
        r"""!Called after alarm"""
        pass

    def onUnload(self):
        r"""!Called by destruction of the plugin"""
        if self._has_sender():
            self.sender.shutdown()
            logger.info("Telegram plugin unloaded")
