import functools
import os
import time
from contextlib import contextmanager
from typing import Union, Hashable, Any, Callable, Optional, Tuple, Iterable, Generator

import itsdangerous
import zmq

from zproc import tools, util, state_type
from zproc.constants import Msgs, Commands

ZMQ_IDENTITY_SIZE = 8
DEFAULT_ZMQ_RECVTIMEO = -1


class State(
    util.SecretKeyHolder, state_type.StateDictMethodStub, metaclass=state_type.StateType
):
    def __init__(
        self,
        server_address: str,
        *,
        namespace: str = "default",
        secret_key: Optional[str] = None
    ) -> None:
        """
        Allows accessing state stored on the zproc server, through a dict-like API.

        Communicates to the zproc server using the ZMQ sockets.

        Please don't share a State object between Processes/Threads.
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

        self.server_address = server_address
        self.namespace = namespace
        self._identity = os.urandom(ZMQ_IDENTITY_SIZE)

        self._zmq_ctx = util.create_zmq_ctx()

        self._dealer_sock = self._zmq_ctx.socket(zmq.DEALER)
        self._dealer_sock.setsockopt(zmq.IDENTITY, self._identity)
        self._dealer_sock.connect(self.server_address)

        self._sub_address, self._push_address = self._head()

        self._push_sock = self._zmq_ctx.socket(zmq.PUSH)
        self._push_sock.connect(self._push_address)

        self._active_sub_sock = self._create_sub_sock()

    def __str__(self):
        return "{}: {} to {} at {}".format(
            State.__qualname__, self.copy(), repr(self.server_address), hex(id(self))
        )

    def __repr__(self):
        return "<{}>".format(self.__str__())

    def fork(
        self,
        server_address: Optional[str] = None,
        *,
        namespace: Optional[str] = None,
        secret_key: Optional[str] = None
    ) -> "State":
        """
        "Forks" this State object.

        Takes the same args as the :py:class:`State` constructor,
        except that they automatically default to the values provided during the creation of this State object.

        If no args are provided to this function,
        then it shall create a new :py:class:`State` object
        that follows the exact same semantics as this one.

        This is preferred over copying a :py:class:`State` object.

        Useful when one needs to access 2 or more namespaces on the same server.
        """
        if server_address is None:
            server_address = self.server_address
        if namespace is None:
            namespace = self.namespace
        if secret_key is None:
            secret_key = self.secret_key

        return self.__class__(
            server_address, namespace=namespace, secret_key=secret_key
        )

    _namespace_bytes = b""
    _namespace_len = 0

    @property
    def namespace(self):
        return self._namespace_bytes.decode()

    @namespace.setter
    def namespace(self, namespace: str):
        assert len(namespace) > 0, "'namespace' cannot be empty!"

        self._namespace_bytes = namespace.encode()
        self._namespace_len = len(self._namespace_bytes)

    def _req_rep(self, request: dict):
        request[Msgs.namespace] = self._namespace_bytes
        # print("sent:", request)
        util.send(request, self._dealer_sock, self._serializer)
        response = util.recv(self._dealer_sock, self._serializer)
        # print("recvd:", response)
        return response

    def _run_fn_atomically(self, fn: Callable, *args, **kwargs):
        snapshot = self._req_rep({Msgs.cmd: Commands.exec_atomic_fn})

        try:
            result = fn(snapshot, *args, **kwargs)
        except Exception:
            util.send(None, self._push_sock, self._serializer)
            raise
        else:
            util.send(snapshot, self._push_sock, self._serializer)

        return result

    def _head(self):
        return self._req_rep({Msgs.cmd: Commands.head})

    def set(self, value: dict):
        """
        Set the state, completely over-writing the previous value.
        """
        return self._req_rep({Msgs.cmd: Commands.set_state, Msgs.info: value})

    def copy(self):
        """
        Return a deep-copy of the state.

        Unlike the shallow-copy returned by :py:meth:`dict.copy`.
        """
        return self._req_rep({Msgs.cmd: Commands.get_state})

    def keys(self):
        return self.copy().keys()

    def values(self):
        return self.copy().values()

    def items(self):
        return self.copy().items()

    def _create_sub_sock(self):
        sock = self._zmq_ctx.socket(zmq.SUB)
        sock.connect(self._sub_address)

        # prevents consuming our own updates, resulting in an circular message
        sock.setsockopt(zmq.SUBSCRIBE, self._identity)
        sock.setsockopt(zmq.INVERT_MATCHING, 1)

        return sock

    def go_live(self):
        """
        Clear the outstanding queue (or buffer), thus clearing any past events that were stored.

        Internally, this re-opens a socket, which in-turn clears the queue.

        Please read :ref:`live-events` for a detailed explanation.
        """
        self._active_sub_sock.close()
        self._active_sub_sock = self._create_sub_sock()

    @contextmanager
    def _setup_state_watch(
        self, live: bool, timeout: Optional[Union[float, int]], duplicate_okay: bool
    ):
        if live:
            sub_sock = self._create_sub_sock()
        else:
            sub_sock = self._active_sub_sock

        if timeout is None:

            def check_timeout():
                pass

        else:
            sub_sock.setsockopt(zmq.RCVTIMEO, int(timeout * 1000))
            epoch = time.time()

            def check_timeout():
                if time.time() - epoch > timeout:
                    raise TimeoutError("Timed-out while waiting for a state update.")

        try:
            yield lambda: self._recv_sub(sub_sock, check_timeout, duplicate_okay)
        except zmq.error.Again:
            raise TimeoutError("Timed-out while waiting for a state update.")
        finally:
            sub_sock.setsockopt(zmq.RCVTIMEO, DEFAULT_ZMQ_RECVTIMEO)

            if live:
                sub_sock.close()

    def _recv_sub(
        self, sub_sock: zmq.Socket, check_timeout: Callable, duplicate_okay: bool
    ):
        while True:
            msg = sub_sock.recv()[ZMQ_IDENTITY_SIZE:]
            # print(msg)
            if not msg.startswith(self._namespace_bytes):
                check_timeout()
                continue
            msg = msg[self._namespace_len :]

            try:
                msg = self._serializer.loads(msg)
            except itsdangerous.BadSignature:
                check_timeout()
                continue

            before, after, identical = msg
            if not identical or duplicate_okay:
                # print(before, after, identical)
                return before, after, identical

            check_timeout()

    @staticmethod
    def _create_dictkey_selector(
        keys: Iterable[Hashable], exclude: bool
    ) -> Callable[[dict, dict], Generator[Hashable, None, None]]:
        if exclude:
            return lambda before, after: (
                key for key in [*before.keys(), *after.keys()] if key not in keys
            )

        return lambda before, after: (
            key for key in [*before.keys(), *after.keys()] if key in keys
        )

    def get_raw_update(
        self,
        live: bool = False,
        timeout: Optional[Union[float, int]] = None,
        duplicate_okay: bool = False,
    ) -> Tuple[dict, dict, bool]:
        """
        A low-level hook that emits each and every state update.

        .. include:: /api/state/get_raw_update.rst
        """
        with self._setup_state_watch(live, timeout, duplicate_okay) as recv_sub:
            return recv_sub()

    def get_when_change(
        self,
        *keys: Hashable,
        exclude: bool = False,
        live: bool = False,
        timeout: Optional[Union[float, int]] = None,
        duplicate_okay: bool = False
    ) -> dict:
        """
        Block until a change is observed, and then return a copy of the state.

        .. include:: /api/state/get_when_change.rst
        """
        with self._setup_state_watch(live, timeout, duplicate_okay) as recv_sub:
            if len(keys):
                select_keys = self._create_dictkey_selector(keys, exclude)

                while True:
                    before, after, _ = recv_sub()

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
                    return recv_sub()[1]

    def get_when(
        self,
        test_fn,
        *,
        live: bool = False,
        timeout: Optional[Union[float, int]] = None,
        duplicate_okay: bool = False
    ) -> dict:
        """
        Block until ``test_fn(snapshot)`` returns a "truthy" value,
        and then return a copy of the state.

        *Where-*

        ``snapshot`` is a ``dict``, containing a copy of the state.

        .. include:: /api/state/get_when.rst
        """
        snapshot = self.copy()
        if test_fn(snapshot):
            return snapshot

        with self._setup_state_watch(live, timeout, duplicate_okay) as recv_sub:
            while True:
                snapshot = recv_sub()[1]
                if test_fn(snapshot):
                    return snapshot

    def get_when_equal(
        self,
        key: Hashable,
        value: Any,
        *,
        live: bool = False,
        timeout: Optional[Union[float, int]] = None,
        duplicate_okay: bool = False
    ) -> dict:
        """
        Block until ``state[key] == value``, and then return a copy of the state.

        .. include:: /api/state/get_when_equality.rst
        """

        def _(snapshot):
            try:
                return snapshot[key] == value
            except KeyError:
                return False

        return self.get_when(
            _, live=live, timeout=timeout, duplicate_okay=duplicate_okay
        )

    def get_when_not_equal(
        self,
        key: Hashable,
        value: Any,
        *,
        live: bool = False,
        timeout: Optional[Union[float, int]] = None,
        duplicate_okay: bool = False
    ) -> dict:
        """
        Block until ``state[key] != value``, and then return a copy of the state.

        .. include:: /api/state/get_when_equality.rst
        """

        def _(snapshot):
            try:
                return snapshot[key] != value
            except KeyError:
                return False

        return self.get_when(
            _, live=live, timeout=timeout, duplicate_okay=duplicate_okay
        )

    def get_when_none(
        self,
        key: Hashable,
        *,
        live: bool = False,
        timeout: Optional[Union[float, int]] = None,
        duplicate_okay: bool = False
    ) -> dict:
        """
        Block until ``state[key] is None``, and then return a copy of the state.

        .. include:: /api/state/get_when_equality.rst
        """

        def _(snapshot):
            try:
                return snapshot[key] is None
            except KeyError:
                return False

        return self.get_when(
            _, live=live, timeout=timeout, duplicate_okay=duplicate_okay
        )

    def get_when_not_none(
        self,
        key: Hashable,
        *,
        live: bool = False,
        timeout: Optional[Union[float, int]] = None,
        duplicate_okay: bool = False
    ) -> dict:
        """
        Block until ``state[key] is not None``, and then return a copy of the state.

        .. include:: /api/state/get_when_equality.rst
        """

        def _(snapshot):
            try:
                return snapshot[key] is not None
            except KeyError:
                return False

        return self.get_when(
            _, live=live, timeout=timeout, duplicate_okay=duplicate_okay
        )

    def get_when_available(
        self,
        key: Hashable,
        *,
        live: bool = False,
        timeout: Optional[Union[float, int]] = None,
        duplicate_okay: bool = False
    ):
        """
        Block until ``key in state``, and then return a copy of the state.

        .. include:: /api/state/get_when_equality.rst
        """
        return self.get_when(
            lambda snapshot: key in snapshot,
            live=live,
            timeout=timeout,
            duplicate_okay=duplicate_okay,
        )

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
        self._active_sub_sock.close()
        util.close_zmq_ctx(self._zmq_ctx)


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
