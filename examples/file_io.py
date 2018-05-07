"""
Demonstration of how you can do concurrent FileIO operations using ZProc.
"""
import os
from collections import deque

import zproc

NUM_PROCS = 25
lock_queue = 'file_lock_queue'


def acquire_lock(state, pid):
    with state.lock_state() as lstate:
        lstate[lock_queue].appendleft(pid)

    state.get_when_equal(pid, 1)


def release_lock(state, pid):
    state[pid] = 2


def file_manager(state: zproc.ZeroState):
    while True:
        try:
            with state.lock_state() as lstate:
                pid = lstate[lock_queue].pop()

            state[pid] = 1  # allow child to acquire lock
            state.get_when_equal(pid, 2)  # wait for lock to be released
        except IndexError:
            state.get_when_not_equal(lock_queue, deque())


def child(state: zproc.ZeroState):
    pid = os.getpid()

    acquire_lock(state, pid)

    with open('proc_count.txt', 'r') as fp:
        count = int(fp.read())

    count += 1

    with open('proc_count.txt', 'w') as fp:
        fp.write(str(count))

    release_lock(state, pid)

    state['finished'] += 1
    print('child: finished writing:', count)


if __name__ == '__main__':
    ctx = zproc.Context()

    with open('proc_count.txt', 'w') as fp:
        fp.write('0')

    ctx.state.setdefault('finished', 0)
    ctx.state.setdefault(lock_queue, deque())

    ctx.process(file_manager).start()  # start file manager

    ctx.process_factory(child, count=NUM_PROCS)  # start the file writers
    ctx.start_all()

    ctx.state.get_when_equal('finished', NUM_PROCS)

    print('All Done!')
