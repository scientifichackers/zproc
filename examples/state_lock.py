"""
Demonstration of state-locking

# Expected output

main: acquire state lock
main: sleeping for 5
child: try to read state..
main: release state lock
child: got state {'foo': 'bar', 'foobar': 'barfoo'}

"""

from time import sleep

import zproc


def reader(state: zproc.ZeroState, props):
    while True:
        print('reader: try to read state..')
        print('reader: got state', state)


def writer(state: zproc.ZeroState, props):
    with state.lock_state() as locked_state:
        locked_state['count'] += 1
        name = 'writer' + str(locked_state['count'])

        print(name + ': acquire state lock')

        locked_state['foo'] = 'bar'
        locked_state['foobar'] = 'barfoo'

        print(name + ': sleeping for 1')
        sleep(1)
        print(name + ': release state lock')


if __name__ == '__main__':
    ctx = zproc.Context()  # create a context for us to work with

    ctx.process(reader)

    ctx.process_factory(writer, count=10)

    ctx.state['count'] = 0
    ctx.start_all()

    input()

    ctx.stop_all()
