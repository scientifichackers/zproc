"""
A test of all synchronization techniques ZProc has to offer


# Expected output

main: I set foo to foobar
main: child processes started
main: I set foo to xxx
child5: something changed, so I wake
child6: foo changed, so I wake, now state = {'foo': 'xxx'}
child3: foo doesnt equal foobar, so I wake, now foo = xxx
child4: foo changed, so I wake, now foo = xxx
main: I set foo to bar
child1: foo_equals_bar so I wake, now state =  {'foo': 'bar'}
child2: foo equals bar, so I wake

child0: I exit
"""
from time import sleep

import zproc


def foo_equals_bar(state):
    return state.get('foo') == 'bar'


def child1(state: zproc.ZeroState, props):
    val = state.get_when(foo_equals_bar)
    print("child1: foo_equals_bar so I wake, now state = ", val)


def child2(state: zproc.ZeroState, props):
    state.get_when_equal('foo', 'bar')
    print("child2: foo equals bar, so I wake")


def child3(state: zproc.ZeroState, props):
    val = state.get_when_not_equal('foo', 'foobar')
    print('child3: foo doesnt equal foobar, so I wake, now foo =', val)


def child4(state: zproc.ZeroState, props):
    val = state.get_val_when_change('foo')
    print('child4: foo changed, so I wake, now foo =', val)


def child5(state: zproc.ZeroState, props):
    state.get_when_change()
    print('child5: something changed, so I wake')


def child6(state: zproc.ZeroState, props):
    val = state.get_when_change('foo')
    print('child6: foo changed, so I wake, now state =', val)


if __name__ == '__main__':
    ctx = zproc.Context()  # create a context for us to work with

    ctx.state['foo'] = 'foobar'
    print('main: I set foo to foobar')

    ctx.process_factory(child1, child2, child3, child4, child5, child6)  # give the context some processes to work with
    ctx.start_all()  # start all processes in context

    iter(ctx.state)

    print('main: child processes started')

    sleep(2)  # sleep for no reason

    ctx.state['foo'] = 'xxx'  # set initial state
    print('main: I set foo to xxx')

    sleep(2)  # sleep for no reason

    ctx.state['foo'] = 'bar'  # set initial state
    print('main: I set foo to bar')

    input()  # wait for user input before exit

    print('child0: I exit')
