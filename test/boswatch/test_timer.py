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

@file:        test_timer.py
@date:        12.10.2026
@author:      Bastian Schroll
@description: Unittests for BOSWatch. File have to run as "pytest" unittest
"""
# problem of the pytest fixtures
# pylint: disable=redefined-outer-name
import logging
import time
import pytest

from boswatch.timer import RepeatedTimer

# every call of a worker writes an entry in this list
calledTargets = []


def setup_function(function):
    logging.debug("[TEST] %s.%s", function.__module__, function.__name__)
    calledTargets.clear()


def targetFast():
    r"""!Fast worker thread"""
    logging.debug("run targetFast")
    calledTargets.append("fast")


def targetSlow():
    r"""!Slow worker thread"""
    logging.debug("run targetSlow start")
    calledTargets.append("slow")
    time.sleep(0.51)
    logging.debug("run targetSlow end")


def waitForCalls(count, timeout=5):
    r"""!Wait until the worker was called the given number of times
    @return True or False if the timeout is reached"""
    endTime = time.time() + timeout
    while len(calledTargets) < count:
        if time.time() > endTime:
            return False
        time.sleep(0.01)
    return True


@pytest.fixture()
def useTimerFast():
    r"""!Server a RepeatedTimer instance with fast worker"""
    testTimer = RepeatedTimer(0.1, targetFast)
    yield testTimer
    if testTimer.isRunning:
        assert testTimer.stop()


@pytest.fixture()
def useTimerSlow():
    r"""!Server a RepeatedTimer instance slow worker"""
    testTimer = RepeatedTimer(0.1, targetSlow)
    yield testTimer
    if testTimer.isRunning:
        assert testTimer.stop()


def test_timerStartStop(useTimerFast):
    r"""!Try to start and stop a timer"""
    assert useTimerFast.start()
    assert useTimerFast.stop()


def test_timerDoubleStart(useTimerFast):
    r"""!Try to start a timer twice"""
    assert useTimerFast.start()
    assert useTimerFast.start()
    assert useTimerFast.stop()


def test_timerStopNotStarted(useTimerFast):
    r"""!Try to stop a timer where is not started"""
    assert useTimerFast.stop()


def test_timerIsRunning(useTimerFast):
    r"""!Check if a timer is running"""
    assert useTimerFast.start()
    assert useTimerFast.isRunning
    assert useTimerFast.stop()


def test_timerRun(useTimerFast):
    r"""!Run a timer and check that the worker is called without overdue and lostEvents"""
    assert useTimerFast.start()
    assert waitForCalls(2)
    assert useTimerFast.stop()
    assert useTimerFast.overdueCount == 0
    assert useTimerFast.lostEvents == 0


def test_timerOverdue(useTimerSlow):
    r"""!Run a timer with a slow worker once and check overdue and lostEvents"""
    assert useTimerSlow.start()
    assert waitForCalls(1)
    assert useTimerSlow.stop()
    assert len(calledTargets) == 1
    assert useTimerSlow.overdueCount == 1
    assert useTimerSlow.lostEvents >= 5


def test_timerOverdueLong(useTimerSlow):
    r"""!Run a timer with a slow worker twice and check overdue and lostEvents"""
    assert useTimerSlow.start()
    assert waitForCalls(2)
    assert useTimerSlow.stop()
    assert len(calledTargets) == 2
    assert useTimerSlow.overdueCount == 2
    assert useTimerSlow.lostEvents >= 10
