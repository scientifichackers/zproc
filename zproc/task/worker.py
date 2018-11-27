from collections import Iterable
from typing import Union, Callable

import zmq

from zproc import util, serializer
from zproc.consts import EMPTY_MULTIPART
from zproc.exceptions import RemoteException
from zproc.state.state import State
from .map_plus import map_plus


def run_task(
    target: Callable, task: Iterable, state: State
) -> Union[list, RemoteException]:
    params, pass_state, namespace = task
    if pass_state:
        state.namespace = namespace

        def target_with_state(*args, **kwargs):
            return target(state, *args, **kwargs)

        target = target_with_state

    return map_plus(target, *params)


def worker_process(server_address: str, send_conn):
    with util.socket_factory(zmq.PULL, zmq.PUSH) as (zmq_ctx, task_pull, result_push):
        server_meta = util.get_server_meta(zmq_ctx, server_address)

        try:
            task_pull.connect(server_meta.task_proxy_out)
            result_push.connect(server_meta.task_result_pull)
            state = State(server_address)
        except Exception:
            with send_conn:
                send_conn.send_bytes(serializer.dumps(RemoteException()))
        else:
            with send_conn:
                send_conn.send_bytes(b"")

        try:
            while True:
                msg = task_pull.recv_multipart()
                if msg == EMPTY_MULTIPART:
                    return
                chunk_id, target_bytes, task_bytes = msg

                try:
                    task = serializer.loads(task_bytes)
                    target = serializer.loads_fn(target_bytes)

                    result = run_task(target, task, state)
                except KeyboardInterrupt:
                    raise
                except Exception:
                    result = RemoteException()
                result_push.send_multipart([chunk_id, serializer.dumps(result)])
        except Exception:
            util.log_internal_crash("Worker process")
