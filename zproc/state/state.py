import itertools
import math
import os
import struct
import time
from functools import wraps
from pprint import pformat
from textwrap import indent
from typing import Hashable, Any, Callable, Dict, List, Generator, Mapping, Sequence

import zmq

from zproc import util, serializer
from zproc.consts import (
    Msgs,
    Cmds,
    DEFAULT_NAMESPACE,
    DEFAULT_ZMQ_RECVTIMEO,
    StateUpdate,
    ZMQ_IDENTITY_LENGTH,
    ServerMeta,
)
from zproc.server import tools
from zproc.state import _type


class State(_type.StateDictMethodStub, metaclass=_type.StateType):
    _server_meta: ServerMeta

    def __init__(
        self, server_address: str, *, namespace: str = DEFAULT_NAMESPACE
    ) -> None:
        """
        Allows accessing the state stored on the zproc server, through a dict-like API.

        Also allows changing the namespace.

        Serves the following ``dict``-like members, for accessing the state:

        - Magic  methods:
            ``__contains__()``,  ``__delitem__()``, ``__eq__()``,
            ``__getitem__()``, ``__iter__()``,
            ``__len__()``, ``__ne__()``, ``__setitem__()``

        - Methods:
            ``clear()``, ``copy()``, ``get()``,
            ``items()``,  ``keys()``, ``pop()``, ``popitem()``,
            ``setdefault()``, ``update()``, ``values()``

        Please don't share a State object between Processes/Threads.
        A State object is not thread-safe.

        :param server_address:
            .. include:: /api/snippets/server_address.rst

            If you are using a :py:class:`Context`, then this is automatically provided.
        """
        #: Passed on from constructor. This is read-only
        self.server_address = server_address
        self.namespace = namespace

        self._zmq_ctx = util.create_zmq_ctx()
        self._s_dealer = self._create_s_dealer()
        self._w_dealer = self._create_w_dealer()

    def __str__(self):
        return "\n".join(
            (
                "%s - namespace: %r server: %r at %#x"
                % (
                    self.__class__.__qualname__,
                    self.namespace,
                    self.server_address,
                    id(self),
                ),
                indent("↳ " + pformat(self.copy()), " " * 2),
            )
        )

    def __repr__(self):
        return util.enclose_in_brackets(self.__str__())

    def fork(self, server_address: str = None, *, namespace: str = None) -> "State":
        r"""
        "Forks" this State object.

        Takes the same args as the :py:class:`State` constructor,
        except that they automatically default to the values provided during the creation of this State object.

        If no args are provided to this function,
        then it shall create a new :py:class:`State` object
        that follows the exact same semantics as this one.

        This is preferred over ``copy()``\ -ing a :py:class:`State` object.

        Useful when one needs to access 2 or more namespaces from the same code.
        """
        if server_address is None:
            server_address = self.server_address
        if namespace is None:
            namespace = self.namespace

        return self.__class__(server_address, namespace=namespace)

    _namespace_bytes: bytes

    @property
    def namespace(self) -> str:
        """
        This State's current working namespace as a ``str``.

        This property is read/write,
        such that you can switch namespaces on the fly by just setting it's value.

        .. code-block:: python

            state['food'] = 'available'
            print(state)

            state.namespace = "foobar"

            print(state)

        """
        return self._namespace_bytes.decode()

    @namespace.setter
    def namespace(self, namespace: str):
        # empty namespace is reserved for use by the framework iteself
        assert len(namespace) > 0, "'namespace' cannot be empty!"

        self._namespace_bytes = namespace.encode()

    #
    # state access
    #

    def _create_s_dealer(self) -> zmq.Socket:
        sock = self._zmq_ctx.socket(zmq.DEALER)
        self._identity = os.urandom(ZMQ_IDENTITY_LENGTH)
        sock.setsockopt(zmq.IDENTITY, self._identity)
        sock.connect(self.server_address)
        self._server_meta = util.req_server_meta(sock)
        return sock

    def _s_request_reply(self, request: Dict[int, Any]):
        request[Msgs.namespace] = self._namespace_bytes
        msg = serializer.dumps(request)
        return serializer.loads(
            util.strict_request_reply(msg, self._s_dealer.send, self._s_dealer.recv)
        )

    def set(self, value: dict):
        """
        Set the state, completely over-writing the previous value.

        .. caution::

            This kind of operation usually leads to a data race.

            Please take good care while using this.

            Use the :py:func:`atomic` deocrator if you're feeling anxious.
        """
        self._s_request_reply({Msgs.cmd: Cmds.set_state, Msgs.info: value})

    def copy(self) -> dict:
        """
        Return a deep-copy of the state as a ``dict``.

        (Unlike the shallow-copy returned by the inbuilt :py:meth:`dict.copy`).
        """
        return self._s_request_reply({Msgs.cmd: Cmds.get_state})

    def keys(self):
        return self.copy().keys()

    def values(self):
        return self.copy().values()

    def items(self):
        return self.copy().items()

    def ping(self, **kwargs):
        """
        Ping the zproc server corresponding to this State's Context

        :param kwargs: Keyword arguments that :py:func:`ping` takes, except ``server_address``.
        :return: Same as :py:func:`ping`
        """
        return tools.ping(self.server_address, **kwargs)

    #
    # state watcher
    #

    def _create_w_dealer(self) -> zmq.Socket:
        sock = self._zmq_ctx.socket(zmq.DEALER)
        sock.connect(self._server_meta.watcher_router)
        return sock

    def _w_request_reply(self, request: List[bytes], only_after: float) -> StateUpdate:
        request[-1] = struct.pack("d", only_after)
        response = util.strict_request_reply(
            request, self._w_dealer.send_multipart, self._w_dealer.recv_multipart
        )
        return StateUpdate(*serializer.loads(response[0]), bool(response[1]))

    def when_change_raw(
        self,
        *,
        live: bool = False,
        timeout: float = None,
        identical_okay: bool = False,
        start_time: bool = None,
        count: int = None,
    ) -> Generator[StateUpdate, None, None]:
        """
        A low-level hook that emits each and every state update.
        All other state watchers are built upon this only.

        .. include:: /api/state/get_raw_update.rst
        """
        if timeout is None:
            time_limit = None
        else:
            time_limit = time.time() + timeout

        only_after = start_time
        if only_after is None:
            only_after = self._s_request_reply({Msgs.cmd: Cmds.time})

        if count is None:
            counter = itertools.count()
        else:
            counter = iter(range(count))

        request_msg = [
            self._identity,
            self._namespace_bytes,
            bytes(identical_okay),
            None,
        ]

        def _(only_after):
            for _ in counter:
                if time_limit is None:
                    self._w_dealer.setsockopt(zmq.RCVTIMEO, DEFAULT_ZMQ_RECVTIMEO)
                else:
                    if time_limit < time.time():
                        raise TimeoutError(
                            "Timed-out while waiting for a state update."
                        )

                    self._w_dealer.setsockopt(
                        zmq.RCVTIMEO, int((time_limit - time.time()) * 1000)
                    )

                if live:
                    only_after = time.time()
                try:
                    state_update = self._w_request_reply(request_msg, only_after)
                except zmq.error.Again:
                    raise TimeoutError("Timed-out while waiting for a state update.")
                if not live:
                    only_after = state_update.timestamp

                yield state_update

        return _(only_after)

    def when_change(
        self, *keys: Hashable, exclude: bool = False, **watcher_kwargs
    ) -> Generator[dict, None, None]:
        """
        Block until a change is observed, and then return a copy of the state.

        .. include:: /api/state/get_when_change.rst
        """
        count = watcher_kwargs.pop("count", None)
        it = self.when_change_raw(**watcher_kwargs)

        if not keys:
            if count is None:
                return (i.after for i in it)
            return (next(it).after for _ in range(count))

        key_set = set(keys)
        identical_okay = watcher_kwargs.get("identical_okay", False)
        if identical_okay:
            raise ValueError(
                "Passing both `identical_okay` and `keys` is not possible. "
                "(Hint: Omit `keys`)"
            )

        if not count:
            count = math.inf

        def _():
            def select():
                selected = {*before.keys(), *after.keys()}
                if exclude:
                    return selected - key_set
                else:
                    return selected & key_set

            i = 0
            while i < count:
                update = next(it)
                before, after = update.before, update.after
                try:
                    if not any(before[key] != after[key] for key in select()):
                        continue
                except KeyError:  # this indirectly implies that something has changed
                    pass

                i += 1
                yield update.after

        return _()

    def when(
        self,
        test_fn,
        *,
        args: Sequence = None,
        kwargs: Mapping = None,
        **watcher_kwargs,
    ) -> Generator[dict, None, None]:
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

        count = watcher_kwargs.pop("count", math.inf)
        it = self.when_change_raw(**watcher_kwargs)

        def _():
            i = 0
            while i < count:
                snapshot = next(it).after
                if test_fn(snapshot, *args, **kwargs):
                    i += 1
                    yield snapshot

        return _()

    def when_truthy(self, key: Hashable, **watcher_kwargs):
        def _(snapshot):
            try:
                return snapshot[key]
            except KeyError:
                return False

        return self.when(_, **watcher_kwargs)

    def when_falsy(self, key: Hashable, **watcher_kwargs):
        def _(snapshot):
            try:
                return not snapshot[key]
            except KeyError:
                return False

        return self.when(_, **watcher_kwargs)

    def when_equal(
        self, key: Hashable, value: Any, **watcher_kwargs
    ) -> Generator[dict, None, None]:
        """
        Block until ``state[key] == value``, and then return a copy of the state.

        .. include:: /api/state/get_when_equality.rst
        """

        def _(snapshot):
            try:
                return snapshot[key] == value
            except KeyError:
                return False

        return self.when(_, **watcher_kwargs)

    def when_not_equal(
        self, key: Hashable, value: Any, **watcher_kwargs
    ) -> Generator[dict, None, None]:
        """
        Block until ``state[key] != value``, and then return a copy of the state.

        .. include:: /api/state/get_when_equality.rst
        """

        def _(snapshot):
            try:
                return snapshot[key] != value
            except KeyError:
                return False

        return self.when(_, **watcher_kwargs)

    def when_none(
        self, key: Hashable, **watcher_kwargs
    ) -> Generator[dict, None, None]:
        """
        Block until ``state[key] is None``, and then return a copy of the state.

        .. include:: /api/state/get_when_equality.rst
        """

        def _(snapshot):
            try:
                return snapshot[key] is None
            except KeyError:
                return False

        return self.when(_, **watcher_kwargs)

    def when_not_none(
        self, key: Hashable, **watcher_kwargs
    ) -> Generator[dict, None, None]:
        """
        Block until ``state[key] is not None``, and then return a copy of the state.

        .. include:: /api/state/get_when_equality.rst
        """

        def _(snapshot):
            try:
                return snapshot[key] is not None
            except KeyError:
                return False

        return self.when(_, **watcher_kwargs)

    def when_available(self, key: Hashable, **watcher_kwargs):
        """
        Block until ``key in state``, and then return a copy of the state.

        .. include:: /api/state/get_when_equality.rst
        """
        return self.when(lambda snapshot: key in snapshot, **watcher_kwargs)

    def __del__(self):
        try:
            self._s_dealer.close()
            self._w_dealer.close()
            util.close_zmq_ctx(self._zmq_ctx)
        except Exception:
            pass


def atomic(fn: Callable) -> Callable:
    """
    Wraps a function, to create an atomic operation out of it.

    This contract guarantees, that while an atomic ``fn`` is running -

    - No one, except the "callee" may access the state.
    - If an ``Exception`` occurs while the ``fn`` is running, the state remains unaffected.
    - | If a signal is sent to the "callee", the ``fn`` remains unaffected.
      | (The state is not left in an incoherent state.)

    .. note::
        - The first argument to the wrapped function *must* be a :py:class:`State` object.
        - The wrapped ``fn`` receives a frozen version (snapshot) of state,
          which is a ``dict`` object, not a :py:class:`State` object.
        - It is not possible to call one atomic function from other.

    Please read :ref:`atomicity` for a detailed explanation.

    :param fn:
        The function to be wrapped, as an atomic function.

    :returns:
        A wrapper function.

        The wrapper function returns the value returned by the wrapped ``fn``.

    >>> import zproc
    >>>
    >>> @zproc.atomic
    ... def increment(snapshot):
    ...     return snapshot['count'] + 1
    ...
    >>>
    >>> ctx = zproc.Context()
    >>> state = ctx.create_state({'count': 0})
    >>>
    >>> increment(state)
    1
    """

    serialized = serializer.dumps_fn(fn)

    @wraps(fn)
    def wrapper(state: State, *args, **kwargs):
        return state._s_request_reply(
            {
                Msgs.cmd: Cmds.run_fn_atomically,
                Msgs.info: serialized,
                Msgs.args: args,
                Msgs.kwargs: kwargs,
            }
        )

    return wrapper
