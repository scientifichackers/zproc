"""
A random sync test, by generating random numbers into the state.

# Expected output

num gen: 0.9335641557984383

...<bunch o crazy numbers>...

listener: foo is between 0.6 and 0.61, so I awake
num gen: 0.6653150239830506
listener: I set STOP to True
listener: exit
num gen: STOP was set to True, so lets exit
num gen: exit

"""

import random

import zproc


# random num generator process
def random_num_gen(state: zproc.ZeroState, props):
    while True:
        num = random.random()
        state['foo'] = num

        print('num gen:', num)

        if state.get('STOP'):
            print('num gen: STOP was set to True, so lets exit')
            break

    print('num gen: exit')


def foo_between(state, low, high):
    return low < state.get('foo') < high


# num listener process
def num_listener(state: zproc.ZeroState, props):
    state.get_when(foo_between, props[0], props[1])  # blocks until foo is between the specified range

    print('listener: foo is between {0} and {1}, so I awake'.format(props[0], props[1]))

    state['STOP'] = True
    print('listener: I set STOP to True')

    print('listener: exit')


ctx = zproc.Context()  # create a context for us to work with

# give the context some processes to work with
# also give some props to the num listener
ctx.process_factory(random_num_gen, num_listener, props=(0.6, 0.61))

ctx.start_all()  # start all processes in context

input()
