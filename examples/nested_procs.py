"""
Demonstration of how to handle nested processes
"""

import zproc

ctx = zproc.Context(background=True)
print('level0', ctx.state)

ctx.state['msg'] = 'hello from level0'


@ctx.processify()
def child1(state):
    print('level1:', state)
    state['msg'] = 'hello from level1'

    ctx = zproc.Context(background=True, uuid=state.uuid)

    @ctx.processify()
    def child2(state):
        print('level2:', state)
        state['msg'] = 'hello from level2'

        ctx = zproc.Context(uuid=state.uuid)

        @ctx.processify()
        def child3(state):
            print('level3:', state)
