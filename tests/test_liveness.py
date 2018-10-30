from time import sleep

import pytest

import zproc


@pytest.fixture
def state() -> zproc.State:
    ctx = zproc.Context()

    @ctx.process
    def mutator(state: zproc.State):
        for i in range(10):
            state["counter"] = i
            sleep(0.1)

    return ctx.state


def test_not_live(state: zproc.State):
    sleep(0.25)
    assert state.get_when_change("counter")["counter"] == 0


def test_live(state: zproc.State):
    sleep(0.25)
    assert state.get_when_change("counter", live=True)["counter"] > 0


def test_go_live(state: zproc.State):
    sleep(0.25)
    state.go_live()
    assert state.get_when_change("counter")["counter"] > 0
