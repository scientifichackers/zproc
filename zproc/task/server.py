import multiprocessing
from collections import defaultdict, Callable
from multiprocessing.connection import Connection
from typing import Any, Dict, List

import zmq

from zproc import util, serializer
from zproc.exceptions import RemoteException


class TaskResultServer:
    _active_identity = None  # type:bytes

    def __init__(
        self, router: zmq.Socket, result_pull: zmq.Socket, publisher: zmq.Socket
    ):
        """
        The task server serves the results acquired from the workers.

        Such that,
        a result is never lost,
        and can be acquired again, by any of the clients.

        It also lets everyone know when a task's result has arrived.
        """
        self.router = router
        self.result_pull = result_pull
        self.publisher = publisher

        self.poller = zmq.Poller()
        self.poller.register(self.result_pull, zmq.POLLIN)
        self.poller.register(self.router, zmq.POLLIN)

        self._task_store: Dict[bytes, Dict[int, Any]] = defaultdict(dict)

    def recv_req(self):
        ident, chunk_id = self.router.recv_multipart()
        resp = b""
        try:
            task_id, index = util.deconstruct_chunk_id(chunk_id)
            # print("req for chunk->", task_id, index)
            try:
                resp = self._task_store[task_id][index]
            except KeyError:
                pass
        except KeyboardInterrupt:
            raise
        except Exception:
            resp = serializer.dumps(RemoteException())
        self.router.send_multipart([ident, resp])

    def recv_task_result(self):
        chunk_id, result = self.result_pull.recv_multipart()
        task_id, index = util.deconstruct_chunk_id(chunk_id)
        self._task_store[task_id][index] = result
        # print("stored->", task_id, index, time.time())
        self.publisher.send(chunk_id)
        # time.sleep(0.01)

    def tick(self):
        for sock, _ in self.poller.poll():
            if sock is self.router:
                self.recv_req()
            elif sock is self.result_pull:
                self.recv_task_result()


def _task_server(_bind: Callable, send_conn: Connection):
    with util.socket_factory(zmq.ROUTER, zmq.PULL, zmq.PUB) as (
        zmq_ctx,
        router,
        result_pull,
        pub_ready,
    ):
        with send_conn:
            try:
                send_conn.send_bytes(
                    serializer.dumps(
                        [_bind(router), _bind(result_pull), _bind(pub_ready)]
                    )
                )
                server = TaskResultServer(router, result_pull, pub_ready)
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


def start_task_server(_bind: Callable) -> List[str]:
    recv_conn, send_conn = multiprocessing.Pipe()

    with recv_conn:
        task_server = multiprocessing.Process(
            target=_task_server, args=[_bind, send_conn]
        )
        task_server.start()
        return serializer.loads(recv_conn.recv_bytes())


# This proxy server is used to forwared task requests to the workers.
#
# This way,
# any client who wishes to get some task done on the workers,
# only needs to have knowlege about the server.
# The workers are opaque to them.


def _task_proxy(_bind: Callable, send_conn: Connection):
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


def start_task_proxy(_bind: Callable) -> List[str]:
    recv_conn, send_conn = multiprocessing.Pipe()

    with recv_conn:
        proxy_server = multiprocessing.Process(
            target=_task_proxy, args=[_bind, send_conn]
        )
        proxy_server.start()
        return serializer.loads(recv_conn.recv_bytes())
