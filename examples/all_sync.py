"""
A test of all synchronization techniques ZProc has to offer


# Expected output

main: I set foo to foobar
main: child processes started
main: I set foo to xxx
.get_when_change() > {'foo': 'xxx'}
.get_when_not_equal('foo', 'foobar') > xxx
.get_when_change('foo') > xxx
main: I set foo to bar
main: I exit
.get_when(foo_equals_bar) > {'foo': 'bar'}
.get_when_equal('foo', 'bar') > bar

"""
from time import sleep

import zproc


def foo_equals_bar(state):
    return state.get('foo') == 'bar'


def child1(state: zproc.ZeroState):
    val = state.get_when(foo_equals_bar)
    print(".get_when(foo_equals_bar) >", val)


def child2(state: zproc.ZeroState):
    val = state.get_when_equal('foo', 'bar')
    print(".get_when_equal('foo', 'bar') >", val)


def child3(state: zproc.ZeroState):
    val = state.get_when_not_equal('foo', 'foobar')
    print(".get_when_not_equal('foo', 'foobar') >", val)


def child4(state: zproc.ZeroState):
    val = state.get_when_change()
    print(".get_when_change() >", val)


def child5(state: zproc.ZeroState):
    val = state.get_when_change('foo')
    print(".get_when_change('foo') >", val)


if __name__ == '__main__':
    ctx = zproc.Context(background=True)  # create a context for us to work with

    ctx.state['foo'] = 'foobar'

    print('main: I set foo to foobar')

    ctx.process_factory(child1, child2, child3, child4, child5)  # give the context some processes to work with

    iter(ctx.state)

    print('main: child processes started')

    sleep(1)  # sleep for no reason

    ctx.state['foo'] = 'xxx'
    print('main: I set foo to xxx')

    sleep(1)  # sleep for no reason

    ctx.state['foo'] = 'bar'
    print('main: I set foo to bar')

    print('main: I exit')