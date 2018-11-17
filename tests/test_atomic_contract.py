import os
import signal
import time

import pytest

import zproc


@pytest.fixture
def ctx():
    return zproc.Context()


def test_exception_contract(ctx):
    @zproc.atomic
    def mutator(snap):
        snap["x"] = 5
        raise ValueError

    with pytest.raises(ValueError):
        mutator(ctx.state)

    assert ctx.state == {}


def test_signal_contract(ctx):
    @zproc.atomic
    def mutator(snap):
        snap["x"] = 5
        time.sleep(0.1)

    curpid = os.getpid()

    @ctx.spawn(pass_state=False)
    def p():
        time.sleep(0.05)
        zproc.send_signal(signal.SIGINT, curpid)

    zproc.signal_to_exception(signal.SIGINT)

    with pytest.raises(zproc.SignalException):
        mutator(ctx.state)

    assert ctx.state == {"x": 5}
