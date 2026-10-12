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

@file:        test_socketutils.py
@date:        12.10.2026
@author:      Claus Schichl
@description: Unittests for BOSWatch. File have to run as "pytest" unittest
"""
# problem of the pytest fixtures
# pylint: disable=redefined-outer-name
import logging
import socket
import threading
import time
import pytest

from boswatch.network.socketutils import recvall


def setup_function(function):
    logging.debug("[TEST] %s.%s", function.__module__, function.__name__)


def sendFragments(sock, fragments):
    r"""!Send the fragments one after another with a short break in an own thread
    - one thread for all fragments keeps the order of the fragments"""
    def sendThread():
        for fragment in fragments:
            time.sleep(0.1)
            sock.sendall(fragment)
    threading.Thread(target=sendThread, daemon=True).start()


@pytest.fixture
def getSocketPair():
    r"""!Build two connected sockets - one to send and one to receive"""
    sendSock, recvSock = socket.socketpair()
    recvSock.settimeout(3)
    yield sendSock, recvSock
    sendSock.close()
    recvSock.close()


def test_recvallComplete(getSocketPair):
    r"""!Read data which is completely available"""
    sendSock, recvSock = getSocketPair
    sendSock.sendall(b"1234567890")
    assert recvall(recvSock, 10) == "1234567890"


def test_recvallFragmented(getSocketPair):
    r"""!Read data which arrives in fragments"""
    sendSock, recvSock = getSocketPair
    sendSock.sendall(b"12345")
    sendFragments(sendSock, [b"678", b"90"])
    assert recvall(recvSock, 10) == "1234567890"


def test_recvallOnlyRequestedBytes(getSocketPair):
    r"""!Read only the requested bytes - the rest stays in the socket"""
    sendSock, recvSock = getSocketPair
    sendSock.sendall(b"abcdef")
    assert recvall(recvSock, 3) == "abc"
    assert recvall(recvSock, 3) == "def"


def test_recvallMultibyteFragmented(getSocketPair):
    r"""!Read a multibyte character which is split into two fragments"""
    sendSock, recvSock = getSocketPair
    data = "ä".encode("utf-8")
    sendSock.sendall(data[:1])
    sendFragments(sendSock, [data[1:]])
    assert recvall(recvSock, 2) == "ä"


def test_recvallConnectionClosed(getSocketPair):
    r"""!The connection is closed before all data was read"""
    sendSock, recvSock = getSocketPair
    sendSock.sendall(b"123")
    sendSock.close()
    assert recvall(recvSock, 10) is None


def test_recvallDecodeError(getSocketPair):
    r"""!Received data which is no valid UTF-8"""
    sendSock, recvSock = getSocketPair
    sendSock.sendall(b"\xff\xfe")
    assert recvall(recvSock, 2) is None


def test_recvallSocketError(getSocketPair):
    r"""!Read from a closed socket"""
    _, recvSock = getSocketPair
    recvSock.close()
    assert recvall(recvSock, 10) is None
