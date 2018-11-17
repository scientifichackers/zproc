import multiprocessing
from collections import defaultdict, Callable
from multiprocessing.connection import Connection
from typing import Any, Dict, Tuple, List

import zmq

from zproc import util
from zproc.exceptions import RemoteException


class TaskResultServer:
    _active_identity = None  # type:bytes
    _task_store = defaultdict(dict)  # type:Dict[bytes, Dict[int, Any]]

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

    def _recv_req_rep(self):
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
            resp = util.dumps(RemoteException())
        self.router.send_multipart([ident, resp])

    def store_task_result(self):
        chunk_id, result = self.result_pull.recv_multipart()
        task_id, index = util.deconstruct_chunk_id(chunk_id)
        self._task_store[task_id][index] = result
        # print("stored->", task_id, index, time.time())
        self.publisher.send(chunk_id)
        # time.sleep(0.01)

    def _recv_req(self):
        while True:
            for sock, _ in self.poller.poll():
                if sock is self.router:
                    self._recv_req_rep()
                elif sock is self.result_pull:
                    self.store_task_result()

    def main(self):
        try:
            while True:
                try:
                    self._recv_req()
                except KeyboardInterrupt:
                    util.log_internal_crash("Task server")
                    return
                except Exception:
                    util.log_internal_crash("Task server")
        finally:
            self.publisher.close()


# fmt: off
def _task_server(_bind: Callable, send_conn: Connection):
    try:
        with \
                util.create_zmq_ctx() as ctx, \
                ctx.socket(zmq.ROUTER) as router, \
                ctx.socket(zmq.PULL) as result_pull, \
                ctx.socket(zmq.PUB) as pub_ready:
            send_conn.send_bytes(
                util.dumps(
                    [_bind(router), _bind(result_pull), _bind(pub_ready)]
                )
            )
            send_conn.close()
            TaskResultServer(router, result_pull, pub_ready).main()
    except Exception:
        if send_conn.closed:
            util.log_internal_crash("Task proxy")
        else:
            send_conn.send_bytes(util.dumps(RemoteException()))
            send_conn.close()


def start_task_server(_bind: Callable) -> Tuple[multiprocessing.Process, List[str]]:
    recv_conn, send_conn = multiprocessing.Pipe()
    try:
        task_server = multiprocessing.Process(
            target=_task_server, args=[_bind, send_conn]
        )
        task_server.start()
        return task_server, util.loads(recv_conn.recv_bytes())
    finally:
        recv_conn.close()


# This proxy server is used to forwared task requests to the workers.
#
# This way,
# any client who wishes to get some task done on the workers,
# only needs to have knowlege about the server.
# The workers are opaque to them.

# fmt: off
def _task_proxy(_bind: Callable, send_conn: Connection):
    try:
        with \
                util.create_zmq_ctx() as ctx, \
                ctx.socket(zmq.PULL) as proxy_in, \
                ctx.socket(zmq.PUSH) as proxy_out:
            send_conn.send_bytes(util.dumps([_bind(proxy_in), _bind(proxy_out)]))
            send_conn.close()

            zmq.proxy(proxy_in, proxy_out)
    except Exception:
        print(">>>>", send_conn.closed)
        if send_conn.closed:
            util.log_internal_crash("Task proxy")
        else:
            send_conn.send_bytes(util.dumps(RemoteException()))
            send_conn.close()


def start_task_proxy(_bind: Callable) -> Tuple[multiprocessing.Process, List[str]]:
    recv_conn, send_conn = multiprocessing.Pipe()
    try:
        proxy_server = multiprocessing.Process(
            target=_task_proxy, args=[_bind, send_conn]
        )
        proxy_server.start()
        return proxy_server, util.loads(recv_conn.recv_bytes())
    finally:
        recv_conn.close()
