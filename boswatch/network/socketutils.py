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

@file:        socketutils.py
@date:        08.10.2026
@author:      Claus Schichl
@description: Shared network utility functions for robust TCP communication
"""
import logging

logging.debug("- %s loaded", __name__)


def recvall(sock, n):
    r"""!Read exactly n bytes from a socket.

    Unlike sock.recv(n), this function guarantees that exactly n bytes
    are read even if the TCP stream delivers them in multiple fragments
    (e.g. over VPN with reduced MTU). Relies on the socket's own timeout
    (set via socket.setdefaulttimeout) to prevent indefinite blocking.

    @param sock: A connected socket object
    @param n: Number of bytes to read
    @return Decoded UTF-8 string of exactly n bytes, or None on error"""
    data = bytearray()
    while len(data) < n:
        try:
            chunk = sock.recv(n - len(data))
        except OSError as e:
            logging.warning("recvall: socket error after %d/%d bytes: %s", len(data), n, e)
            return None
        if not chunk:
            logging.debug("recvall: connection closed after %d/%d bytes", len(data), n)
            return None
        data.extend(chunk)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as e:
        logging.warning("recvall: decode error: %s | raw: %s", e, data.hex())
        return None
