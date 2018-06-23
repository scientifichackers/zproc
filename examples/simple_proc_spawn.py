"""
Demonstration of simple process spawn

# Expected output

child1: 30631
child2: 30632
[<zproc.zproc.ZeroProcess object at 0x7f7929460c18>, <zproc.zproc.ZeroProcess object at 0x7f7926fc4c50>, <zproc.zproc.ZeroProcess object at 0x7f7926fd4a20>, <zproc.zproc.ZeroProcess object at 0x7f7926fd4a90>]
child2: True
{30632, 30633, 30636, 30631}
child3: 30633
child3: True
child3: True
child4: 30636
child4: True
child4: True
child4: True
Press Enter to stop: ↵
[<zproc.zproc.ZeroProcess object at 0x7f7929460c18>, <zproc.zproc.ZeroProcess object at 0x7f7926fc4c50>, <zproc.zproc.ZeroProcess object at 0x7f7926fd4a20>, <zproc.zproc.ZeroProcess object at 0x7f7926fd4a90>]
set()
"""

import os

from time import sleep

import zproc


def child1():
    print("child1:", os.getpid())
    sleep(5)


def child2(state):
    print("child2:", os.getpid())
    print("child2:", state.get("foo") == "bar")
    sleep(5)


def child3(state, props):
    print("child3:", os.getpid())
    print("child3:", state.get("foo") == "bar")
    print("child3:", props == "test_props")
    sleep(5)


def child4(state, props, proc):
    print("child4:", os.getpid())
    print("child4:", state.get("foo") == "bar")
    print("child4:", props == "test_props")
    print("child4:", proc.pid == os.getpid())
    sleep(5)


if __name__ == "__main__":
    ctx = zproc.Context()

    ctx.state.update({"foo": "bar"})

    ctx.process_factory(
        child1, child2, child3, child4, props="test_props", start=False
    )  # notice start=False

    ctx.start_all()
    print(ctx.process_list)
