import os
from collections import defaultdict, deque
from contextlib import contextmanager
from copy import deepcopy
from typing import Any, Dict, Deque, Tuple

import zmq

from zproc import serializer
from zproc.consts import Commands, ServerMeta
from zproc.consts import Msgs

RequestType = Dict[Msgs, Any]


class StateServer:
    _ident: bytes
    _namespace: bytes
    _state: dict

    def __init__(
        self,
        state_router: zmq.Socket,
        watch_router: zmq.Socket,
        server_meta: ServerMeta,
    ) -> None:
        self.state_router = state_router
        self.watch_router = watch_router
        self.server_meta = server_meta

        self.poller = zmq.Poller()
        self.poller.register(self.state_router)
        self.poller.register(self.watch_router)

        self._dispatch_dict = {
            Commands.run_fn_atomically: self.run_fn_atomically,
            Commands.run_dict_method: self.run_dict_method,
            Commands.get_state: self.send_state,
            Commands.set_state: self.set_state,
            Commands.get_server_meta: self.get_server_meta,
            Commands.ping: self.ping,
        }
        self._state_store: Dict[bytes, dict] = defaultdict(dict)
        self._watch_queue_store: Dict[bytes, Deque[Tuple[bytes, bytes]]] = defaultdict(
            deque
        )

    def _recv_req(self):
        self._ident, req = self.state_router.recv_multipart()
        req = serializer.loads(req)
        try:
            self._namespace = req[Msgs.namespace]
        except KeyError:
            pass
        else:
            self._state = self._state_store[self._namespace]
        self._dispatch_dict[req[Msgs.cmd]](req)

    def tick(self):
        for sock, _ in self.poller.poll():
            if sock is self.state_router:
                self._recv_req()
            elif sock is self.watch_router:
                ident, sender, namespace = sock.recv_multipart()
                self._watch_queue_store[namespace].append((ident, sender))

    def reply(self, resp):
        # print("server rep:", self._active_ident, resp, time.time())
        self.state_router.send_multipart([self._ident, serializer.dumps(resp)])

    def send_state(self, _):
        """reply with state to the current client"""
        self.reply(self._state)

    def get_server_meta(self, _):
        self.reply(self.server_meta)

    def ping(self, req):
        self.reply({Msgs.info: [req[Msgs.info], os.getpid()]})

    @contextmanager
    def mutate_state(self):
        old = deepcopy(self._state)

        try:
            yield
        except Exception:
            self._state_store[self._namespace] = old
            raise

        identical = bytes(self._state == old)
        update = serializer.dumps((old, self._state))

        for ident, sender in self._watch_queue_store[self._namespace]:
            self.watch_router.send_multipart(
                [ident, identical, bytes(self._ident == sender), update]
            )

        self._watch_queue_store[self._namespace].clear()

    def set_state(self, request):
        new = request[Msgs.info]
        with self.mutate_state():
            self._state_store[self._namespace] = new
            self.reply(True)

    def run_dict_method(self, request):
        """Execute a method on the state ``dict`` and reply with the result."""
        state_method_name, args, kwargs = (
            request[Msgs.info],
            request[Msgs.args],
            request[Msgs.kwargs],
        )
        # print(method_name, args, kwargs)
        with self.mutate_state():
            self.reply(getattr(self._state, state_method_name)(*args, **kwargs))

    def run_fn_atomically(self, req):
        """Execute a function, atomically and reply with the result."""
        fn = serializer.loads_fn(req[Msgs.info])
        args, kwargs = req[Msgs.args], req[Msgs.kwargs]

        with self.mutate_state():
            self.reply(fn(self._state, *args, **kwargs))

    def reset_state(self):
        self._ident = None
        self._namespace = None
        self._state = None
