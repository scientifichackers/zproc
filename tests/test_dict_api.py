"""
Test the dict API, offered by State
"""
import pytest

import zproc

ctx = zproc.Context()


@pytest.fixture
def pydict() -> dict:
    return {"foo": "foo", "bar": "bar"}


@pytest.fixture
def state(pydict) -> zproc.State:
    ctx.state.set(pydict)
    return ctx.state


def test_update(state, pydict):
    state.update({"zoo": 1, "dog": 2})
    pydict.update({"zoo": 1, "dog": 2})

    assert state == pydict


def test__contains__(state, pydict):
    assert ("foo" in state) == ("foo" in pydict)
    assert ("foo" not in state) == ("foo" not in pydict)


def test__delitem__(state, pydict):
    del state["foo"]
    del pydict["foo"]

    assert state == pydict


def test__eq__(state, pydict):
    assert (state == {"bar": "bar"}) == (pydict == {"bar": "bar"})


def test__getitem__(state, pydict):
    assert state["bar"] == pydict["bar"]


def test__iter__(state, pydict):
    for k1, k2 in zip(state, pydict):
        assert k1 == k2


def test__len__(state, pydict):
    assert len(state) == len(pydict)


def test__ne__(state, pydict):
    assert (state != {"bar": "bar"}) == (pydict != {"bar": "bar"})


def test__setitem__(state, pydict):
    state["foo"] = 2
    pydict["foo"] = 2
    assert state == pydict


def test_clear(state, pydict):
    state.clear()
    pydict.clear()
    assert state == pydict


def test_dict_inbuilt(state, pydict):
    assert dict(state) == dict(pydict)


def test_copy(state, pydict):
    assert state.copy() == pydict.copy()


def test_get(state, pydict):
    assert state.get("xxx", []) == pydict.get("xxx", [])
    assert state.get("foo") == pydict.get("foo")


def test_items(state, pydict):
    for i, j in zip(state.items(), pydict.items()):
        assert i[0] == j[0] and i[1] == j[1]


def test_values(state, pydict):
    for i, j in zip(state.values(), pydict.values()):
        assert i == j


def test_keys(state, pydict):
    for i, j in zip(state.keys(), pydict.keys()):
        assert i == j


def test_setdefault(state, pydict):
    state.setdefault("zzz", None)
    pydict.setdefault("zzz", None)

    assert state == pydict


def test_pop(state, pydict):
    assert state.pop("foo") == pydict.pop("foo")
    assert state == pydict


def test_popitem(state, pydict):
    assert state.popitem() == pydict.popitem()
    assert state == pydict
