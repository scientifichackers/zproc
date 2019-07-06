import random
import time

import zproc

NUM_PROCS = 100
NUM_COOKIES = 5


#
# define aotmic operations
#


@zproc.atomic
def decrement(state, key):
    state[key] -= 1


@zproc.atomic
def increment(state, key):
    state[key] += 1


#
# define cookie eater
#


def cookie_eater(ctx):
    state = ctx.create_state()
    increment(state, "ready")

    # some fuzzing
    time.sleep(random.random())

    # passing `start_time=0` gives updates from the very begining,
    # no matter in what space-time we currently are!
    for _ in state.when_change("cookies", count=NUM_COOKIES, start_time=0):
        decrement(state, "cookies")

    increment(state, "done")


#
# Here's where the maigc happens
#

# boilerplate
ctx = zproc.Client(wait=True)
state = ctx.create_state({"cookies": 0, "ready": 0, "done": 0})

# store a handle to receive "ready" from eater
ready = state.when_change("ready", count=NUM_PROCS)

# start some eater processes
eaters = ctx.spawn(cookie_eater, count=NUM_PROCS)
print(eaters)

# wait for all to be ready
ready = list(ready)
print("ready:", ready)
assert len(ready) == NUM_PROCS

# store a handle to receive "done" from eater
done = state.when_change("done", count=NUM_PROCS)

# make some cookies
for _ in range(NUM_COOKIES):
    increment(state, "cookies")

# wait for all to complete
done = list(done)
print("done:", done)
assert len(done) == NUM_PROCS

# finally, check if right amount of cookies were consumed
assert state["cookies"] == NUM_COOKIES - NUM_PROCS * NUM_COOKIES
