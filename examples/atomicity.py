"""
Shows how much ZProc is resillient to race conditions.
Complete with a fuzz! (Thanks to Raymond's talk on the Concurrency)

Spawns 100 processes that do non-atomic operation (incrementation) on state.
Since the operations are run using ".atomic()", they magically avoid race conditions!

Expected Output:

1
2
3
.
.

100
"""
from random import random
from time import sleep

import zproc

ctx = zproc.Context(wait=True)
ctx.state["count"] = 0


@zproc.atomic
def increment(snap):
    count = snap["count"]

    sleep(random())

    snap["count"] = count + 1
    print(snap["count"])


def child1(state):
    increment(state)


ctx.spawn(child1, count=10)
