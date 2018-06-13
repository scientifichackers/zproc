"""
Expected output:

<ZeroProcess pid: 1733 target: <function cookie_baker at 0x7f82ead3b2f0> uuid: a847e6a0-6ef8-11e8-99b9-7c7a912e12b5>
<ZeroProcess pid: 1732 target: <function Context._get_watcher_decorator.<locals>.watcher_decorator.<locals>.watcher_proc at 0x7f82ead3b268> uuid: a847e6a0-6ef8-11e8-99b9-7c7a912e12b5>
Here's a cookie!
Here's a cookie!
Here's a cookie!
nom nom nom
Here's a cookie!
nom nom nom
Here's a cookie!
nom nom nom
nom nom nom
nom nom nom
"""

import zproc

ctx = zproc.Context(background=True)
ctx.state["cookies"] = 0


def eat_cookie(state):
    state["cookies"] -= 1
    print("nom nom nom")


def bake_cookie(state):
    state["cookies"] += 1
    print("Here's a cookie!")


@ctx.call_when_change("cookies")
def cookie_eater(state):
    state.atomic(eat_cookie)


@ctx.processify()
def cookie_baker(state):
    for i in range(5):
        state.atomic(bake_cookie)


print(cookie_baker)
print(cookie_eater)
