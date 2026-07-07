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

@file:        server.py
@date:        05.07.2026
@author:      Bastian Schroll, Claus Schichl
@description: Class implementation for a threaded TCP socket server
"""
import logging
import socket
import socketserver
import threading
import time
import select
from boswatch.network.socketutils import recvall

logging.debug("- %s loaded", __name__)

HEADERSIZE = 10


class _ThreadedTCPRequestHandler(socketserver.BaseRequestHandler):
    r"""!ThreadedTCPRequestHandler class for our TCPServer class."""

    def _send_ack(self):
        r"""!Sends a standardized protocol acknowledgment [ack] to the client"""
        ack_msg = "[ack]"
        # Build header, pad to 10 characters, and encode both cleanly to bytes
        ack_header = str(len(ack_msg)).ljust(HEADERSIZE).encode("utf-8")
        ack_payload = ack_msg.encode("utf-8")
        self.request.sendall(ack_header + ack_payload)

    def handle(self):
        r"""!Handles the request from an single client in a own thread

        Insert a request in the clients[] list and send a [ack]"""
        with self.server.clientsConnectedLock:  # because our list is not threadsafe
            self.server.clientsConnected[threading.current_thread().name] = {"address": self.client_address[0], "timestamp": time.time()}

        logging.info("Client connected: %s", self.client_address[0])
        cur_thread = threading.current_thread().name
        req_name = str(cur_thread) + " " + self.client_address[0]

        try:
            while self.server.isActive:
                read, _, _ = select.select([self.request], [], [], 0.5)
                if not read:
                    continue  # nothing to read on the socket

                # --- 1. READING HEADER ---
                # recvall() returns a decoded string or None
                header = recvall(self.request, HEADERSIZE, fragment_timeout=10.0)
                if not header:
                    logging.warning("%s connection dropped or fragment timeout/decode error during header read.", req_name)
                    break

                header_stripped = header.strip()
                if not header_stripped.isdigit():
                    logging.error("%s Protocol desync: invalid packet header (expected an integer length, got %r) - closing connection", req_name, header)
                    break

                length = int(header_stripped)

                # --- 2. READING PAYLOAD ---
                # Renamed to 'payload' since it's already a string, not bytes
                payload = recvall(self.request, length, fragment_timeout=10.0)
                if not payload:
                    logging.warning("%s connection dropped or fragment timeout/decode error during payload read.", req_name)
                    break

                # --- 3. KEEP-ALIVE HANDLING ---
                if payload.strip() == "<keep-alive>":
                    # ENABLE next line, if DEBUGGING (BUT CAUTION: logs every one (happens very often!))
                    # logging.debug("%s received <keep-alive>, sending [ack]", req_name)
                    self._send_ack()
                    continue

                # --- 4. PROCESSING ALARM DATA ---
                # Removed redundant .decode() calls
                logging.debug("%s recv header: '%s'", req_name, header)

                # Accurate byte-length calculation for multi-byte UTF-8 characters
                byte_length = len(payload.encode("utf-8"))
                logging.debug("%s recv %d bytes:\n%s", req_name, byte_length, payload)

                # add a new entry and the decoded data string and a timestamp
                self.server.alarmQueue.put((self.client_address[0], payload, time.time()))
                logging.debug("Add data to queue")

                # --- 5. ACKNOWLEDGMENT ALARM ---
                logging.debug("%s send: [ack]", req_name)
                self._send_ack()

        except socket.error as e:
            logging.error(e)
            return False
        finally:
            self.request.close()
            del self.server.clientsConnected[threading.current_thread().name]
            logging.info("Client disconnected: %s", self.client_address[0])


class _ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    r"""!ThreadedTCPServer class for our TCPServer class."""
    pass


class TCPServer:
    r"""!TCP server class"""

    def __init__(self, alarmQueue, timeout=3):
        r"""!Create a new instance

        @param alarmQueue: python queue instance
        @param timeout: server timeout in sec (3)
        """
        self._server = None
        self._server_thread = None
        self._timeout = timeout
        self._alarmQueue = alarmQueue

        self._clientsConnectedLock = threading.Lock()
        self._clientsConnected = {}

    def __del__(self):
        if self.isRunning:
            self.stop()

    def start(self, port=8080):
        r"""!Start a threaded TCP socket server

        Start a TCP Socket Server in a new thread that will
        then start one more thread for each client request.
        The ip address for binding the server socket is always 'localhost'

        @param port: Server Port (8080)

        @return True or False"""
        if not self.isRunning:
            try:
                socketserver.TCPServer.allow_reuse_address = True  # because we can start two instances on same port elsewhere
                self._server = _ThreadedTCPServer(("", port), _ThreadedTCPRequestHandler)
                self._server.timeout = self._timeout
                self._server.alarmQueue = self._alarmQueue
                self._server.isActive = True

                self._server.clientsConnectedLock = self._clientsConnectedLock
                self._server.clientsConnected = self._clientsConnected

                self._server_thread = threading.Thread(target=self._server.serve_forever)
                self._server_thread.name = "Thread-BWServer"
                self._server_thread.daemon = True
                self._server_thread.start()
                logging.debug("TCPServer started in Thread: %s", self._server_thread.name)
                return True
            except socket.error as e:
                logging.error(e)
                return False
        else:
            logging.warning("server always started")
            return True

    def stop(self):
        r"""!Stops the TCP socket server

        @return True or False"""
        if self.isRunning:
            self._server.shutdown()
            self._server.isActive = False
            self._server.server_close()
            self._server_thread.join()
            self._server_thread = None
            self._server = None
            logging.debug("TCPServer stopped")
            return True
        logging.warning("server always stopped")
        return True

    def countClientsConnected(self):
        r"""!Number of currently connected Clients

        @return Connected clients"""
        with self._clientsConnectedLock:  # because our list is not threadsafe
            return len(self._clientsConnected)

    def getClientsConnected(self):
        r"""!A list of all connected clients
        with their IP address and last seen timestamp
        _clients[ThreadName] = {"address", "timestamp"}

        @return List of onnected clients"""
        # todo return full list or write a print/debug method?
        with self._clientsConnectedLock:  # because our list is not threadsafe
            return self._clientsConnected

    @property
    def isRunning(self):
        r"""!Property of server running state"""
        if self._server:
            return True
        return False
