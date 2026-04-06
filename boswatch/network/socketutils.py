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
@date:        12.04.2026
@author:      Claus Schichl
@description: Shared network utility functions for robust TCP communication
"""
import logging
import select

logging.debug("- %s loaded", __name__)

# Maximum time in seconds to wait for the next fragment before aborting.
# Covers the "Half-Open Connection" scenario over VPN/WAN connections.
_RECVALL_FRAGMENT_TIMEOUT = 10.0


def recvall(sock, n, fragment_timeout=_RECVALL_FRAGMENT_TIMEOUT):
    r"""!Read exactly n bytes from a socket.

    Unlike sock.recv(n), this function guarantees that exactly n bytes
    are read, even if the underlying TCP stream delivers them in multiple
    fragments (e.g. over VPN with reduced MTU).

    Uses an internal per-fragment timeout for blocking sockets to prevent
    threads from hanging indefinitely on half-open connections (e.g. VPN dropout).
    Respects existing socket timeouts if already set.

    @param sock: A connected socket object
    @param n: Number of bytes to read
    @param fragment_timeout: Max seconds to wait for next fragment (default: 10.0)
    @return Decoded string of exactly n bytes, or None if connection broke or timeout was exceeded"""
    data = bytearray()
    while len(data) < n:
        # Check if socket is in blocking mode (no timeout set)
        if sock.gettimeout() is None:
            # Blocking socket (e.g. Server) - use select() to prevent infinite hang
            ready, _, _ = select.select([sock], [], [], fragment_timeout)
            if not ready:
                logging.warning("recvall: fragment timeout after %.1fs "
                                "(%d/%d bytes received) - possible half-open connection",
                                fragment_timeout, len(data), n)
                return None

        try:
            packet = sock.recv(n - len(data))
        except OSError as e:
            logging.warning("recvall: socket error after %d/%d bytes: %s", len(data), n, e)
            return None

        if not packet:
            logging.debug("recvall: connection closed after %d/%d bytes", len(data), n)
            return None

        data.extend(packet)

    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as e:
        logging.warning("recvall: decode error: %s | raw: %s", e, data.hex())
        return None
