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

@file:        route.py
@date:        30.08.2026
@author:      Bastian Schroll
@description: Class for a single BOSWatch packet router route point
"""

import logging

logging.debug("- %s loaded", __name__)


class Route:
    r"""!Class for single routing points"""
    def __init__(self, name, callback, statsCallback=None, cleanupCallback=None, isRouter=False):
        r"""!Create a instance of an route point

        @param name: name of the route point
        @param callback: instance of the callback function
        @param statsCallback: instance of the callback to get statistics (None)
        @param cleanupCallback: instance of the callback to run a cleanup method (None)
        @param isRouter: True if this route point jumps into another router (type: router).
                         Used by Router._process_route_recursive() to distinguish a
                         sub-router that filtered internally (continue with the parent's
                         next route point) from a module/plugin that explicitly stops
                         the whole route (stop immediately). (False)
        """
        self.name = name
        self.callback = callback
        self.statistics = statsCallback
        self.cleanup = cleanupCallback
        self.isRouter = isRouter
