"""
Tests the re-creation of object, using the UUID feature
"""
import random

import pytest

import zproc

TEST_VALUE = {"foo": 42}


def test_random_addr():
    ctx = zproc.Context()
    state = ctx.create_state(TEST_VALUE)

    ctx = zproc.Context(ctx.server_address, start_server=False)
    assert state == TEST_VALUE

    state = zproc.State(ctx.server_address)
    assert state == TEST_VALUE


def test_static_addr():
    addr = "tcp://127.0.0.1:%d" % random.randint(20000, 50000)

    ctx = zproc.Context(addr)
    state = ctx.create_state(TEST_VALUE)

    assert state == TEST_VALUE

    state = zproc.State(addr)
    assert state == TEST_VALUE


def test_start_server():
    _, addr = zproc.start_server()

    ctx = zproc.Context(addr, start_server=False)
    state = ctx.create_state(TEST_VALUE)

    ctx = zproc.Context(addr, start_server=False)
    assert state == TEST_VALUE

    state = zproc.State(ctx.server_address)
    assert state == TEST_VALUE


def test_not_start_server():
    with pytest.raises(AssertionError):
        zproc.Context(start_server=False)
