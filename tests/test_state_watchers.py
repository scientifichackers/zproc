import time

import pytest

import zproc


def _setup_ctx():
    ctx = zproc.Context()

    @ctx._process
    def updater(state):
        state["none"] = None
        state["flag"] = False
        time.sleep(0.1)
        state["avail"] = True
        state["flag"] = True
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
    snap = state.get_when_change()
    assert isinstance(snap, dict)


def test_call_when_change(ctx):
    @ctx.call_when_change()
    def my_process(snap, _):
        assert isinstance(snap, dict)
        raise zproc.ProcessExit()


###


def test_get_when(state):
    snap = state.get_when(lambda s: s.get("flag") is True)
    assert snap["flag"] is True


def test_call_when(ctx):
    @ctx.call_when(lambda s: s.get("flag") is True)
    def my_process(snap, _):
        assert snap["flag"] is True
        raise zproc.ProcessExit()


###


def test_get_when_equal(state):
    snap = state.get_when_equal("flag", True)
    assert snap["flag"]


def test_call_when_equal(ctx):
    @ctx.call_when_equal("flag", True)
    def my_process(snap, _):
        assert snap["flag"]
        raise zproc.ProcessExit()


###


def test_get_when_not_equal(state):
    snap = state.get_when_not_equal("flag", False)
    assert snap.get("flag") is not False


def test_call_when_not_equal(ctx):
    @ctx.call_when_not_equal("flag", False)
    def my_process(snap, _):
        assert snap["flag"] is not False
        raise zproc.ProcessExit()


###


def test_get_when_none(state):
    snap = state.get_when_none("none")
    assert snap.get("none") is None


def test_call_when_none(ctx):
    @ctx.call_when_none("none")
    def my_process(snap, _):
        assert snap.get("none") is None
        raise zproc.ProcessExit()


###


def test_get_when_not_none(state):
    snap = state.get_when_not_none("none")
    assert snap["none"] is not None


def test_call_when_not_none(ctx):
    @ctx.call_when_not_none("none")
    def my_process(snap, _):
        assert snap["none"] is not None
        raise zproc.ProcessExit()


###


def test_get_when_avail(state):
    snap = state.get_when_available("avail")
    assert "avail" in snap


def test_call_when_avail(ctx):
    @ctx.call_when_available("avail")
    def my_process(snap, _):
        assert "avail" in snap
        raise zproc.ProcessExit()
