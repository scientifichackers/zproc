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


from time import sleep
from random import random

import zproc

ctx = zproc.Context(wait=True)
ctx.state["count"] = 0


@zproc.atomic
def increment(state, fuzz):

    count = state["count"]
    sleep(fuzz)  # this ensures that this operation is non-atomic
    state["count"] = count + 1

    print(state["count"])


def child(state):
    increment(state, random())


ctx.process_factory(child, count=100)
