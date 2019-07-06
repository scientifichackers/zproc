"""
Demonstration of how to handle nested processes
"""
import zproc

ctx = zproc.Client(wait=True)
print("level0", ctx.state)

ctx.state["msg"] = "hello from level0"


@ctx._process
def child1(state):
    print("level1:", state)
    state["msg"] = "hello from level1"

    ctx = zproc.Client(state.address, wait=True)

    @ctx._process
    def child2(state):
        print("level2:", state)
        state["msg"] = "hello from level2"

        ctx = zproc.Client(state.address, wait=True)

        @ctx._process
        def child3(state):
            print("level3:", state)
