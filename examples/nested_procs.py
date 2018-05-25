"""
Demonstration of how zproc can handle nested processes
"""

import os

import zproc

ctx = zproc.Context(background=True)
ctx.state['foo'] = 'bar'
print('parent:', os.getpid(), os.getppid())


@ctx.processify()
def child1(state):
    print('child:', os.getpid(), os.getppid(), state)

    inner_ctx = zproc.Context(background=True)
    inner_ctx.state['foo'] = 'foobar'

    @inner_ctx.processify()
    def child2(state):
        print('nested child:', os.getpid(), os.getppid(), state)

        @inner_ctx.processify()
        def child3(state):
            print('nested-nested child:', os.getpid(), os.getppid(), state)
