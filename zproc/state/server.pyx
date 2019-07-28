import os
import struct
import time
from collections import defaultdict
from contextlib import contextmanager
from copy import deepcopy

import glom
import numpy as np
import zmq

from zproc import serializer
from zproc.consts import Cmds, ServerMeta
from zproc.consts import Msgs

cimport numpy as np


cdef class DoubleList:
    cdef get(self):
        return self.arr[:self.nexti]

    def __init__(self):
        self.nexti = 0
        self.arr = np.empty(1024)

    cdef append(self, double item):
        cdef double[:] copy

        if self.nexti >= len(self.arr):
            arr = np.empty(2 * self.nexti)
            arr[:self.nexti] = self.arr
        else:
            arr = self.arr

        arr[self.nexti] = item
        self.nexti += 1


cdef class ServerData:
    def __init__(self):
        self.data = defaultdict(lambda : [{}, DoubleList(), [], {}])

    cdef set_state(self, dict state):
        self.data[self.namespace][0] = state

    cdef set_namespace(self, bytes value):
        self.namespace = value
        self.state, self.timeline, self.history, self.pending = self.data[value]


cdef class StateServer:
    def __init__(
        self,
        state_router: zmq.Socket,
        watch_router: zmq.Socket,
        server_meta: ServerMeta,
    ):
        self.state_router = state_router
        self.watch_router = watch_router
        self.server_meta = server_meta

        self.dispatch_dict = {
            Cmds.run_fn_atomically: self.run_fn_atomically,
            Cmds.get_server_meta: self.get_server_meta,
            Cmds.ping: self.ping,
            Cmds.time: self.time,
        }

        self.data = ServerData()

    def recv_request(self):
        self.identity, request = self.state_router.recv_multipart()
        request = serializer.loads(request)
        self.data.set_namespace(request[Msgs.namespace])
        self.dispatch_dict[request[Msgs.cmd]](request)

    cdef reply(self, response):
        self.state_router.send_multipart(
            [self.identity, serializer.dumps(response)]
        )

    def get_server_meta(self, _):
        self.reply(self.server_meta)

    def ping(self, request):
        self.reply((request[Msgs.info], os.getpid()))

    def time(self, _):
        self.reply(time.time())

    @contextmanager
    def mutate_safely(self):
        old = deepcopy(self.data.state)
        stamp = time.time()

        try:
            yield
        except Exception:
            self.data.set_state(old)
            raise

        self.data.timeline.append(stamp)
        self.data.history.append(
            (self.identity, serializer.dumps([old, self.data.state, stamp])),
        )
        self.solve_pending_watchers()

    def run_fn_atomically(self, request):
        """Execute a function, atomically and reply with the result."""
        # ccdef bytes fn_bytes
        # ccdef dict state

        fn_bytes, path = request[Msgs.info]
        fn = serializer.loads_fn(fn_bytes)
        args, kwargs = request[Msgs.args], request[Msgs.kwargs]

        with self.mutate_safely():
            arg = self.data.state
            if path is not None:
                arg = glom.glom(arg, path)
            self.reply(fn(arg, *args, **kwargs))

    def recv_watcher(self):
        watcher_id, state_id, namespace, only_after = (
            self.watch_router.recv_multipart()
        )
        self.data.pending[watcher_id] = (
            state_id, namespace, *struct.unpack("d", only_after)
        )

    cdef solve_watcher(
        self,
        bytes watcher_id,
        bytes state_id,
        bytes namespace,
        double only_after,
    ):
        # cdef bytes ident, old, new
        # cdef int
        timeline = self.data.timeline.get()
        if not timeline:
            return
        index = np.searchsorted(timeline, only_after, side='right') - 1
        # print(list(timeline), only_after, index)
        stamp = timeline[index]
        # timestamps, history = self.history[namespace]
        # index = bisect(timestamps, only_after) - 1

        while True:
            index += 1
            try:
                owner, data = self.data.history[index]
            except IndexError:
                break
            if owner == state_id:
                continue
            self.watch_router.send_multipart([watcher_id, data])
            return True

        return False

    def solve_pending_watchers(self):
        # cdef bytes watcher_id
        # cdef (char*, char*, float) info

        if not self.data.pending:
            return
        for watcher_id in list(self.data.pending):
            info = self.data.pending[watcher_id]
            if self.solve_watcher(watcher_id, info[0], info[1], info[2]):
                del self.data.pending[watcher_id]

    cdef tick(self):
        self.solve_pending_watchers()

        for sock in zmq.select([self.watch_router, self.state_router], [], [])[0]:
            if sock is self.state_router:
                self.recv_request()
            else:
                self.recv_watcher()
