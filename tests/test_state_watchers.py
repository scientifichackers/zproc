import time

import pytest

import zproc


@pytest.fixture
def state():
    ctx = zproc.Client()

    @ctx.spawn()
    def updater(ctx):
        state = ctx.create_state()

        state["none"] = None
        state["flag"] = False
        time.sleep(0.1)
        state["avail"] = True
        state["flag"] = True
        state["none"] = True

    return ctx.create_state()


###


def test_when_change(state):
    it = state.when_change()
    assert isinstance(next(it), dict)


###


def test_when(state):
    it = state.when(lambda s: s.get("flag") is True)
    assert next(it)["flag"] is True


###


def test_when_equal(state):
    it = state.when_equal("flag", True)
    assert next(it)["flag"]


###


def test_when_not_equal(state):
    it = state.when_not_equal("flag", False)
    assert next(it).get("flag") is not False


###


def test_when_none(state):
    it = state.when_none("none")
    assert next(it).get("none") is None


###


def test_when_not_none(state):
    it = state.when_not_none("none")
    assert next(it)["none"] is not None


###


def test_when_avail(state):
    it = state.when_available("avail")
    assert "avail" in next(it)
