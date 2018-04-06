from time import sleep

import zproc


def child1(state, props):
    print('child1', state.get_state_when_change('foo'))


    def child2(state, props):
        print('child2', state.get_state_when_change('bar'))
        print('child2 unblocked!')

    ctx = zproc.Context()

    ctx.process(child2)
    ctx.start_all()

    sleep(1)

    ctx.state['bar'] = 'ddd'
    print('child1 unblocked!')


ctx = zproc.Context()

procs = ctx.process_factory(child1, props='hello!')
ctx.start_all()

print(ctx.state)

sleep(1)

ctx.state['foo'] = 'foobar'
print(ctx.state)

sleep(1)

ctx.state['bar'] = 'foo'
print(ctx.state)

input()
