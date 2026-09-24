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

@file:        client.py
@date:        21.09.2026
@author:      Bastian Schroll
@description: Class implementation for a TCP socket client
"""
import logging
import socket
import select
from boswatch.network.socketutils import recvall

logging.debug("- %s loaded", __name__)

HEADERSIZE = 10


class TCPClient:
    r"""!TCP client class"""

    def __init__(self, timeout=3):
        r"""!Create a new instance

        @param timeout: timeout for the client in sec. (3)"""
        socket.setdefaulttimeout(timeout)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def connect(self, host="localhost", port=8080):
        r"""!Connect to the server

        @param host: Server IP address ("localhost")
        @param port: Server Port (8080)
        @return True or False"""
        try:
            if not self.isConnected:
                self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._sock.connect((host, port))
                logging.debug("connected to %s:%s", host, port)
                return True
            logging.warning("client always connected")
            return True
        except socket.error as e:
            logging.error(e)
        return False

    def disconnect(self):
        r"""!Disconnect from the server

        @return True or False"""
        try:
            if self._sock:
                try:
                    self._sock.shutdown(socket.SHUT_RDWR)
                except socket.error:
                    pass  # Ignore shutdown errors on a dead connection
                self._sock.close()
                self._sock = None
                logging.debug("disconnected")
                return True
            logging.warning("client already disconnected")
            return True
        except socket.error as e:
            logging.error(e)
        return False

    def transmit(self, data):
        r"""!Send a data packet to the server

        @param data: data to send to the server
        @return True or False"""
        try:
            logging.debug("transmitting:\n%s", data)
            data = data.encode("utf-8")
            header = str(len(data)).ljust(HEADERSIZE).encode("utf-8")
            self._sock.sendall(header + data)
            logging.debug("transmitted...")
            return True
        except socket.error as e:
            logging.error(e)
        return False

    def receive(self, timeout=1):
        r"""!Receive data from the server

        @param timeout: to wait for incoming data in seconds
        @return received data"""
        try:
            read, _, _ = select.select([self._sock], [], [], timeout)
            if not read:  # check if there is something to read
                return False

            header = recvall(self._sock, HEADERSIZE)
            if header is None:
                return False

            header_stripped = header.strip()
            if not header_stripped.isdigit():
                logging.warning("Invalid header received: '%s'", header_stripped)
                return False

            length = int(header_stripped)
            received = recvall(self._sock, length, fragment_timeout=5.0)
            if received is None:
                return False

            logging.debug("recv header: '%s'", header)
            logging.debug("received %d bytes: %s", len(received), received)
            return received
        except socket.error as e:
            logging.error(e)
        return False

    @property
    def isConnected(self):
        r"""!Property of client connected state"""
        try:
            if self._sock:
                self._sock.getpeername()
                read, write, _ = select.select([self._sock], [self._sock], [], 0.1)
                if read:
                    # Peek without consuming - empty = FIN = connection closed
                    data = self._sock.recv(1, socket.MSG_PEEK)
                    if not data:
                        return False
                return bool(write)
            return False
        except (socket.error, ValueError) as e:
            logging.warning("Connection lost (%s) - buffering packet and entering retry mode", e)
            return False
