"""
This is meant to test resilience and stability of state watchers.

Its hard to test automatically, so we must inspect it ourselves.
"""

import random
import time

import zproc

TIMEOUT = 10000
SLOW = True

ctx = zproc.Context()
ctx.state["foobar"] = 0


def wait_and_stop():
    try:
        test_process.wait(TIMEOUT)
    except TimeoutError:
        test_process.stop()
    print("\n" * 5, "-" * 10, "\n" * 5)
    time.sleep(1)


@zproc.atomic
def inc(state):
    state["foobar"] += 1


@ctx.process
def generator(state):
    while True:
        inc(state)
        if SLOW:
            time.sleep(random.random())


print("LIVE:")


@ctx.process
def test_process(state):
    while True:
        print(state.get_when_change("foobar"), end=",", flush=True)
        if SLOW:
            time.sleep(random.random())


wait_and_stop()
print("BUFFERED:")


@ctx.process
def test_process(state):
    while True:
        print(state.get_when_change("foobar", live=False), end=",", flush=True)
        if SLOW:
            time.sleep(random.random())


wait_and_stop()
print("LIVE:")


@ctx.call_when_change("foobar", stateful=False)
def test_process(foobar):
    print(foobar, end=",", flush=True)
    if SLOW:
        time.sleep(random.random())


wait_and_stop()
print("BUFFERED:")


@ctx.call_when_change("foobar", live=False, stateful=False)
def test_process(foobar):
    print(foobar, end=",", flush=True)
    if SLOW:
        time.sleep(random.random())


wait_and_stop()
