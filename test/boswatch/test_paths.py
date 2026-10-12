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

@file:        test_paths.py
@date:        12.10.2026
@author:      Bastian Schroll
@description: Unittests for BOSWatch. File have to run as "pytest" unittest
"""
# problem of the pytest fixtures
# pylint: disable=redefined-outer-name
import logging
import os

from boswatch.utils import paths


def setup_function(function):
    logging.debug("[TEST] %s.%s", function.__module__, function.__name__)


def test_fileExists():
    r"""!Check an existing file"""
    assert paths.fileExist(paths.ROOT_PATH + "README.md")


def test_fileNotExists():
    r"""!Check a not existing file"""
    assert not paths.fileExist(paths.ROOT_PATH + "notFound.txt")


def test_testPath():
    r"""!The test path contains the test config"""
    assert paths.fileExist(paths.TEST_PATH + "test_config.yaml")


def test_makeDirNotExisting(tmp_path):
    r"""!Create a not existing directory"""
    dirPath = str(tmp_path / "UnItTeSt")
    assert paths.makeDirIfNotExist(dirPath) == dirPath
    assert os.path.isdir(dirPath)


def test_makeDirExisting(tmp_path):
    r"""!Create an already existing directory"""
    dirPath = str(tmp_path / "UnItTeSt")
    paths.makeDirIfNotExist(dirPath)
    assert paths.makeDirIfNotExist(dirPath) == dirPath
    assert os.path.isdir(dirPath)
