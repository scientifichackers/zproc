"""
Expected output:

<ZeroProcess pid: 2555 target: <function cookie_eater at 0x7f5b4542c9d8> uuid: e74521ae-76ca-11e8-bd1f-7c7a912e12b5>
<ZeroProcess pid: 2556 target: <function cookie_baker at 0x7f5b4542c950> uuid: e74521ae-76ca-11e8-bd1f-7c7a912e12b5>
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

ctx = zproc.Context(background=True)  # background waits for all processes to finish
ctx.state["cookies"] = 0


@zproc.atomic
def eat_cookie(state):
    state["cookies"] -= 1
    print("nom nom nom")


@zproc.atomic
def bake_cookie(state):
    state["cookies"] += 1
    print("Here's a cookie!")


@ctx.call_when_change("cookies")
def cookie_eater(state):
    eat_cookie(state)


@ctx.process
def cookie_baker(state):
    for i in range(5):
        bake_cookie(state)


print(cookie_eater)
print(cookie_baker)
