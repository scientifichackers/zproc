import zproc


def test_namespaces():
    state = zproc.Client().create_state()

    state.namespace = "test1"
    state["foo"] = 10

    assert state == {"foo": 10}

    state.namespace = "test2"
    state["bar"] = 10

    assert state == {"bar": 10}

    state.namespace = "test3"
    assert state == {}
