"""
A demonstration of all synchronization techniques zproc has to offer


# Expected output

main: child processes started
main: I set flag1
.get_when(lambda s: s.get("flag1") is True) -> {'flag1': True, 'flag2': False}
.get_when_change() -> {'flag1': True, 'flag2': False}
.get_when_equal('flag1', True) -> True
.get_when_not_equal('flag1', False) -> True
main: I set flag2
main: I exit
.get_when_change("flag1", exclude=True) -> {'flag1': True, 'flag2': True}
.get_when_change("flag2") -> True

"""

from time import sleep

import zproc


def child1(state):
    val = state.get_when(lambda s: s.get("flag1") is True)
    print('.get_when(lambda s: s.get("flag1") is True) ->', val)


def child2(state):
    val = state.get_when_equal("flag1", True)
    print(".get_when_equal('flag1', True) ->", val)


def child3(state):
    val = state.get_when_not_equal("flag1", False)
    print(".get_when_not_equal('flag1', False) ->", val)


def child4(state):
    val = state.get_when_change("flag1")
    print(".get_when_change() ->", val)


def child5(state):
    val = state.get_when_change("flag2")
    print('.get_when_change("flag2") ->', val)


def child6(state):
    val = state.get_when_change("flag1", exclude=True)
    print('.get_when_change("flag1", exclude=True) ->', val)


if __name__ == "__main__":
    ctx = zproc.Context(background=True)  # background waits for all processes to finish

    ctx.state.setdefault("flag1", False)
    ctx.state.setdefault("flag2", False)

    ctx.process_factory(child1, child2, child3, child4, child5, child6)

    print("main: child processes started")

    sleep(1)

    ctx.state["flag1"] = True
    print("main: I set flag1")

    sleep(1)

    ctx.state["flag2"] = True
    print("main: I set flag2")

    print("main: I exit")
