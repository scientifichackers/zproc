from time import sleep

import zproc


def child1(state, props):
    print('child1', state.get_state_when_change('foo'))

    print('child1 unblocked!')


def child2(state, props):
    print('child2', state.get_state_when_change('bar'))

    print('child2 unblocked!')

ctx = zproc.Context()

procs = ctx.process_factory(child2, child1, props='hello!')
print(procs)
ctx.start_all()

print(ctx.state)

sleep(2)

ctx.state['foo'] = 'foobar'
print(ctx.state)

sleep(2)

ctx.state['bar'] = 'foo'
print(ctx.state)

input()
