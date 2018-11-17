"""
A random sync test, by generating random numbers into the state.

# Expected output

num gen: 0.9335641557984383

...<bunch o crazy numbers>...

listener: foo is between 0.6 and 0.61, so I awake
num gen: <some crazy number>
listener: I set STOP to True
listener: exit
num gen: STOP was set to True, so lets exit
num gen: exit

"""
import random

import zproc


def num_listener(state, low, high):
    # blocks until num is between the specified range
    state.get_when(lambda state: low < state.get("num") < high)

    print("listener: foo is between {0} and {1}, so I awake".format(low, high))

    state["STOP"] = True
    print("listener: I set STOP to True")

    print("listener: I exit")


if __name__ == "__main__":
    ctx = zproc.Context()  # create a context for us to work with
    state = ctx.state

    state.setdefault("num", 0)  # set the default value, just to be safe

    # give the context some processes to work with
    # also give some props to the num listener
    ctx.spawn(num_listener, args=[0.6, 0.601])

    while True:
        if state.get("STOP"):
            print("num gen: STOP was set to True, so lets exit")
            break
        else:
            num = random.random()
            state["num"] = num

            print("num gen:", num)

    print("num gen: I exit")
