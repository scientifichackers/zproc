"""
Expected output:

Process - pid: 10815 target: '__main__.cookie_eater' ppid: 10802 is_alive: True exitcode: None
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


@zproc.atomic
def eat_cookie(snap):
    """Eat a cookie."""
    snap["cookies"] -= 1
    print("nom nom nom")


@zproc.atomic
def bake_cookie(snap):
    """Bake a cookie."""
    snap["cookies"] += 1
    print("Here's a cookie!")


ctx = zproc.Context(wait=True)
state = ctx.create_state()
state["cookies"] = 0


@ctx.spawn
def cookie_eater(ctx):
    """Eat cookies as they're baked."""
    state = ctx.create_state()
    state["ready"] = True

    for _ in state.when_change("cookies"):
        eat_cookie(state)


# wait for that process
next(state.when_available("ready"))

# finally, get to work.
print(cookie_eater)
for _ in range(5):
    bake_cookie(state)

