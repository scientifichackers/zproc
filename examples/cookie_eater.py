from time import sleep

import zproc

ctx = zproc.Context(background=True)
ctx.state["cookies"] = 0


def eat_cookie(state):
    state["cookies"] -= 1


def make_cookie(state):
    state["cookies"] += 1


@ctx.call_when_change("cookies")
def cookie_eater(state):
    state.atomic(eat_cookie)
    print("child: nom nom nom")


sleep(0.5)  # wait for the process to stabilize
print(cookie_eater.pid)  # The "Process" pid.

for i in range(5):
    ctx.state.atomic(make_cookie)
    print("main: I made a cookie!")
