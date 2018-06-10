"""
Shows how much ZProc is resillient to race conditions.

Spawns 500 processes that do non-atomic operation (incrementation) on state.
Since the operations are wrapped inside @state.taskify(), they magically avoid race conditions!

Expected Output:

1
2
3
.
.

500

"""

import zproc

ctx = zproc.Context(background=True)

ctx.state['count'] = 0


def child(state: zproc.ZeroState):
    @state.taskify()
    def increment(state):
        state['count'] += 1
        return state['count']

    print(increment())


ctx.process_factory(child, count=500)
