import sys
from pprint import pprint

import zproc

ctx = zproc.Context()


@ctx.process
def child1(state):
    val = state.get_when(lambda s: s.get("flag1") is True)
    assert val["flag1"] is True


@ctx.call_when(lambda s: s.get("flag1") is True)
def child1_clone(val, _):
    assert val["flag1"] is True

    sys.exit(0)


@ctx.process
def child2(state):
    val = state.get_when_equal("flag1", True)
    assert val is True


@ctx.call_when_equal("flag1", True)
def child2_clone(val, _):
    assert val is True

    sys.exit(0)


@ctx.process
def child3(state):
    val = state.get_when_not_equal("flag1", False)
    assert val is None


@ctx.call_when_equal("flag1", True)
def child3_clone(val, _):
    assert val is True

    sys.exit(0)


@ctx.process
def child4(state):
    val = state.get_when_change()
    assert isinstance(val, dict)


@ctx.call_when_change()
def child4_clone(val, _):
    assert isinstance(val, dict)

    sys.exit(0)


@ctx.process
def child5(state):
    val = state.get_when_change("flag2")
    assert val is True


@ctx.call_when_change("flag2")
def child5_clone(val, _):
    assert val is True

    sys.exit(0)


@ctx.process
def child6(state):
    val = state.get_when_change("flag1", exclude=True)
    assert val == {"flag1": True, "flag2": True}


@ctx.call_when_change("flag1", exclude=True)
def child6_clone(val, _):
    assert val == {"flag1": True, "flag2": True}

    sys.exit(0)


@ctx.process
def updater(state):
    state["flag1"] = True
    state["flag2"] = True


pprint(ctx.process_list)
for i, p in enumerate(ctx.process_list):
    try:
        print(p.wait())
    except zproc.ProcessWaitError:
        pass
    print(i)
