import os
import time
from collections import defaultdict
from contextlib import contextmanager
from copy import deepcopy
from typing import Any, Dict

import zmq

from zproc import util
from zproc.consts import Commands, ServerMeta
from zproc.consts import Msgs
from zproc.exceptions import RemoteException

RequestType = Dict[Msgs, Any]


class StateServer:
    _ident: bytes
    _namespace: bytes
    _state: dict

    _state_store: Dict[bytes, dict] = defaultdict(dict)

    def __init__(
        self, router: zmq.Socket, publisher: zmq.Socket, server_meta: ServerMeta
    ) -> None:
        self.router = router
        self.publisher = publisher
        self.server_meta = server_meta

        self._dispatch_dict = {
            Commands.run_fn_atomically: self.run_fn_atomically,
            Commands.run_dict_method: self.run_dict_method,
            Commands.get_state: self.send_state,
            Commands.set_state: self.set_state,
            Commands.get_server_meta: self.get_server_meta,
            Commands.ping: self.ping,
        }

    def _recv_req(self):
        self._ident, req = self.router.recv_multipart()
        req = util.loads(req)
        try:
            self._namespace = req[Msgs.namespace]
        except KeyError:
            pass
        else:
            self._state = self._state_store[self._namespace]
        self._dispatch_dict[req[Msgs.cmd]](req)

    def _reply(self, resp):
        # print("server rep:", self._active_ident, resp, time.time())
        self.router.send_multipart([self._ident, util.dumps(resp)])

    def send_state(self, _):
        """reply with state to the current client"""
        self._reply(self._state)

    def get_server_meta(self, _):
        self._reply(self.server_meta)

    def ping(self, req):
        self._reply({Msgs.info: [req[Msgs.info], os.getpid()]})

    @contextmanager
    def mutate_state(self):
        old = deepcopy(self._state)

        try:
            yield
        except Exception:
            self._state_store[self._namespace] = old
            raise

        self.publisher.send(
            (
                self._ident
                + self._namespace
                + util.dumps([old, self._state, old == self._state])
            )
        )

    def set_state(self, request):
        new = request[Msgs.info]
        with self.mutate_state():
            self._state_store[self._namespace] = new
            self._reply(True)

    def run_dict_method(self, request):
        """Execute a method on the state ``dict`` and reply with the result."""
        state_method_name, args, kwargs = (
            request[Msgs.info],
            request[Msgs.args],
            request[Msgs.kwargs],
        )
        # print(method_name, args, kwargs)
        with self.mutate_state():
            self._reply(getattr(self._state, state_method_name)(*args, **kwargs))

    def run_fn_atomically(self, req):
        """Execute a function, atomically and reply with the result."""
        fn = util.loads_fn(req[Msgs.info])
        args, kwargs = req[Msgs.args], req[Msgs.kwargs]

        with self.mutate_state():
            self._reply(fn(self._state, *args, **kwargs))

    def main(self):
        while True:
            try:
                self._recv_req()
            except KeyboardInterrupt:
                raise
            except Exception:
                try:
                    self._reply(RemoteException())
                except TypeError:  # when active_ident is None
                    util.log_internal_crash("State server")
            finally:
                self._ident = None
                self._namespace = None
                self._state = None
