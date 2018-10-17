import time

import pytest

import zproc


def _setup_ctx():
    ctx = zproc.Context()

    @ctx.process
    def updater(state):
        time.sleep(1)
        state["flag"] = True
        print(state)

    return ctx


@pytest.fixture
def ctx():
    return _setup_ctx()


@pytest.fixture
def state():
    return _setup_ctx().state


###


def test_get_when_change(state):
    snapshot = state.get_when_change()
    assert isinstance(snapshot, dict)


def test_call_when_change(ctx):
    @ctx.call_when_change()
    def child4_clone(snapshot, _):
        assert isinstance(snapshot, dict)
        raise zproc.ProcessExit()


###


def test_get_when(state):
    snapshot = state.get_when(lambda s: s.get("flag") is True)
    assert snapshot["flag"] is True


def test_call_when(ctx):
    @ctx.call_when(lambda s: s.get("flag") is True)
    def child1_clone(snapshot, _):
        assert snapshot["flag"] is True
        raise zproc.ProcessExit()


###


def test_get_when_equal(state):
    snapshot = state.get_when_equal("flag", True)
    assert snapshot["flag"]


def test_call_when_equal(ctx):
    @ctx.call_when_equal("flag", True)
    def child2_clone(snapshot, _):
        assert snapshot["flag"]
        raise zproc.ProcessExit()


###


def test_get_when_not_equal(state):
    snapshot = state.get_when_not_equal("flag", False)
    assert not snapshot.get("flag")


def test_call_when_not_equal(ctx):
    @ctx.call_when_equal("flag", False)
    def child3_clone(snapshot, _):
        assert snapshot["flag"]
        raise zproc.ProcessExit()
