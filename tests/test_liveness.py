from time import sleep

import pytest

import zproc


@pytest.fixture
def state() -> zproc.State:
    ctx = zproc.Context()

    @ctx.spawn
    def mutator(ctx: zproc.Context):
        state = ctx.create_state()

        for n in range(10):
            state["counter"] = n
            sleep(0.1)

    return ctx.create_state()


def test_not_live(state: zproc.State):
    it = state.get_when_change("counter")
    sleep(0.25)
    assert next(it)["counter"] == 0


def test_live(state: zproc.State):
    it = state.get_when_change("counter", live=True)
    sleep(0.25)
    assert next(it)["counter"] > 0


def test_go_live(state: zproc.State):
    it = state.get_when_change("counter")
    sleep(0.25)
    state.go_live()
    assert next(it)["counter"] > 0
