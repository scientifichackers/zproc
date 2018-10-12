import sys
from pprint import pprint

import zproc

ctx = zproc.Context()


@ctx.process
def child1(state):
    snapshot = state.get_when(lambda s: s.get("flag1") is True)
    assert snapshot["flag1"] is True


@ctx.call_when(lambda s: s.get("flag1") is True)
def child1_clone(snapshot, _):
    assert snapshot["flag1"] is True

    sys.exit(0)


@ctx.process
def child2(state):
    snapshot = state.get_when_equal("flag1", True)
    assert snapshot["flag1"]


@ctx.call_when_equal("flag1", True)
def child2_clone(snapshot, _):
    assert snapshot["flag1"]

    sys.exit(0)


@ctx.process
def child3(state):
    snapshot = state.get_when_not_equal("flag1", False)
    assert not snapshot.get("flag1")


@ctx.call_when_equal("flag1", True)
def child3_clone(snapshot, _):
    assert snapshot["flag1"]

    sys.exit(0)


@ctx.process
def child4(state):
    snapshot = state.get_when_change()
    assert isinstance(snapshot, dict)


@ctx.call_when_change()
def child4_clone(snapshot, _):
    assert isinstance(snapshot, dict)

    sys.exit(0)


@ctx.process
def child5(state):
    snapshot = state.get_when_change("flag2")
    assert snapshot["flag2"]


@ctx.call_when_change("flag2")
def child5_clone(snapshot, _):
    assert snapshot["flag2"]

    sys.exit(0)


@ctx.process
def child6(state):
    snapshot = state.get_when_change("flag1", exclude=True)
    assert snapshot == {"flag1": True, "flag2": True}


@ctx.call_when_change("flag1", exclude=True)
def child6_clone(snapshot, _):
    assert snapshot == {"flag1": True, "flag2": True}

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
