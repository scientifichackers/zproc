import random
import time

import zproc

MAX_ITER = 100
SLOW = False

ctx = zproc.Context()
state = ctx.create_state({"foobar": 0})


@zproc.atomic
def inc(snap):
    snap["foobar"] += 1


@ctx.spawn
def generator(ctx):
    state = ctx.create_state()
    while True:
        inc(state)
        if SLOW:
            time.sleep(random.random())


print("LIVE:")


@ctx.spawn
def test_process(ctx):
    state = ctx.create_state()

    for snap in state.when_change("foobar", live=True, count=MAX_ITER):
        print(snap, end=",", flush=True)

        if SLOW:
            time.sleep(random.random())
    print()


test_process.wait()
print("BUFFERED:")


@ctx.spawn
def test_process(ctx):
    state = ctx.create_state()

    for snap in state.when_change("foobar", live=False, count=MAX_ITER):
        print(snap, end=",", flush=True)

        if SLOW:
            time.sleep(random.random())

    print()


test_process.wait()
