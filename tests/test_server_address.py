"""
Tests the re-creation of object, using the UUID feature
"""

import zproc


def test_random_addr():
    ctx = zproc.Context()
    ctx.state["foo"] = 42

    ctx = zproc.Context(ctx.server_address)
    assert ctx.state.copy() == {"foo": 42}

    state = zproc.State(ctx.server_address)
    assert state.copy() == {"foo": 42}


ADDRESS = "tcp://127.0.0.1:50000"


def test_static_addr():
    zproc.start_server(ADDRESS)

    ctx = zproc.Context(ADDRESS)
    ctx.state["foo"] = 42

    assert ctx.state.copy() == {"foo": 42}

    state = zproc.State(ADDRESS)
    assert state.copy() == {"foo": 42}
