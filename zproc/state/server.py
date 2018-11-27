import os
import struct
import time
from bisect import bisect
from collections import defaultdict
from contextlib import contextmanager
from copy import deepcopy
from typing import Any, Dict, List, Tuple

import zmq

from zproc import serializer
from zproc.consts import Cmds, ServerMeta
from zproc.consts import Msgs

RequestType = Dict[Msgs, Any]


class StateServer:
    identity: bytes
    namespace: bytes

    state_map: Dict[bytes, dict]
    state: dict

    history: Dict[bytes, Tuple[List[float], List[List[bytes]]]]
    pending: Dict[bytes, Tuple[bytes, bytes, bool, float]]

    def __init__(
        self,
        state_router: zmq.Socket,
        watch_router: zmq.Socket,
        server_meta: ServerMeta,
    ) -> None:
        self.state_router = state_router
        self.watch_router = watch_router
        self.server_meta = server_meta

        self.dispatch_dict = {
            Cmds.run_fn_atomically: self.run_fn_atomically,
            Cmds.run_dict_method: self.run_dict_method,
            Cmds.get_state: self.send_state,
            Cmds.set_state: self.set_state,
            Cmds.get_server_meta: self.get_server_meta,
            Cmds.ping: self.ping,
            Cmds.time: self.time,
        }
        self.state_map = defaultdict(dict)

        self.history = defaultdict(lambda: ([], []))
        self.pending = {}

    def send_state(self, _):
        """reply with state to the current client"""
        self.reply(self.state)

    def get_server_meta(self, _):
        self.reply(self.server_meta)

    def ping(self, request):
        self.reply((request[Msgs.info], os.getpid()))

    def time(self, _):
        self.reply(time.time())

    def set_state(self, request):
        new = request[Msgs.info]
        with self.mutate_safely():
            self.state_map[self.namespace] = new
            self.reply(True)

    def run_dict_method(self, request):
        """Execute a method on the state ``dict`` and reply with the result."""
        state_method_name, args, kwargs = (
            request[Msgs.info],
            request[Msgs.args],
            request[Msgs.kwargs],
        )
        # print(method_name, args, kwargs)
        with self.mutate_safely():
            self.reply(getattr(self.state, state_method_name)(*args, **kwargs))

    def run_fn_atomically(self, request):
        """Execute a function, atomically and reply with the result."""
        fn = serializer.loads_fn(request[Msgs.info])
        args, kwargs = request[Msgs.args], request[Msgs.kwargs]
        with self.mutate_safely():
            self.reply(fn(self.state, *args, **kwargs))

    def recv_request(self):
        self.identity, request = self.state_router.recv_multipart()
        request = serializer.loads(request)
        try:
            self.namespace = request[Msgs.namespace]
        except KeyError:
            pass
        else:
            self.state = self.state_map[self.namespace]
        self.dispatch_dict[request[Msgs.cmd]](request)

    def reply(self, response):
        # print("server rep:", self.identity, response, time.time())
        self.state_router.send_multipart([self.identity, serializer.dumps(response)])

    @contextmanager
    def mutate_safely(self):
        old = deepcopy(self.state)
        stamp = time.time()

        try:
            yield
        except Exception:
            self.state = self.state_map[self.namespace] = old
            raise

        slot = self.history[self.namespace]
        slot[0].append(stamp)
        slot[1].append(
            [
                self.identity,
                serializer.dumps((old, self.state, stamp)),
                self.state == old,
            ]
        )
        self.resolve_pending()

    def resolve_watcher(
        self,
        w_ident: bytes,
        s_ident: bytes,
        namespace: bytes,
        identical_not_okay: bool,
        only_after: float,
    ) -> bool:
        timestamps, history = self.history[namespace]
        index = bisect(timestamps, only_after) - 1

        while True:
            index += 1
            try:
                ident, update, identical = history[index]
            except IndexError:
                break
            if ident == s_ident:
                continue
            if identical_not_okay and identical:
                continue
            self.watch_router.send_multipart([w_ident, update, bytes(identical)])
            return True

        return False

    def resolve_pending(self):
        pending = self.pending
        if not pending:
            return
        for w_ident in list(pending):
            if self.resolve_watcher(w_ident, *pending[w_ident]):
                del pending[w_ident]

    def recv_watcher(self):
        w_ident, s_ident, namespace, identical_okay, only_after = (
            self.watch_router.recv_multipart()
        )
        self.pending[w_ident] = (
            s_ident,
            namespace,
            not identical_okay,
            *struct.unpack("d", only_after),
        )

    def reset_internal_state(self):
        self.identity = None
        self.namespace = None
        self.state = None

    def tick(self):
        self.resolve_pending()

        for sock in zmq.select([self.watch_router, self.state_router], [], [])[0]:
            if sock is self.state_router:
                self.recv_request()
            elif sock is self.watch_router:
                self.recv_watcher()
