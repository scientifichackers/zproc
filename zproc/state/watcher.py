import time

import zmq

from zproc import util
from zproc.consts import DEFAULT_ZMQ_RECVTIMEO


class Watcher:
    live = False

    def __init__(self, server_address: str):
        self._zmq_ctx = zmq.Context()
        self._server_meta = util.get_server_meta(self._zmq_ctx, server_address)
        self._dealer = self._create_dealer()

    def _create_dealer(self) -> zmq.Socket:
        dealer = self._zmq_ctx.socket(zmq.DEALER)
        dealer.connect(self._server_meta.watcher_router)
        return dealer

    def go_live(self):
        self._dealer.close()
        self._dealer = self._create_dealer()

    def _main(
        self, live: bool = False, timeout: float = None, identical_okay: bool = False
    ):
        if timeout is None:

            def _update_timeout() -> None:
                pass

        else:
            final = time.time() + timeout

            def _update_timeout() -> None:
                self._dealer.setsockopt(zmq.RCVTIMEO, int((final - time.time()) * 1000))

        if live:
            self.go_live()

        while True:
            _update_timeout()
            before, after, identical = util.loads(self._dealer.recv())
            if identical and not identical_okay:
                continue
            return before, after, identical

    def main(self):
        try:
            return self._main()
        except zmq.error.Again:
            raise TimeoutError("Timed-out while waiting for a state update.")
        finally:
            self._dealer.setsockopt(zmq.RCVTIMEO, DEFAULT_ZMQ_RECVTIMEO)
