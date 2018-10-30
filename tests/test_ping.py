"""
Tests the "ping()" API
"""
import pytest

import zproc

ctx = zproc.Context()
pid = ctx.server_process.pid


def test_ping():
    assert zproc.ping(ctx.server_address) == pid
    assert ctx.state.ping() == pid
    assert ctx.ping() == pid


def test_timeout():
    assert zproc.ping(ctx.server_address, timeout=0.5) == pid
    assert ctx.state.ping(timeout=0.5) == pid
    assert ctx.ping(timeout=0.5) == pid


def test_timeout_error():
    with pytest.raises(TimeoutError):
        zproc.ping(ctx.server_address, timeout=0)

    with pytest.raises(TimeoutError):
        ctx.ping(timeout=0)

    with pytest.raises(TimeoutError):
        ctx.state.ping(timeout=0)


def test_ping_after_close():
    ctx.close()

    with pytest.raises(TimeoutError):
        zproc.ping(ctx.server_address, timeout=0.5)

    with pytest.raises(TimeoutError):
        ctx.ping(timeout=0.5)

    with pytest.raises(TimeoutError):
        ctx.state.ping(timeout=0.5)
