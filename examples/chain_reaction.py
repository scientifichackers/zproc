"""
Demonstration of a chain reaction to a state change

# Expected output

main: I set foo to foobar
child1: foo changed, so I wake, now foo = foobar
child1: I set foo to bar
child1: I exit
child2: foo changed to bar, so I wake
child2: I exit

main: I exit
"""
from time import sleep

import zproc


def foo_equals_bar(state):
    return state.get('foo') == 'bar'


# define a child process
def child1(state: zproc.ZeroState):
    val = state.get_when_change('foo')  # wait for foo to change
    print("child1: foo changed, so I wake, now foo =", val)

    state['foo'] = 'bar'  # update bar
    print('child1: I set foo to bar')
    print('child1: I exit')


# define another child process
def child2(state: zproc.ZeroState):
    state.get_state_when(foo_equals_bar)  # wait for bar_equals_bar
    print('child2: foo changed to bar, so I wake')
    print('child2: I exit')


if __name__ == '__main__':
    ctx = zproc.Context()  # create a context for us to work with

    ctx.process_factory(child1, child2)  # give the context some processes to work with
    ctx.start_all()  # start all processes in context

    sleep(2)  # sleep for no reason

    ctx.state['foo'] = 'foobar'  # set initial state
    print('main: I set foo to foobar')

    input()  # wait for user input before exit

    print('main: I exit')
