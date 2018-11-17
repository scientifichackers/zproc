"""
Tests the re-creation of object, using the UUID feature
"""
import random

import pytest

import zproc


def test_random_addr():
    ctx = zproc.Context()
    ctx.state["foo"] = 42

    ctx = zproc.Context(ctx.address, start_server=False)
    assert ctx.state.copy() == {"foo": 42}

    state = zproc.State(ctx.address)
    assert state.copy() == {"foo": 42}


def test_static_addr():
    addr = "tcp://127.0.0.1:%d" % random.randint(20000, 50000)

    ctx = zproc.Context(addr)
    ctx.state["foo"] = 42

    assert ctx.state.copy() == {"foo": 42}

    state = zproc.State(addr)
    assert state.copy() == {"foo": 42}


def test_start_server():
    _, addr = zproc.start_server()

    ctx = zproc.Context(addr, start_server=False)
    ctx.state["foo"] = 42

    ctx = zproc.Context(addr, start_server=False)
    assert ctx.state.copy() == {"foo": 42}

    state = zproc.State(ctx.address)
    assert state.copy() == {"foo": 42}


def test_not_start_server():
    with pytest.raises(AssertionError):
        zproc.Context(start_server=False)
