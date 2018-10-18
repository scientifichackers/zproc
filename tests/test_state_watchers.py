import time

import pytest

import zproc


def _setup_ctx():
    ctx = zproc.Context()

    @ctx.process
    def updater(state):
        state["avail"] = True
        state["none"] = None
        time.sleep(1)
        state["true"] = True
        state["none"] = True

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
    snapshot = state.get_when(lambda s: s.get("true") is True)
    assert snapshot["true"] is True


def test_call_when(ctx):
    @ctx.call_when(lambda s: s.get("true") is True)
    def child1_clone(snapshot, _):
        assert snapshot["true"] is True
        raise zproc.ProcessExit()


###


def test_get_when_equal(state):
    snapshot = state.get_when_equal("true", True)
    assert snapshot["true"]


def test_call_when_equal(ctx):
    @ctx.call_when_equal("true", True)
    def child2_clone(snapshot, _):
        assert snapshot["true"]
        raise zproc.ProcessExit()


###


def test_get_when_not_equal(state):
    snapshot = state.get_when_not_equal("true", False)
    assert snapshot.get("true") is not False


def test_call_when_not_equal(ctx):
    @ctx.call_when_not_equal("true", False)
    def child3_clone(snapshot, _):
        assert snapshot["true"] is not False
        raise zproc.ProcessExit()


###


def test_get_when_none(state):
    snapshot = state.get_when_none("none")
    assert snapshot.get("none") is None


def test_call_when_none(ctx):
    @ctx.call_when_none("none")
    def child3_clone(snapshot, _):
        assert snapshot.get("none") is None
        raise zproc.ProcessExit()


###


def test_get_when_not_none(state):
    snapshot = state.get_when_not_none("none")
    assert snapshot["none"] is not None


def test_call_when_not_none(ctx):
    @ctx.call_when_not_none("none")
    def child3_clone(snapshot, _):
        assert snapshot["none"] is not None
        raise zproc.ProcessExit()


###


def test_get_when_avail(state):
    snapshot = state.get_when_available("avail")
    assert "avail" in snapshot


def test_call_when_avail(ctx):
    @ctx.call_when_available("avail")
    def child3_clone(snapshot, _):
        assert "avail" in snapshot
        raise zproc.ProcessExit()
