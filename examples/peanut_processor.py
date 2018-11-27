"""
Demonstrates how live-ness of events works in ZProc.

Example output:

    Consuming LIVE events:

    PEANUT GEN: 1
    live consumer got: 1
    PEANUT GEN: 2
    PEANUT GEN: 3
    live consumer got: 3
    PEANUT GEN: 4
    PEANUT GEN: 5
    live consumer got: 5
    PEANUT GEN: 6
    PEANUT GEN: 7
    live consumer got: 7
    PEANUT GEN: 8
    PEANUT GEN: 9
    PEANUT GEN: 10
    live consumer got: 10
    PEANUT GEN: 11
    PEANUT GEN: 12
    live consumer got: 12
    PEANUT GEN: 13
    PEANUT GEN: 14
    live consumer got: 14
    PEANUT GEN: 15
    PEANUT GEN: 16
    live consumer got: 16
    PEANUT GEN: 17
    PEANUT GEN: 18
    live consumer got: 18
    PEANUT GEN: 19
    PEANUT GEN: 20
    live consumer got: 20
    PEANUT GEN: 21

    Consuming non-LIVE events:

    non-live consumer got: 1
    PEANUT GEN: 22
    PEANUT GEN: 23
    non-live consumer got: 2
    PEANUT GEN: 24
    PEANUT GEN: 25
    non-live consumer got: 3
    PEANUT GEN: 26
    PEANUT GEN: 27
    non-live consumer got: 4
    PEANUT GEN: 28
    PEANUT GEN: 29
    non-live consumer got: 5
    PEANUT GEN: 30
    PEANUT GEN: 31
    non-live consumer got: 6
    PEANUT GEN: 32
    PEANUT GEN: 33
    non-live consumer got: 7
    PEANUT GEN: 34
    PEANUT GEN: 35
    non-live consumer got: 8
    PEANUT GEN: 36
    PEANUT GEN: 37
    non-live consumer got: 9
    PEANUT GEN: 38
    PEANUT GEN: 39
    non-live consumer got: 10
    PEANUT GEN: 40
    PEANUT GEN: 41

    Consuming a hybrid of LIVE and non-LIVE events:

    hybrid consumer got: 11
    PEANUT GEN: 42
    PEANUT GEN: 43
    hybrid consumer got: 42
    PEANUT GEN: 44
    PEANUT GEN: 45
    hybrid consumer got: 44
    PEANUT GEN: 46
    PEANUT GEN: 47
    hybrid consumer got: 46
    PEANUT GEN: 48
    PEANUT GEN: 49
    hybrid consumer got: 48
    PEANUT GEN: 50
    PEANUT GEN: 51
    hybrid consumer got: 50
    PEANUT GEN: 52
    PEANUT GEN: 53
    hybrid consumer got: 52
    PEANUT GEN: 54
    PEANUT GEN: 55
    hybrid consumer got: 54
    PEANUT GEN: 56
    PEANUT GEN: 57
    hybrid consumer got: 56
    PEANUT GEN: 58
    PEANUT GEN: 59
    hybrid consumer got: 58
    PEANUT GEN: 60
    PEANUT GEN: 61
    PEANUT GEN: 62
    PEANUT GEN: 63
    PEANUT GEN: 64
    PEANUT GEN: 65
    PEANUT GEN: 66
    PEANUT GEN: 67
    PEANUT GEN: 68
    ...
"""
from time import sleep

import zproc

ctx = zproc.Context()
state = ctx.state

state["peanuts"] = 0


@zproc.atomic
def inc_peanuts(snap):
    snap["peanuts"] += 1
    print("PEANUT GEN:", snap["peanuts"])


@ctx._process
def peanut_gen(state):
    while True:
        inc_peanuts(state)
        sleep(1)


print("\nConsuming LIVE events:\n")

for _ in range(10):
    num = state.get_when_change("peanuts", live=True)
    print("live consumer got:", num)

    sleep(2)

print("\nConsuming non-LIVE events:\n")

for _ in range(10):
    num = state.get_when_change("peanuts", live=False)
    print("non-live consumer got:", num)

    sleep(2)

print("\nConsuming a hybrid of LIVE and non-LIVE events:\n")

for _ in range(10):
    num = state.get_when_change("peanuts", live=False)
    print("hybrid consumer got:", num)

    state.go_live()

    sleep(2)

print("Exit")
