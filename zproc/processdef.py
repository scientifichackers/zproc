"""
Contains the definitions for the mainloop(s) of processes/workers.
"""
import pickle
import signal
from typing import Union, Callable

import zmq
from tblib import pickling_support

from zproc import util
from zproc.server import Server
from zproc.state import State

# installs pickle-ing support for exceptions.
pickling_support.install()


def server_process(*args, **kwargs):
    server = Server(*args, **kwargs)

    def signal_handler(*args):
        server.close()
        util.clean_process_tree(*args)

    signal.signal(signal.SIGTERM, signal_handler)
    server.mainloop()


def child_process(
    server_address: str,
    target: Callable,
    process_repr: str,
    stateful: bool,
    args: tuple,
    kwargs: dict,
    retry_for: tuple,
    retry_delay: Union[int, float],
    max_retries: Union[None, bool],
    retry_args: Union[None, tuple],
    retry_kwargs: Union[None, dict],
    result_address: str,
):
    if args is None:
        args = ()
    if kwargs is None:
        kwargs = {}

    if stateful:
        state = State(server_address)
        ctx = state._zmq_ctx
    else:
        state = None
        ctx = zmq.Context()
    result_sock = ctx.socket(zmq.PUSH)
    result_sock.connect(result_address)

    to_catch = tuple(util.convert_to_exceptions(retry_for))

    tries = 0
    while True:
        tries += 1

        try:
            if stateful:
                return_value = target(state, *args, **kwargs)
            else:
                return_value = target(*args, **kwargs)
        except to_catch as e:
            if (max_retries is not None) and (tries > max_retries):
                raise e
            else:
                util.handle_crash(e, retry_delay, tries, max_retries, process_repr)

                if retry_args is not None:
                    args = retry_args
                if retry_kwargs is not None:
                    kwargs = retry_kwargs
        else:
            result_sock.send_pyobj(return_value, protocol=pickle.HIGHEST_PROTOCOL)
            break

    result_sock.close()


# Please don't try to understand this mess.
# It can be done in 5 lines using `functools.partial()`.
# But that has a performance penalty, so here is some artwork :)


def _stateful_worker(state, i, a, k, target, _a, _k):
    if i is None and a is None and k is None:
        return []
    elif i is None and a is None:
        return [target(state, *_a, **kitem, **_k) for kitem in k]
    elif a is None and k is None:
        return [target(state, iitem, *_a, **_k) for iitem in i]
    elif k is None and i is None:
        return [target(state, *aitem, *_a, **_k) for aitem in a]
    elif i is None:
        return [target(state, *aitem, *_a, **kitem, **_k) for aitem, kitem in zip(a, k)]
    elif a is None:
        return [target(state, iitem, *_a, **kitem, **_k) for iitem, kitem in zip(i, k)]
    elif k is None:
        return [target(state, iitem, *aitem, *_a, **_k) for iitem, aitem in zip(i, a)]
    else:
        return [
            target(state, iitem, *aitem, *_a, **kitem, **_k)
            for iitem, aitem, kitem in zip(i, a, k)
        ]


def _stateless_worker(i, a, k, target, _a, _k):
    if i is None and a is None and k is None:
        return []
    elif i is None and a is None:
        return [target(*_a, **kitem, **_k) for kitem in k]
    elif a is None and k is None:
        return [target(iitem, *_a, **_k) for iitem in i]
    elif k is None and i is None:
        return [target(*aitem, *_a, **_k) for aitem in a]
    elif i is None:
        return [target(*aitem, *_a, **kitem, **_k) for aitem, kitem in zip(a, k)]
    elif a is None:
        return [target(iitem, *_a, **kitem, **_k) for iitem, kitem in zip(i, k)]
    elif k is None:
        return [target(iitem, *aitem, *_a, **_k) for iitem, aitem in zip(i, a)]
    else:
        return [
            target(iitem, *aitem, *_a, **kitem, **_k)
            for iitem, aitem, kitem in zip(i, a, k)
        ]


def process_map_worker(state: State, push_address: str, pull_address: str):
    ctx = state._zmq_ctx

    pull_sock = ctx.socket(zmq.PULL)
    pull_sock.connect(pull_address)

    push_sock = ctx.socket(zmq.PUSH)
    push_sock.connect(push_address)

    while True:
        try:
            todo = pull_sock.recv_pyobj()

            if todo == 0:  # time to close shop.
                return
            else:
                task_detail, chunk_detail, i, a, k, stateful, target, _a, _k = todo
            # print(i, a, k, index, stateful, target, _a, _k)
            if stateful:
                result = _stateful_worker(state, i, a, k, target, _a, _k)
            else:
                result = _stateless_worker(i, a, k, target, _a, _k)
            push_sock.send_pyobj(
                (task_detail, chunk_detail, result), protocol=pickle.HIGHEST_PROTOCOL
            )
        except KeyboardInterrupt:
            pull_sock.close()
            push_sock.close()
            return
        except:
            # proxy the exception back to parent.
            push_sock.send_pyobj(util.RemoteException())
