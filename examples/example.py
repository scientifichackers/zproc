from time import sleep

import zproc


def child1(state, props):
    state.get_when_change('foo')
    print("child1: foo got updated, so I wake")

    state['bar'] = 'xxx'
    print('child1: I set bar to xxx')
    print('child1: I exit')


def bar_equals_xxx(state):
    return state.get('bar') == 'xxx'


def child2(state, props):
    state.get_when(bar_equals_xxx)
    print('child2: bar changed to xxx, so I wake')
    print('child2: I exit')


ctx = zproc.Context()

ctx.process_factory(child1, child2, props='hello!')
ctx.start_all()

sleep(1)

ctx.state['foo'] = 'foobar'
print('child0: I set foo to foobar')

input()

print('child0: I exit')