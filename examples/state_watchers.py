"""
A demonstration of the numerous ways of "watching" the state.

# Expected output

.get_when_not_equal('flag1', False) -> None

main: I set flag1:
.get_when(lambda s: s.get("flag1") is True) -> {'flag1': True}
.get_when_equal('flag1', True) -> True
.get_when_change() -> {'flag1': True}

main: I set flag2:
.get_when_change("flag1", exclude=True) -> {'flag1': True, 'flag2': True}
.get_when_change("flag2") -> True

"""
from time import sleep

import zproc


def child1(state):
    val = state.when(lambda s: s.get("flag1") is True)
    print('.get_when(lambda s: s.get("flag1") is True) ->', val)


def child2(state):
    val = state.when_equal("flag1", True)
    print(".get_when_equal('flag1', True) ->", val)


def child3(state):
    val = state.when_not_equal("flag1", False)
    print(".get_when_not_equal('flag1', False) ->", val)


def child4(state):
    val = state.when_change()
    print(".get_when_change() ->", val)


def child5(state):
    val = state.when_change("flag2")
    print('.get_when_change("flag2") ->', val)


def child6(state):
    val = state.when_change("flag1", exclude=True)
    print('.get_when_change("flag1", exclude=True) ->', val)


if __name__ == "__main__":
    ctx = zproc.Context(wait=True)

    ctx.spawn(child1, child2, child3, child4, child5, child6)

    sleep(1)

    print("\nmain: I set flag1:")
    ctx.state["flag1"] = True

    sleep(1)

    print("\nmain: I set flag2:")
    ctx.state["flag2"] = True
