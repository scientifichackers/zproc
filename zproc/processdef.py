from functools import wraps
from typing import Callable

import zmq
from tblib import pickling_support

from . import exceptions, util
from .state import State

pickling_support.install()


class ChildProcess:
    exitcode = 0

    def __init__(self, **kwargs):
        self.kwargs = kwargs

        self.pass_context = self.kwargs["pass_context"]
        self.pass_state = self.kwargs["pass_state"]

        self.target_args = self.kwargs["target_args"]
        self.target_kwargs = self.kwargs["target_kwargs"]
        if self.target_args is None:
            self.target_args = {}
        if self.target_kwargs is None:
            self.target_kwargs = {}

        self.main()

    def main(self):
        try:
            target = self.target_runner(self.kwargs["target"])
            serializer = util.get_serializer(self.kwargs["secret_key"])

            if self.pass_context:
                from .context import Context  # this helps avoid a circular import

                return_value = target(
                    Context(
                        self.kwargs["server_address"],
                        namespace=self.kwargs["namespace"],
                        secret_key=self.kwargs["secret_key"],
                    ),
                    *self.target_args,
                    **self.target_kwargs
                )
            elif self.pass_state:
                return_value = target(
                    State(
                        self.kwargs["server_address"],
                        namespace=self.kwargs["namespace"],
                        secret_key=self.kwargs["secret_key"],
                    ),
                    *self.target_args,
                    **self.target_kwargs
                )
            else:
                return_value = target(*self.target_args, **self.target_kwargs)
            # print(return_value)
            with zmq.Context() as zmq_ctx:
                with zmq_ctx.socket(zmq.PAIR) as result_sock:
                    result_sock.connect(self.kwargs["result_address"])
                    util.send(return_value, result_sock, serializer)
        finally:
            util.clean_process_tree(self.exitcode)

    def target_runner(self, target: Callable) -> Callable:
        @wraps(target)
        def wrapper(*args, **kwargs):
            to_catch = tuple(util.convert_to_exceptions(self.kwargs["retry_for"]))
            max_retries = self.kwargs["max_retries"]
            retry_delay = self.kwargs["retry_delay"]
            process_repr = self.kwargs["process_repr"]
            retry_args = self.kwargs["retry_args"]
            retry_kwargs = self.kwargs["retry_kwargs"]

            retries = 0
            while True:
                retries += 1
                try:
                    return target(*args, **kwargs)
                except exceptions.ProcessExit as e:
                    self.exitcode = e.exitcode
                    return None
                except to_catch as e:
                    if max_retries is not None and retries > max_retries:
                        raise e

                    util.handle_process_crash(
                        exc=e,
                        retry_delay=retry_delay,
                        retries=retries,
                        max_retries=max_retries,
                        process_repr=process_repr,
                    )

                    if retry_args is not None:
                        self.target_args = retry_args
                    if retry_kwargs is not None:
                        self.target_kwargs = retry_kwargs

        return wrapper


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
    with zmq.Context() as zmq_ctx, zmq_ctx.socket(
        zmq.PULL
    ) as pull_sock, zmq_ctx.socket(zmq.PUSH) as push_sock:
        pull_sock.connect(pull_address)
        push_sock.connect(push_address)

        serializer = util.get_serializer(secret_key)
        while True:
            try:
                todo = util.recv(pull_sock, serializer)
                if todo is None:  # time to close shop.
                    return
                else:
                    task_detail, chunk_id, pass_state, target, params = todo
                if pass_state:
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
