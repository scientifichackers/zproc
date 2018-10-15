import zproc


ctx = zproc.Context()
state = ctx.state


def test1():
    state.namespace = "test1"
    state["foo"] = 10

    assert state == {"foo": 10}


def test2():
    state.namespace = "test2"
    state["bar"] = 10

    assert state == {"bar": 10}


def test3():
    state.namespace = "test3"
    assert state == {}
