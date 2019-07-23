import os
import struct
import time
from bisect import bisect
from collections import defaultdict
from contextlib import contextmanager
from copy import deepcopy
from typing import Dict, List, Tuple, Optional

import glom
import zmq

from zproc import serializer
from zproc.consts import Cmds, ServerMeta
from zproc.consts import Msgs


class StateServer:
    identity: Optional[bytes]
    namespace: Optional[bytes]

    state_map: Dict[bytes, dict]
    state: Optional[dict]

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
            Cmds.get_server_meta: self.get_server_meta,
            Cmds.ping: self.ping,
            Cmds.time: self.time,
        }
        self.state_map = defaultdict(dict)

        self.history = defaultdict(lambda: ([], []))
        self.pending = {}

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
        self.solve_pending_watchers()

    def get_server_meta(self, _):
        self.reply(self.server_meta)

    def ping(self, request):
        self.reply((request[Msgs.info], os.getpid()))

    def time(self, _):
        self.reply(time.time())

    def run_fn_atomically(self, request):
        """Execute a function, atomically and reply with the result."""
        fn_bytes, path = request[Msgs.info]
        fn = serializer.loads_fn(fn_bytes)
        args, kwargs = request[Msgs.args], request[Msgs.kwargs]

        with self.mutate_safely():
            if path is None:
                state = self.state
            else:
                state = glom.glom(self.state, path)
            self.reply(fn(state, *args, **kwargs))

    def recv_watcher(self):
        watcher_id, state_id, namespace, identical_okay, only_after = (
            self.watch_router.recv_multipart()
        )
        self.pending[watcher_id] = (
            state_id,
            namespace,
            not identical_okay,
            *struct.unpack("d", only_after),
        )

    def solve_watcher(
        self,
        watcher_id: bytes,
        state_id: bytes,
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
            if ident == state_id:
                continue
            if identical_not_okay and identical:
                continue
            self.watch_router.send_multipart([watcher_id, update, bytes(identical)])
            return True

        return False

    def solve_pending_watchers(self):
        pending = self.pending
        if not pending:
            return
        for watcher_id in list(pending):
            if self.solve_watcher(watcher_id, *pending[watcher_id]):
                del pending[watcher_id]

    def reset_internal_state(self):
        self.identity = None
        self.namespace = None
        self.state = None

    def tick(self):
        self.solve_pending_watchers()

        for sock in zmq.select([self.watch_router, self.state_router], [], [])[0]:
            if sock is self.state_router:
                self.recv_request()
            else:
                self.recv_watcher()
