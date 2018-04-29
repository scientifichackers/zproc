from time import sleep

import zproc


def foo_equals_bar(state):
    return state.get('foo') == 'bar'


# define a child process
def child1(state, props):
    state.get_when_change('foo')  # wait for foo to change
    print("child1: foo got updated, so I wake")

    state['foo'] = 'bar'  # update bar
    print('child1: I set foo to bar')
    print('child1: I exit')


# define another child process
def child2(state, props):
    state.get_when(foo_equals_bar)  # wait for bar_equals_bar
    print('child2: foo changed to bar, so I wake')
    print('child2: I exit')


ctx = zproc.Context()  # create a context for us to work with

ctx.process_factory(child1, child2)  # give the context some processes to work with
ctx.start_all()  # start all processes in context

sleep(1)  # sleep for no reason

ctx.state['foo'] = 'foobar'  # set initial state
print('child0: I set foo to foobar')

input()  # wait for user input before exit

print('child0: I exit')
