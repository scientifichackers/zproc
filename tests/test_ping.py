"""
Tests the "ping()" API
"""
import pytest

import zproc


@pytest.fixture
def ctx():
    return zproc.Client()


@pytest.fixture
def state(ctx):
    return ctx.create_state()


def test_ping(ctx, state):
    pid = ctx.server_process.pid
    assert zproc.ping(ctx.server_address) == pid
    assert state.ping() == pid
    assert ctx.ping() == pid


def test_timeout(ctx, state):
    pid = ctx.server_process.pid
    assert zproc.ping(ctx.server_address, timeout=0.1) == pid
    assert state.ping(timeout=0.1) == pid
    assert ctx.ping(timeout=0.1) == pid


def test_timeout_error(ctx, state):
    with pytest.raises(TimeoutError):
        zproc.ping(ctx.server_address, timeout=0)

    with pytest.raises(TimeoutError):
        ctx.ping(timeout=0)

    with pytest.raises(TimeoutError):
        state.ping(timeout=0)


def test_ping_after_close(ctx, state):
    ctx.server_process.terminate()

    with pytest.raises(TimeoutError):
        zproc.ping(ctx.server_address, timeout=0.1)

    with pytest.raises(TimeoutError):
        ctx.ping(timeout=0.1)

    with pytest.raises(TimeoutError):
        state.ping(timeout=0.1)
