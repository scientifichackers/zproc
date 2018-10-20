import os
from typing import Union, Callable, Optional

import zmq
from tblib import pickling_support

from . import exceptions, util
from .state import State

pickling_support.install()


def child_process(
    server_address: str,
    target: Callable,
    process_repr: str,
    namespace: str,
    secret_key: Optional[str],
    stateful: bool,
    pass_context: bool,
    args: tuple,
    kwargs: dict,
    retry_for: tuple,
    retry_delay: Union[int, float],
    max_retries: Optional[bool],
    retry_args: Optional[tuple],
    retry_kwargs: Optional[dict],
    result_address: str,
):
    if args is None:
        args = ()
    if kwargs is None:
        kwargs = {}

    if pass_context:
        from .context import Context

        ctx = Context(server_address, namespace=namespace, secret_key=secret_key)
        state = ctx.state  # type: Union[State, None]
    elif stateful:
        state = State(server_address, namespace=namespace, secret_key=secret_key)
    else:
        state = None

    if state is None:
        zmq_ctx = util.create_zmq_ctx()
    else:
        zmq_ctx = state._zmq_ctx
    result_sock = zmq_ctx.socket(zmq.PUSH)
    result_sock.connect(result_address)

    serialier = util.get_serializer(secret_key)

    to_catch = tuple(util.convert_to_exceptions(retry_for))

    tries = 0
    while True:
        tries += 1

        try:
            if pass_context:
                return_value = target(ctx, *args, **kwargs)
            elif stateful:
                return_value = target(state, *args, **kwargs)
            else:
                return_value = target(*args, **kwargs)
        except exceptions.ProcessExit as e:
            os._exit(e.status)
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
            util.send(return_value, result_sock, serialier)
            result_sock.close()

            util.clean_process_tree(0)


def _stateful_worker(state, target, i, a, _a, k, _k):
    if i is None and a is None and k is None:
        return []
    elif i is None and a is None:
        return [target(state, *_a, **ik, **_k) for ik in k]
    elif a is None and k is None:
        return [target(state, ii, *_a, **_k) for ii in i]
    elif k is None and i is None:
        return [target(state, *ai, *_a, **_k) for ai in a]
    elif i is None:
        return [target(state, *ai, *_a, **ki, **_k) for ai, ki in zip(a, k)]
    elif a is None:
        return [target(state, ii, *_a, **ki, **_k) for ii, ki in zip(i, k)]
    elif k is None:
        return [target(state, ii, *ai, *_a, **_k) for ii, ai in zip(i, a)]
    else:
        return [target(state, ii, *ai, *_a, **ki, **_k) for ii, ai, ki in zip(i, a, k)]


def _stateless_worker(target, i, a, _a, k, _k):
    if i is None and a is None and k is None:
        return []
    elif i is None and a is None:
        return [target(*_a, **ki, **_k) for ki in k]
    elif a is None and k is None:
        return [target(ii, *_a, **_k) for ii in i]
    elif k is None and i is None:
        return [target(*ai, *_a, **_k) for ai in a]
    elif i is None:
        return [target(*ai, *_a, **ki, **_k) for ai, ki in zip(a, k)]
    elif a is None:
        return [target(ii, *_a, **ki, **_k) for ii, ki in zip(i, k)]
    elif k is None:
        return [target(ii, *ai, *_a, **_k) for ii, ai in zip(i, a)]
    else:
        return [target(ii, *ai, *_a, **ki, **_k) for ii, ai, ki in zip(i, a, k)]


def process_map_worker(
    state: State, push_address: str, pull_address: str, secret_key: str
):
    serializer = util.get_serializer(secret_key)

    ctx = state._zmq_ctx

    pull_sock = ctx.socket(zmq.PULL)
    pull_sock.connect(pull_address)

    push_sock = ctx.socket(zmq.PUSH)
    push_sock.connect(push_address)

    while True:
        try:
            todo = util.recv(pull_sock, serializer)

            if todo is None:  # time to close shop.
                return
            else:
                task_detail, chunk_id, stateful, target, params = todo

            if stateful:
                result = _stateful_worker(state, target, *params)
            else:
                result = _stateless_worker(target, *params)

            util.send([task_detail, chunk_id, result], push_sock, serializer)
        except KeyboardInterrupt:
            pull_sock.close()
            push_sock.close()
            return
        except Exception:
            # proxy the exception back to parent.
            util.send(exceptions.RemoteException(), push_sock, serializer)
