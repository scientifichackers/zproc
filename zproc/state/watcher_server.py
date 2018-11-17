import multiprocessing
from collections import defaultdict
from multiprocessing.connection import Connection
from typing import Dict, Callable

import zmq

from zproc import util
from zproc.consts import WatcherCommands, Msgs
from zproc.exceptions import RemoteException


class WatcherServer:
    _ident: bytes
    _namespace: bytes
    _clients: set

    def __init__(self, router: zmq.Socket, pair: zmq.Socket):
        self.router = router
        self.pair = pair
        self.poller = zmq.Poller()

        self._client_store: Dict[bytes, set] = defaultdict(dict)
        self._dispatch_dict = {
            WatcherCommands.register: self.register,
            WatcherCommands.unregister: self.unregister,
        }

    def register(self, _):
        self._clients.add(self._ident)

    def unregister(self, _):
        self._clients.remove(self._ident)

    def _recv_req(self):
        self._ident, req = self.router.recv_multipart()
        resp = b""
        try:
            self._namespace = req[Msgs.namespace]
            self._clients = self._client_store[self._namespace]
            self._dispatch_dict[req[Msgs.cmd]](req)
        except KeyboardInterrupt:
            raise
        except Exception:
            resp = util.dumps(RemoteException())
        self.router.send_multipart([self._ident, resp])

    def recv_update(self):
        ident, namespace, update = self.pair.recv_multipart()
        to_consider = self._client_store[namespace].copy()
        try:
            to_consider.remove(ident)
        except KeyError:
            pass
        for ident in to_consider:
            self.router.send_multipart([ident, update])

    def _reset_req_state(self):
        self._ident = None
        self._namespace = None
        self._clients = None

    def recv_req(self):
        while True:
            for sock, _ in self.poller.poll():
                if sock is self.router:
                    try:
                        self._recv_req()
                    finally:
                        self._reset_req_state()
                elif sock is self.pair:
                    self.recv_update()

    def main(self):
        while True:
            try:
                self.recv_req()
            except KeyboardInterrupt:
                util.log_internal_crash("Task server")
                return
            except Exception:
                util.log_internal_crash("Task server")


# fmt: off
def _watcher_server(_bind: Callable, pair_address: str, send_conn: Connection):
    try:
        with \
                util.create_zmq_ctx() as ctx, \
                ctx.socket(zmq.ROUTER) as router, \
                ctx.socket(zmq.PAIR) as pair:
            pair.connect(pair_address)
            send_conn.send_bytes(util.dumps(_bind(router)))
            send_conn.close()
            WatcherServer(router, pair).main()
    except Exception:
        if send_conn.closed:
            util.log_internal_crash("Task proxy")
        else:
            send_conn.send_bytes(util.dumps(RemoteException()))
            send_conn.close()


def start_watcher_server(_bind: Callable, pair_address: str) -> str:
    recv_conn, send_conn = multiprocessing.Pipe()
    try:
        watcher_server = multiprocessing.Process(
            target=_watcher_server, args=[_bind, pair_address, send_conn]
        )
        watcher_server.start()
        return util.loads(recv_conn.recv_bytes())
    finally:
        recv_conn.close()
