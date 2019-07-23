import math
import os
import struct
import time
from collections import deque
from typing import Hashable, Any, Dict, Mapping, Sequence

import zmq

from zproc import util, serializer
from zproc.consts import (
    Msgs,
    Cmds,
    DEFAULT_ZMQ_RECVTIMEO,
    StateUpdate,
    ZMQ_IDENTITY_LENGTH,
    ServerMeta,
)
from zproc.server import tools


class SkipStateUpdate(Exception):
    pass


def dummy_callback(_):
    pass


class StateWatcher:
    _time_limit: float
    _iters: int = 0

    def __init__(self, *args):
        (
            self._state,
            self.callback,
            self.live,
            self.timeout,
            self.identical_okay,
            self.start_time,
            self.count,
        ) = args

        if self.count is None:
            self._iter_limit = math.inf
        else:
            self._iter_limit = self.count

        self._only_after = self.start_time
        if self._only_after is None:
            self._only_after = time.time()

    def _settimeout(self):
        if time.time() > self._time_limit:
            raise TimeoutError("Timed-out while waiting for a state update.")

        self._state.watcher_dealer.setsockopt(
            zmq.RCVTIMEO, int((self._time_limit - time.time()) * 1000)
        )

    def _request_reply(self) -> StateUpdate:
        response = util.strict_request_reply(
            [
                self._state.identity,
                self._state.namespace_bytes,
                bytes(self.identical_okay),
                struct.pack("d", self._only_after),
            ],
            self._state.watcher_dealer.send_multipart,
            self._state.watcher_dealer.recv_multipart,
        )
        return StateUpdate(
            *serializer.loads(response[0]), is_identical=bool(response[1])
        )

    def go_live(self):
        self._only_after = time.time()

    def __next__(self):
        if self.timeout is None:
            self._state.watcher_dealer.setsockopt(zmq.RCVTIMEO, DEFAULT_ZMQ_RECVTIMEO)
        else:
            self._time_limit = time.time() + self.timeout

        while self._iters < self._iter_limit:
            if self.timeout is not None:
                self._settimeout()
            if self.live:
                self._only_after = time.time()
            try:
                state_update = self._request_reply()
            except zmq.error.Again:
                raise TimeoutError("Timed-out while waiting for a state update.")
            if not self.live:
                self._only_after = state_update.timestamp
            try:
                value = self.callback(state_update)
            except SkipStateUpdate:
                continue
            else:
                self._iters += 1
            return value

        raise StopIteration

    def __iter__(self):
        return self

    def consume(self):
        # consumes iterator at C speed
        deque(iter(self), maxlen=0)


class StateAPI:
    _server_meta: ServerMeta

    def __init__(self, client):
        self.client = client
        self.ctx = util.create_zmq_ctx()
        self.state_dealer = self.create_state_dealer()  # state dealer
        self.watcher_dealer = self.create_watcher_dealer()  # watcher dealer

    @property
    def server_address(self) -> str:
        return self.client.server_address

    @property
    def namespace_bytes(self) -> bytes:
        return self.client.namespace.encode()

    def create_state_dealer(self) -> zmq.Socket:
        sock = self.ctx.socket(zmq.DEALER)
        self.identity = os.urandom(ZMQ_IDENTITY_LENGTH)
        sock.setsockopt(zmq.IDENTITY, self.identity)
        sock.connect(self.server_address)
        self._server_meta = util.req_server_meta(sock)
        return sock

    def state_request_reply(self, request: Dict[int, Any]):
        request[Msgs.namespace] = self.namespace_bytes
        msg = serializer.dumps(request)
        return serializer.loads(
            util.strict_request_reply(
                msg, self.state_dealer.send, self.state_dealer.recv
            )
        )

    def ping(self, **kwargs):
        """
        Ping the zproc server connected to this Client.

        :param kwargs: Keyword arguments that :py:func:`ping` takes, except ``server_address``.
        :return: Same as :py:func:`ping`
        """
        return tools.ping(self.server_address, **kwargs)

    def time(self) -> float:
        return self.state_request_reply({Msgs.cmd: Cmds.time})

    def create_watcher_dealer(self) -> zmq.Socket:
        sock = self.ctx.socket(zmq.DEALER)
        sock.connect(self._server_meta.watcher_router)
        return sock

    def when_change_raw(
        self,
        *,
        live: bool = False,
        timeout: float = None,
        identical_okay: bool = False,
        start_time: bool = None,
        count: int = None,
    ) -> StateWatcher:
        """
        A low-level hook that emits each and every state update.
        All other state watchers are built upon this only.

        .. include:: /api/state/get_raw_update.rst
        """
        return StateWatcher(
            self, live, dummy_callback, timeout, identical_okay, start_time, count
        )

    def when_change(
        self,
        *keys: Hashable,
        exclude: bool = False,
        live: bool = False,
        timeout: float = None,
        identical_okay: bool = False,
        start_time: bool = None,
        count: int = None,
    ) -> StateWatcher:
        """
        Block until a change is observed, and then return a copy of the state.

        .. include:: /api/state/get_when_change.rst
        """
        if not keys:

            def callback(update: StateUpdate) -> dict:
                return update.after

        else:
            if identical_okay:
                raise ValueError(
                    "Passing both `identical_okay` and `keys` is not possible. "
                    "(Hint: Omit `keys`)"
                )

            key_set = set(keys)

            def select(before, after):
                selected = {*before.keys(), *after.keys()}
                if exclude:
                    return selected - key_set
                else:
                    return selected & key_set

            def callback(update: StateUpdate) -> dict:
                before, after = update.before, update.after
                try:
                    if not any(before[k] != after[k] for k in select(before, after)):
                        raise SkipStateUpdate
                except KeyError:  # this indirectly implies that something has changed
                    pass
                return update.after

        return StateWatcher(
            self, callback, live, timeout, identical_okay, start_time, count
        )

    def when(
        self,
        test_fn,
        *,
        args: Sequence = None,
        kwargs: Mapping = None,
        live: bool = False,
        timeout: float = None,
        identical_okay: bool = False,
        start_time: bool = None,
        count: int = None,
    ) -> StateWatcher:
        """
        Block until ``test_fn(snapshot)`` returns a "truthy" value,
        and then return a copy of the state.

        *Where-*

        ``snapshot`` is a ``dict``, containing a version of the state after this update was applied.

        .. include:: /api/state/get_when.rst
        """
        if args is None:
            args = []
        if kwargs is None:
            kwargs = {}

        def callback(update: StateUpdate) -> dict:
            snapshot = update.after
            if test_fn(snapshot, *args, **kwargs):
                return snapshot
            raise SkipStateUpdate

        return StateWatcher(
            self, callback, live, timeout, identical_okay, start_time, count
        )

    def when_truthy(self, key: Hashable, **when_kwargs) -> StateWatcher:
        def _(snapshot):
            try:
                return snapshot[key]
            except KeyError:
                return False

        return self.when(_, **when_kwargs)

    def when_falsy(self, key: Hashable, **when_kwargs) -> StateWatcher:
        def _(snapshot):
            try:
                return not snapshot[key]
            except KeyError:
                return False

        return self.when(_, **when_kwargs)

    def when_equal(self, key: Hashable, value: Any, **when_kwargs) -> StateWatcher:
        """
        Block until ``state[key] == value``, and then return a copy of the state.

        .. include:: /api/state/get_when_equality.rst
        """

        def _(snapshot):
            try:
                return snapshot[key] == value
            except KeyError:
                return False

        return self.when(_, **when_kwargs)

    def when_not_equal(self, key: Hashable, value: Any, **when_kwargs) -> StateWatcher:
        """
        Block until ``state[key] != value``, and then return a copy of the state.

        .. include:: /api/state/get_when_equality.rst
        """

        def _(snapshot):
            try:
                return snapshot[key] != value
            except KeyError:
                return False

        return self.when(_, **when_kwargs)

    def when_none(self, key: Hashable, **when_kwargs) -> StateWatcher:
        """
        Block until ``state[key] is None``, and then return a copy of the state.

        .. include:: /api/state/get_when_equality.rst
        """

        def _(snapshot):
            try:
                return snapshot[key] is None
            except KeyError:
                return False

        return self.when(_, **when_kwargs)

    def when_not_none(self, key: Hashable, **when_kwargs) -> StateWatcher:
        """
        Block until ``state[key] is not None``, and then return a copy of the state.

        .. include:: /api/state/get_when_equality.rst
        """

        def _(snapshot):
            try:
                return snapshot[key] is not None
            except KeyError:
                return False

        return self.when(_, **when_kwargs)

    def when_available(self, key: Hashable, **when_kwargs) -> StateWatcher:
        """
        Block until ``key in state``, and then return a copy of the state.

        .. include:: /api/state/get_when_equality.rst
        """
        return self.when(lambda snapshot: key in snapshot, **when_kwargs)

    def __del__(self):
        try:
            self.state_dealer.close()
            self.watcher_dealer.close()
            util.close_zmq_ctx(self.ctx)
        except Exception:
            pass
