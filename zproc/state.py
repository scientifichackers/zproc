import functools
import os
import time
from typing import Union, Hashable, Any, Callable

import itsdangerous
import zmq

from zproc import tools, util
from zproc.server import ServerFn, Msg

ZMQ_IDENTITY_SIZE = 8
DEFAULT_ZMQ_RECVTIMEO = -1


def _create_get_when_xxx_mainloop(self: "State", live: bool):
    """Generates a template for a state watcher mainloop."""

    def decorator(mainloop_fn):
        @functools.wraps(mainloop_fn)
        def wrapper():

            if live:

                sock = self._create_subscribe_sock()
                try:
                    return mainloop_fn(sock, time.time())
                finally:
                    sock.close()

            else:
                return mainloop_fn(self._buffered_sub_sock, time.time())

        return wrapper

    return decorator


class State(util.SecretKeyHolder):
    def __init__(
        self,
        server_address: str,
        *,
        namespace: str = "",
        secret_key: Union[str, None] = None
    ) -> None:
        """
        Allows accessing state stored on the zproc server, through a dict-like API.

        Communicates to the zproc server using the ZMQ sockets.

        Please don't share a State object between Processes / Threads.
        A State object is not thread-safe.

        Boasts the following ``dict``-like members, for accessing the state:

        - Magic  methods:
            ``__contains__()``,  ``__delitem__()``, ``__eq__()``,
            ``__getitem__()``, ``__iter__()``,
            ``__len__()``, ``__ne__()``, ``__setitem__()``

        - Methods:
            ``clear()``, ``copy()``, ``get()``,
            ``items()``,  ``keys()``, ``pop()``, ``popitem()``,
            ``setdefault()``, ``update()``, ``values()``

        :param server_address:
            The address of zproc server.

            If you are using a :py:class:`Context`, then this is automatically provided.

            Please read :ref:`server-address-spec` for a detailed explanation.

        :ivar server_address: Passed on from constructor.
        """

        super().__init__(secret_key)

        self._namespace_bytes, self._namespace_len = b"", -1
        self.namespace = namespace

        self._identity = os.urandom(ZMQ_IDENTITY_SIZE)

        self._zmq_ctx = zmq.Context()
        self._zmq_ctx.setsockopt(zmq.LINGER, 0)

        self.server_address = server_address

        self._dealer_sock = self._zmq_ctx.socket(zmq.DEALER)
        self._dealer_sock.setsockopt(zmq.IDENTITY, self._identity)
        self._dealer_sock.connect(self.server_address)

        self._sub_address, self._push_address = self._head()

        self._push_sock = self._zmq_ctx.socket(zmq.PUSH)
        self._push_sock.connect(self._push_address)

        self._buffered_sub_sock = self._create_subscribe_sock()

    def __str__(self):
        return "{}: {} to {} at {}".format(
            State.__qualname__, self.copy(), repr(self.server_address), hex(id(self))
        )

    def __repr__(self):
        return "<{}>".format(self.__str__())

    @property
    def namespace(self):
        return self._namespace_bytes.decode()

    @namespace.setter
    def namespace(self, namespace: str):
        self._namespace_bytes = namespace.encode()
        self._namespace_len = len(self._namespace_bytes)

    def _head(self):
        return self._req_rep({Msg.server_fn: ServerFn.head})

    def _create_subscribe_sock(self):
        sock = self._zmq_ctx.socket(zmq.SUB)
        sock.connect(self._sub_address)

        # prevents consuming our own updates, resulting in an circular message
        sock.setsockopt(zmq.SUBSCRIBE, self._identity)
        sock.setsockopt(zmq.INVERT_MATCHING, 1)

        return sock

    def _recv_sub(
        self,
        subscribe_sock: zmq.Socket,
        start_time: Union[float, int],
        timeout: Union[None, float, int] = None,
        duplicate_okay: bool = False,
    ):
        if timeout is not None:
            subscribe_sock.setsockopt(zmq.RCVTIMEO, int(timeout * 1000))

        try:
            while True:
                msg = subscribe_sock.recv()[ZMQ_IDENTITY_SIZE:]

                if msg.startswith(self._namespace_bytes):
                    msg = msg[self._namespace_len :]
                    try:
                        msg = util.handle_remote_exc(self._serializer.loads(msg))
                    except itsdangerous.BadSignature:
                        pass
                    else:
                        before, after, identical = msg
                        if not identical or duplicate_okay:
                            return before, after

                if timeout is not None and time.time() - start_time > timeout:
                    raise TimeoutError("Timed-out while waiting for a state update.")
        except zmq.error.Again:
            raise TimeoutError("Timed-out while waiting for a state update.")
        finally:
            subscribe_sock.setsockopt(zmq.RCVTIMEO, DEFAULT_ZMQ_RECVTIMEO)

    def _req_rep(self, request):
        request[Msg.namespace] = self._namespace_bytes
        # print("send:", request)
        util.send(self._dealer_sock, self._serializer, request)
        response = util.recv(self._dealer_sock, self._serializer)
        # print('res:', response)

        return util.handle_remote_exc(response)

    def _run_fn_atomically(self, fn, *args, **kwargs):
        snapshot = self._req_rep({Msg.server_fn: ServerFn.exec_atomic_fn})

        try:
            result = fn(snapshot, *args, **kwargs)
        except Exception:
            util.send(self._push_sock, self._serializer, None)
            raise
        else:
            util.send(self._push_sock, self._serializer, snapshot)

        return result

    @staticmethod
    def _create_dictkey_selector(keys, exclude):
        if exclude:
            return lambda before, after: (
                key for key in (*before.keys(), *after.keys()) if key not in keys
            )

        return lambda before, after: (
            key for key in (*before.keys(), *after.keys()) if key in keys
        )

    def get_when_change(
        self,
        *keys: Hashable,
        exclude: bool = False,
        live: bool = True,
        timeout: Union[None, float, int] = None
    ):
        """
        Block until a change is observed, and then return a copy of the state.

        .. include:: /api/state/get_when_change.rst
        """

        @_create_get_when_xxx_mainloop(self, live)
        def mainloop(sock, start_time):
            if len(keys):
                select_keys = self._create_dictkey_selector(keys, exclude)

                while True:
                    before, after = self._recv_sub(sock, start_time, timeout)
                    for key in select_keys(before, after):
                        try:
                            before_val, after_val = before[key], after[key]
                        except KeyError:  # this indirectly implies that something changed
                            return after
                        else:
                            if before_val != after_val:
                                return after
            else:
                while True:
                    return self._recv_sub(sock, start_time, timeout)[1]

        return mainloop()

    def get_raw_update(
        self,
        live: bool = True,
        timeout: Union[float, int, None] = None,
        duplicate_okay: bool = False,
    ):
        """
        A low-level hook
        :param live:
        :param timeout:
        :param duplicate_okay:
        :return:
        """

        @_create_get_when_xxx_mainloop(self, live)
        def mainloop(sock, start_time):
            return self._recv_sub(sock, start_time, timeout, duplicate_okay)

        return mainloop()

    def get_when(
        self,
        test_fn,
        *,
        live: bool = True,
        timeout: Union[float, int, None] = None,
        duplicate_okay: bool = False
    ):
        """
        Block until ``test_fn(state)`` returns a "truthy" value,
        and then return a copy of the state.

        .. include:: /api/state/get_when.rst
        """

        @_create_get_when_xxx_mainloop(self, live)
        def mainloop(sock, start_time):
            latest_copy = self.copy()

            while True:
                if test_fn(latest_copy):
                    return latest_copy

                latest_copy = self._recv_sub(sock, start_time, timeout, duplicate_okay)[
                    1
                ]

        return mainloop()

    def get_when_equal(
        self,
        key: Hashable,
        value: Any,
        *,
        live: bool = True,
        timeout: Union[float, int, None] = None,
        duplicate_okay: bool = False
    ):
        """
        Block until ``state.get(key) == value``, and then return a copy of the state.

        .. include:: /api/state/get_when_equality.rst
        """

        return self.get_when(
            lambda state: state.get(key) == value,
            live=live,
            timeout=timeout,
            duplicate_okay=duplicate_okay,
        )

    def get_when_not_equal(
        self,
        key: Hashable,
        value: Any,
        *,
        live: bool = True,
        timeout: Union[float, int, None] = None,
        duplicate_okay: bool = False
    ):
        """
        Block until ``state.get(key) != value``, and then return a copy of the state.

        .. include:: /api/state/get_when_equality.rst
        """

        return self.get_when(
            lambda state: state.get(key) != value,
            live=live,
            timeout=timeout,
            duplicate_okay=duplicate_okay,
        )

    def get_when_none(
        self,
        key: Hashable,
        *,
        live: bool = True,
        timeout: Union[float, int, None] = None,
        duplicate_okay: bool = False
    ):
        """
        Block until ``state.get(key) is None``, and then return a copy of the state.

        .. include:: /api/state/get_when_equality.rst
        """

        return self.get_when(
            lambda state: state.get(key) is None,
            live=live,
            timeout=timeout,
            duplicate_okay=duplicate_okay,
        )

    def get_when_not_none(
        self,
        key: Hashable,
        *,
        live: bool = True,
        timeout: Union[float, int, None] = None,
        duplicate_okay: bool = False
    ):
        """
        Block until ``state.get(key) is not None``, and then return a copy of the state.

        .. include:: /api/state/get_when_equality.rst
        """

        return self.get_when(
            lambda state: state.get(key) is not None,
            live=live,
            timeout=timeout,
            duplicate_okay=duplicate_okay,
        )

    def go_live(self):
        """
        Clear the events buffer, thus removing past events that were stored.

        Please read :ref:`live-events` for a detailed explanation.
        """

        self._buffered_sub_sock.close()
        self._buffered_sub_sock = self._create_subscribe_sock()

    def ping(self, **kwargs):
        """
        Ping the zproc server corresponding to this State's Context

        :param kwargs: Keyword arguments that :py:func:`ping` takes, except ``server_address``.
        :return: Same as :py:func:`ping`
        """

        return tools.ping(self.server_address, **kwargs)

    def close(self):
        """
        Close this State and disconnect with the Server.
        """

        self._dealer_sock.close()
        self._push_sock.close()
        self._buffered_sub_sock.close()
        util.close_zmq_ctx(self._zmq_ctx)

    def set(self, value: dict):
        """
        Set the state, completely over-writing the previous value.
        """

        return self._req_rep({Msg.server_fn: ServerFn.set_state, Msg.value: value})

    def copy(self):
        """
        Return a deep-copy of the state.

        Unlike the shallow-copy returned by :py:meth:`dict.copy`.
        """

        return self._req_rep({Msg.server_fn: ServerFn.state_reply})

    def keys(self):
        return self.copy().keys()

    def items(self):
        return self.copy().items()

    def values(self):
        return self.copy().values()

    # These are here to enable proper typing in IDEs.
    # Their contents are populated at runtime. (see below)

    def __contains__(self, o: object) -> bool:
        pass

    def __delitem__(self, v) -> None:
        pass

    def __eq__(self, o: object) -> bool:
        pass

    def __getitem__(self, k):
        pass

    def __iter__(self):
        pass

    def __len__(self) -> int:
        pass

    def __ne__(self, o: object) -> bool:
        pass

    def __setitem__(self, k, v) -> None:
        pass

    def clear(self) -> None:
        pass

    def get(self, k):
        pass

    def pop(self, k):
        pass

    def popitem(self):
        pass

    def setdefault(self, k, d=None):
        pass

    def update(self, E=None, **F) -> None:
        pass


def _create_remote_dict_method(state_method_name: str):
    """
    Generates a method for the State class,
    that will call the "method_name" on the state (a ``dict``) stored on the server,
    and return the result.

    Glorified RPC.
    """

    def remote_method(self: State, *args, **kwargs):
        return self._req_rep(
            {
                Msg.server_fn: ServerFn.exec_state_method,
                Msg.state_method: state_method_name,
                Msg.args: args,
                Msg.kwargs: kwargs,
            }
        )

    remote_method.__name__ = state_method_name
    return remote_method


for name in {
    "__contains__",
    "__delitem__",
    "__eq__",
    "__getitem__",
    "__iter__",
    "__len__",
    "__ne__",
    "__setitem__",
    "clear",
    "get",
    "pop",
    "popitem",
    "setdefault",
    "update",
}:
    setattr(State, name, _create_remote_dict_method(name))


def atomic(fn: Callable) -> Callable:
    """
    Wraps a function, to create an atomic operation out of it.

    No Process shall access the state while ``fn`` is running.

    .. note::
        - The first argument to the wrapped function *must* be a :py:class:`State` object.

        - | The wrapped function receives a frozen version (snapshot) of state;
          | a ``dict`` object, not a :py:class:`State` object.

    Please read :ref:`atomicity` for a detailed explanation.

    :param fn:
        The ``function`` to be wrapped, as an atomic function.

    :returns:
        A wrapper ``function``.

        The "wrapper" ``function`` returns the value returned by the "wrapped" ``function``.

    >>> import zproc
    >>>
    >>> @zproc.atomic
    ... def increment(snapshot):
    ...     return snapshot['count'] + 1
    ...
    >>>
    >>> ctx = zproc.Context()
    >>> ctx.state['count'] = 0
    >>>
    >>> increment(ctx.state)
    1
    """

    @functools.wraps(fn)
    def wrapper(state: State, *args, **kwargs):
        return state._run_fn_atomically(fn, *args, **kwargs)

    return wrapper
