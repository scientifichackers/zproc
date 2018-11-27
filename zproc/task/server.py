import multiprocessing
from collections import defaultdict, Callable, deque
from typing import Dict, List

import zmq

from zproc import util, serializer
from zproc.exceptions import RemoteException


class TaskResultServer:
    result_store: Dict[bytes, Dict[int, bytes]]
    pending: Dict[bytes, deque]

    def __init__(self, router: zmq.Socket, result_pull: zmq.Socket):
        """
        The task server serves the results acquired from the workers.

        Such that,
        a result is never lost,
        and can be acquired again, by any of the clients.

        It also lets everyone know when a task's result has arrived.
        """
        self.router = router
        self.result_pull = result_pull

        self.result_store = defaultdict(dict)
        self.pending = defaultdict(deque)

    def recv_request(self):
        ident, chunk_id = self.router.recv_multipart()
        try:
            task_id, index = util.decode_chunk_id(chunk_id)
            # print("request->", task_id, index)
            task_store = self.result_store[task_id]
            try:
                chunk_result = task_store[index]
            except KeyError:
                self.pending[chunk_id].appendleft(ident)
            else:
                self.router.send_multipart([ident, chunk_result])
        except KeyboardInterrupt:
            raise
        except Exception:
            self.router.send_multipart([ident, serializer.dumps(RemoteException())])

    def resolve_pending(self, chunk_id: bytes, chunk_result: bytes):
        pending = self.pending[chunk_id]
        send = self.router.send_multipart
        msg = [None, chunk_result]

        while pending:
            msg[0] = pending.pop()
            send(msg)

    def recv_chunk_result(self):
        chunk_id, chunk_result = self.result_pull.recv_multipart()
        task_id, index = util.decode_chunk_id(chunk_id)
        self.result_store[task_id][index] = chunk_result
        self.resolve_pending(chunk_id, chunk_result)
        # print("stored->", task_id, index)

    def tick(self):
        for sock in zmq.select([self.result_pull, self.router], [], [])[0]:
            if sock is self.router:
                self.recv_request()
            elif sock is self.result_pull:
                self.recv_chunk_result()


def _task_server(send_conn, _bind: Callable):
    with util.socket_factory(zmq.ROUTER, zmq.PULL) as (zmq_ctx, router, result_pull):
        with send_conn:
            try:
                send_conn.send_bytes(
                    serializer.dumps([_bind(router), _bind(result_pull)])
                )
                server = TaskResultServer(router, result_pull)
            except Exception:
                send_conn.send_bytes(serializer.dumps(RemoteException()))
                return
        while True:
            try:
                server.tick()
            except KeyboardInterrupt:
                util.log_internal_crash("Task server")
                return
            except Exception:
                util.log_internal_crash("Task proxy")


# This proxy server is used to forwared task requests to the workers.
#
# This way,
# any client who wishes to get some task done on the workers,
# only needs to have knowlege about the server.
# Clients never need to talk to a worker directly.


def _task_proxy(send_conn, _bind: Callable):
    with util.socket_factory(zmq.PULL, zmq.PUSH) as (zmq_ctx, proxy_in, proxy_out):
        with send_conn:
            try:
                send_conn.send_bytes(
                    serializer.dumps([_bind(proxy_in), _bind(proxy_out)])
                )
            except Exception:
                send_conn.send_bytes(serializer.dumps(RemoteException()))
        try:
            zmq.proxy(proxy_in, proxy_out)
        except Exception:
            util.log_internal_crash("Task proxy")


#
# Helper functions to start servers, and get return values.
#


def _start_server(fn, _bind: Callable):
    recv_conn, send_conn = multiprocessing.Pipe()
    multiprocessing.Process(target=fn, args=[send_conn, _bind]).start()
    with recv_conn:
        return serializer.loads(recv_conn.recv_bytes())


def start_task_server(_bind: Callable) -> List[str]:
    return _start_server(_task_server, _bind)


def start_task_proxy(_bind: Callable) -> List[str]:
    return _start_server(_task_proxy, _bind)
