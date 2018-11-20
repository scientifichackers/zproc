import time

import zmq

from zproc import util
from zproc.consts import DEFAULT_ZMQ_RECVTIMEO


class Watcher:
    def __init__(self, server_address: str):
        self._zmq_ctx = zmq.Context()
        self._server_meta = util.get_server_meta(self._zmq_ctx, server_address)
        self._dealer = self._create_dealer()

    def _create_dealer(self) -> zmq.Socket:
        sock = self._zmq_ctx.socket(zmq.DEALER)
        sock.connect(self._server_meta.watch_router)
        return sock

    def go_live(self):
        self._dealer.close()
        self._dealer = self._create_dealer()

    def main(
        self,
        live: bool,
        timeout: float,
        identical_okay: bool,
        circular_okay: bool,
        ident: bytes,
        namespace_bytes: bytes,
    ):
        print("wtf?")
        if timeout is None:
            self._dealer.setsockopt(zmq.RCVTIMEO, DEFAULT_ZMQ_RECVTIMEO)
        else:
            final = time.time() + timeout

        try:
            while True:
                if live:
                    self.go_live()
                if timeout is not None:
                    self._dealer.setsockopt(
                        zmq.RCVTIMEO, int((final - time.time()) * 1000)
                    )

                self._dealer.send(namespace_bytes)
                identical, circular, update = self._dealer.recv_multipart()

                identical = bool(identical)
                circular = bool(circular)

                if identical and not identical_okay:
                    continue

                if circular and not circular_okay:
                    continue

                yield update, identical, circular
        except zmq.error.Again:
            raise TimeoutError("Timed-out while waiting for a state update.")
