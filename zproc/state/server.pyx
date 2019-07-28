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
from zproc.consts import ServerMeta
from zproc.consts import Msgs
from zproc.consts.enums cimport Cmds

cimport numpy as np


cdef class DoubleList:
    def __init__(self):
        self.nexti = 0
        self.arr = np.empty(1024)

    cdef double[:] get(self):
        return self.arr[:self.nexti]

    cdef append(self, double item):
        cdef double[:] arr

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
        self.data = ServerData()

    cdef reply(self, object response):
        self.state_router.send_multipart([self.identity, serializer.dumps(response)])

    cdef recv_request(self):
        cdef dict request
        cdef bytes data
        cdef int cmd

        self.identity, data = self.state_router.recv_multipart()

        request = serializer.loads(data)
        self.data.set_namespace(request[Msgs.namespace])
        cmd = request[Msgs.cmd]

        if cmd == Cmds.run_fn_atomically:
            self.run_fn_atomically(request)
        elif cmd == Cmds.ping:
            self.reply((request[Msgs.info], os.getpid()))
        elif cmd == Cmds.get_server_meta:
            self.reply(self.server_meta)
        elif cmd == Cmds.time:
            self.reply(time.time())
        else:
            raise ValueError(f'Invalid command: "{cmd}"')

    @contextmanager
    def mutate_safely(self):
        cdef dict old, new
        cdef double stamp

        old = deepcopy(self.data.state)
        stamp = time.time()

        try:
            yield
        except Exception:
            self.data.set_state(old)
            raise

        new = self.data.state
        if old == new:
            return

        self.data.timeline.append(stamp)
        self.data.history.append(
            (self.identity, serializer.dumps([old, new, stamp])),
        )
        self.solve_pending_watchers()

    cdef run_fn_atomically(self, dict request):
        """Execute a function, atomically and reply with the result."""
        cdef bytes fn_bytes
        cdef dict state, kwargs
        cdef tuple args

        fn_bytes, path = request[Msgs.info]
        fn = serializer.loads_fn(fn_bytes)
        args, kwargs = request[Msgs.args], request[Msgs.kwargs]

        with self.mutate_safely():
            arg = self.data.state
            if path is not None:
                arg = glom.glom(arg, path)
            self.reply(fn(arg, *args, **kwargs))

    cdef recv_watcher(self):
        cdef bytes watcher_id, state_id, namespace, only_after

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
        cdef int index
        cdef bytes owner, data
        cdef double[:] timeline

        timeline = self.data.timeline.get()
        if len(timeline) <= 0:
            return

        index = np.searchsorted(timeline, only_after, side='right')

        while True:
            try:
                owner, data = self.data.history[index]
            except IndexError:
                break
            if owner == state_id:
                index += 1
                continue
            self.watch_router.send_multipart([watcher_id, data])
            return True

        return False

    cdef solve_pending_watchers(self):
        cdef bytes watcher_id
        cdef (char*, char*, double) info
        cdef dict pending

        pending = self.data.pending
        if not pending:
            return
        for watcher_id in list(pending):
            info = pending[watcher_id]
            if self.solve_watcher(watcher_id, info[0], info[1], info[2]):
                del pending[watcher_id]

    cdef tick(self):
        self.solve_pending_watchers()

        for sock in zmq.select([self.watch_router, self.state_router], [], [])[0]:
            if sock is self.state_router:
                self.recv_request()
            else:
                self.recv_watcher()
