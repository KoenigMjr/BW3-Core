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

@file:        test_router.py
@date:        12.10.2026
@author:      Claus Schichl
@description: Unittests for BOSWatch. File have to run as "pytest" unittest
"""
# problem of the pytest fixtures
# pylint: disable=redefined-outer-name
import logging
import pytest

from boswatch.packet import Packet
from boswatch.router.router import Router
from boswatch.router.route import Route

# every route callback writes an entry in this list to check the call order
calledRoutes = []


def setup_function(function):
    logging.debug("[TEST] %s.%s", function.__module__, function.__name__)
    calledRoutes.clear()


def routeReturnNone(bwPacket):
    r"""!Route callback which returns None"""
    calledRoutes.append("none")
    return None


def routeReturnFalse(bwPacket):
    r"""!Route callback which returns False"""
    calledRoutes.append("false")
    return False


def routeReturnModified(bwPacket):
    r"""!Route callback which modifies the packet and returns it"""
    calledRoutes.append("modified")
    bwPacket.set("testField", "modified")
    return bwPacket


def routeModifyInPlace(bwPacket):
    r"""!Route callback which modifies the packet but returns None"""
    calledRoutes.append("inPlace")
    bwPacket.set("testField", "inPlace")
    return None


def routeSaveField(bwPacket):
    r"""!Route callback which saves the content of the test field"""
    calledRoutes.append(bwPacket.get("testField"))
    return None


def statsCallback():
    r"""!Statistics callback for a route point"""
    return {}


def cleanupCallback():
    r"""!Cleanup callback for a route point"""
    pass


@pytest.fixture
def makeRouter():
    r"""!Build a router object"""
    return Router("testRouter")


@pytest.fixture
def makePacket():
    r"""!Build a BW Packet object with a test field"""
    packet = Packet()
    packet.set("testField", "original")
    return packet


def test_routeCreate():
    r"""!Create a route point with all callbacks"""
    route = Route("testRoute", routeReturnNone, statsCallback, cleanupCallback)
    assert route.name == "testRoute"
    assert route.callback is routeReturnNone
    assert route.statistics is statsCallback
    assert route.cleanup is cleanupCallback


def test_routeCreateDefaults():
    r"""!Create a route point without statistics and cleanup callback"""
    route = Route("testRoute", routeReturnNone)
    assert route.statistics is None
    assert route.cleanup is None


def test_routerCreate(makeRouter):
    r"""!Create a router"""
    assert makeRouter.name == "testRouter"
    assert makeRouter.routeList == []


def test_routerAddRoute(makeRouter):
    r"""!Add route points and check the order"""
    makeRouter.addRoute(Route("first", routeReturnNone))
    makeRouter.addRoute(Route("second", routeReturnNone))
    assert [route.name for route in makeRouter.routeList] == ["first", "second"]


def test_routerRunWithoutRoutes(makeRouter, makePacket):
    r"""!Run a router without route points"""
    result = makeRouter.runRouter(makePacket)
    assert result.get("testField") == "original"


def test_routerRunOrder(makeRouter, makePacket):
    r"""!Run all route points in the added order"""
    makeRouter.addRoute(Route("first", routeReturnNone))
    makeRouter.addRoute(Route("second", routeSaveField))
    makeRouter.addRoute(Route("third", routeReturnNone))
    makeRouter.runRouter(makePacket)
    assert calledRoutes == ["none", "original", "none"]


def test_routerReturnNone(makeRouter, makePacket):
    r"""!Returning None continues with the unchanged packet"""
    makeRouter.addRoute(Route("none", routeReturnNone))
    makeRouter.addRoute(Route("save", routeSaveField))
    result = makeRouter.runRouter(makePacket)
    assert calledRoutes == ["none", "original"]
    assert result.get("testField") == "original"


def test_routerReturnModified(makeRouter, makePacket):
    r"""!Returning a packet continues with the modified packet"""
    makeRouter.addRoute(Route("modified", routeReturnModified))
    makeRouter.addRoute(Route("save", routeSaveField))
    result = makeRouter.runRouter(makePacket)
    assert calledRoutes == ["modified", "modified"]
    assert result.get("testField") == "modified"


def test_routerReturnFalse(makeRouter, makePacket):
    r"""!Returning False stops the router - following route points are not called"""
    makeRouter.addRoute(Route("save", routeSaveField))
    makeRouter.addRoute(Route("false", routeReturnFalse))
    makeRouter.addRoute(Route("save", routeSaveField))
    makeRouter.runRouter(makePacket)
    assert calledRoutes == ["original", "false"]


def test_routerReturnFalseResult(makeRouter, makePacket):
    r"""!After a stop the router returns the last packet before the stop"""
    makeRouter.addRoute(Route("modified", routeReturnModified))
    makeRouter.addRoute(Route("false", routeReturnFalse))
    result = makeRouter.runRouter(makePacket)
    assert result.get("testField") == "modified"


def test_routerSubRouterStopped(makeRouter, makePacket):
    r"""!A stopped sub router does not stop the parent router"""
    subRouter = Router("subRouter")
    subRouter.addRoute(Route("false", routeReturnFalse))
    makeRouter.addRoute(Route("subRouter", subRouter.runRouter))
    makeRouter.addRoute(Route("save", routeSaveField))
    makeRouter.runRouter(makePacket)
    assert calledRoutes == ["false", "original"]


def test_routerSubRouterModified(makeRouter, makePacket):
    r"""!The parent router continues with the packet modified by the sub router"""
    subRouter = Router("subRouter")
    subRouter.addRoute(Route("modified", routeReturnModified))
    subRouter.addRoute(Route("false", routeReturnFalse))
    makeRouter.addRoute(Route("subRouter", subRouter.runRouter))
    makeRouter.addRoute(Route("save", routeSaveField))
    makeRouter.runRouter(makePacket)
    assert calledRoutes == ["modified", "false", "modified"]


def test_routerModifyInPlaceIsolated(makeRouter, makePacket):
    r"""!A route point which modifies the packet but returns None does not change the packet for the next route points"""
    makeRouter.addRoute(Route("inPlace", routeModifyInPlace))
    makeRouter.addRoute(Route("save", routeSaveField))
    makeRouter.runRouter(makePacket)
    assert calledRoutes == ["inPlace", "original"]


def test_routerInputPacketUnchanged(makeRouter, makePacket):
    r"""!The packet given to the router is not changed by the route points"""
    makeRouter.addRoute(Route("modified", routeReturnModified))
    makeRouter.addRoute(Route("inPlace", routeModifyInPlace))
    makeRouter.runRouter(makePacket)
    assert makePacket.get("testField") == "original"


def test_routerStatistics(makeRouter, makePacket):
    r"""!Get the statistics after two router runs"""
    makeRouter.addRoute(Route("none", routeReturnNone))
    makeRouter.runRouter(makePacket)
    makeRouter.runRouter(makePacket)
    stats = makeRouter._getStatistics()
    assert stats["type"] == "router"
    assert stats["runCount"] == 2
    assert stats["cumTime"] >= stats["moduleTime"] >= 0
