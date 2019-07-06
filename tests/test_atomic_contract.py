import os
import signal
import time

import pytest

import zproc


@pytest.fixture
def ctx():
    return zproc.Client()


@pytest.fixture
def state(ctx):
    return ctx.create_state()


def test_exception_contract(ctx, state):
    @zproc.atomic
    def mutator(snap):
        snap["x"] = 5
        raise ValueError

    with pytest.raises(ValueError):
        mutator(state)

    assert state == {}


def test_signal_contract(ctx, state):
    @zproc.atomic
    def atomic_fn(snap):
        snap["x"] = 5
        time.sleep(0.1)

    curpid = os.getpid()

    @ctx.spawn(pass_context=False)
    def p():
        time.sleep(0.05)
        zproc.send_signal(signal.SIGINT, curpid)

    zproc.signal_to_exception(signal.SIGINT)

    with pytest.raises(zproc.SignalException):
        atomic_fn(state)

    print(state.copy())
    assert state == {"x": 5}
