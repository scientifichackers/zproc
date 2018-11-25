import pytest

import zproc


@pytest.fixture
def ctx():
    return zproc.Context()


@pytest.fixture
def state(ctx):
    return ctx.create_state({"times": 0})


def test_retry(ctx, state):
    @ctx.spawn(retry_for=[ValueError], max_retries=5, retry_delay=0)
    def p(ctx):
        state = ctx.create_state()
        try:
            raise ValueError
        finally:
            state["times"] += 1

    with pytest.raises(zproc.ProcessWaitError):
        p.wait()
    assert state["times"] == 6


def test_infinite_retry(ctx, state):
    @ctx.spawn(retry_for=[ValueError], max_retries=None, retry_delay=0.005)
    def p(ctx):
        state = ctx.create_state()
        try:
            raise ValueError
        finally:
            state["times"] += 1

    with pytest.raises(TimeoutError):
        p.wait(timeout=0.1)
    p.stop()
    assert 10 <= state["times"] <= 20
