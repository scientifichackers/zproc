import os
from contextlib import contextmanager
from functools import wraps
from pprint import pformat
from textwrap import indent
from typing import Hashable, Any, Callable, Tuple, Generator, Dict

import zmq

from zproc import util, serializer
from zproc.consts import Msgs, Commands, ZMQ_IDENTITY_LENGTH, DEFAULT_NAMESPACE
from zproc.server import tools
from zproc.state import _type
from zproc.state.watcher import Watcher


class State(_type.StateDictMethodStub, metaclass=_type.StateType):
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
        #: Passed on from constructor.
        self.server_address = server_address
        self.namespace = namespace

        self._zmq_ctx = util.create_zmq_ctx()
        self._dealer = self._create_dealer()
        self._server_meta = util.get_server_meta(self._zmq_ctx, server_address)
        self._watcher = Watcher(self._server_meta.watch_router)

    def _create_dealer(self) -> zmq.Socket:
        sock = self._zmq_ctx.socket(zmq.DEALER)
        self._ident = os.urandom(ZMQ_IDENTITY_LENGTH)
        sock.setsockopt(zmq.IDENTITY, self._ident)
        sock.connect(self.server_address)
        return sock

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
    _namespace_length: int

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
        self._namespace_length = len(self._namespace_bytes)

    def _req_rep(self, req: Dict[int, Any]):
        req[Msgs.namespace] = self._namespace_bytes
        msg = serializer.dumps(req)

        try:
            self._dealer.send(msg)
            msg = self._dealer.recv()
        except Exception:
            self._dealer.close()
            self._dealer = self._create_dealer()
            raise

        return serializer.loads(msg)

    def set(self, value: dict):
        """
        Set the state, completely over-writing the previous value.

        .. caution::

            This kind of operation usually leads to a data race.

            Please take good care while using this.

            Use the :py:func:`atomic` deocrator if you're feeling anxious.
        """
        self._req_rep({Msgs.cmd: Commands.set_state, Msgs.info: value})

    def copy(self) -> dict:
        """
        Return a deep-copy of the state as a ``dict``.

        (Unlike the shallow-copy returned by the inbuilt :py:meth:`dict.copy`).
        """
        return self._req_rep({Msgs.cmd: Commands.get_state})

    def keys(self):
        return self.copy().keys()

    def values(self):
        return self.copy().values()

    def items(self):
        return self.copy().items()

    def go_live(self):
        """
        Clear the outstanding queue (or buffer), thus clearing any past events that were stored.

        Internally, this re-opens a socket, which in-turn clears the queue.

        Please read :ref:`live-events` for a detailed explanation.
        """
        self._watcher.go_live()

    @contextmanager
    def get_raw_update(
        self,
        *,
        live: bool = False,
        timeout: float = None,
        identical_okay: bool = False,
        circular_okay: bool = False
    ) -> Generator[Tuple[dict, dict, bool], None, None]:
        """
        A low-level hook that emits each and every state update.
        All other state watchers are built upon this only.

        .. include:: /api/state/get_raw_update.rst
        """
        self._watcher.live = live
        self._watcher.timeout = timeout
        return self._watcher.main(
            live,
            timeout,
            identical_okay,
            circular_okay,
            self._ident,
            self._namespace_bytes,
        )

    def get_when_change(
        self, *keys: Hashable, exclude: bool = False, **watcher_kwargs
    ) -> dict:
        """
        Block until a change is observed, and then return a copy of the state.

        .. include:: /api/state/get_when_change.rst
        """
        if len(keys):
            keys = set(keys)

            def select_keys():
                selected = {*before.keys(), *after.keys()}
                if exclude:
                    return selected - keys
                else:
                    return selected & keys

            for before, after, _, _ in self.get_raw_update(**watcher_kwargs):
                try:
                    if any(before[key] != after[key] for key in select_keys()):
                        return after
                except KeyError:  # this indirectly implies that something changed
                    return after
        else:
            for update in self.get_raw_update(**watcher_kwargs):
                yield update[1]

    def get_when(self, test_fn, **watcher_kwargs) -> dict:
        """
        Block until ``test_fn(snap)`` returns a "truthy" value,
        and then return a copy of the state.

        *Where-*

        ``snap`` is a ``dict``, containing a copy of the state.

        .. include:: /api/state/get_when.rst
        """
        snap = self.copy()
        if test_fn(snap):
            return snap

        with self.get_raw_update(
            live=live, timeout=timeout, identical_okay=identical_okay
        ) as get:
            while True:
                snap = get()[1]
                if test_fn(snap):
                    return snap

    def get_when_equal(self, key: Hashable, value: Any, **watcher_kwargs) -> dict:
        """
        Block until ``state[key] == value``, and then return a copy of the state.

        .. include:: /api/state/get_when_equality.rst
        """

        def _(snap):
            try:
                return snap[key] == value
            except KeyError:
                return False

        return self.get_when(
            _, live=live, timeout=timeout, identical_okay=identical_okay
        )

    def get_when_not_equal(self, key: Hashable, value: Any, **watcher_kwargs) -> dict:
        """
        Block until ``state[key] != value``, and then return a copy of the state.

        .. include:: /api/state/get_when_equality.rst
        """

        def _(snap):
            try:
                return snap[key] != value
            except KeyError:
                return False

        return self.get_when(
            _, live=live, timeout=timeout, identical_okay=identical_okay
        )

    def get_when_none(self, key: Hashable, **watcher_kwargs) -> dict:
        """
        Block until ``state[key] is None``, and then return a copy of the state.

        .. include:: /api/state/get_when_equality.rst
        """

        def _(snap):
            try:
                return snap[key] is None
            except KeyError:
                return False

        return self.get_when(
            _, live=live, timeout=timeout, identical_okay=identical_okay
        )

    def get_when_not_none(self, key: Hashable, **watcher_kwargs) -> dict:
        """
        Block until ``state[key] is not None``, and then return a copy of the state.

        .. include:: /api/state/get_when_equality.rst
        """

        def _(snap):
            try:
                return snap[key] is not None
            except KeyError:
                return False

        return self.get_when(
            _, live=live, timeout=timeout, identical_okay=identical_okay
        )

    def get_when_available(self, key: Hashable, **watcher_kwargs):
        """
        Block until ``key in state``, and then return a copy of the state.

        .. include:: /api/state/get_when_equality.rst
        """
        return self.get_when(
            lambda snap: key in snap,
            live=live,
            timeout=timeout,
            identical_okay=identical_okay,
        )

    def ping(self, **kwargs):
        """
        Ping the zproc server corresponding to this State's Context

        :param kwargs: Keyword arguments that :py:func:`ping` takes, except ``server_address``.
        :return: Same as :py:func:`ping`
        """
        return tools.ping(self.server_address, **kwargs)

    def __del__(self):
        try:
            self._dealer.close()
            self._subscriber.close()
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
        - The wrapped ``fn`` receives a frozen version (snap) of state,
          which is a ``dict`` object, not a :py:class:`State` object.

    Please read :ref:`atomicity` for a detailed explanation.

    :param fn:
        The function to be wrapped, as an atomic function.

    :returns:
        A wrapper function.

        The wrapper function returns the value returned by the wrapped ``fn``.

    >>> import zproc
    >>>
    >>> @zproc.atomic
    ... def increment(snap):
    ...     return snap['count'] + 1
    ...
    >>>
    >>> ctx = zproc.Context()
    >>> ctx.state['count'] = 0
    >>>
    >>> increment(ctx.state)
    1
    """

    serialized = serializer.dumps_fn(fn)

    @wraps(fn)
    def wrapper(state: State, *args, **kwargs):
        return state._req_rep(
            {
                Msgs.cmd: Commands.run_fn_atomically,
                Msgs.info: serialized,
                Msgs.args: args,
                Msgs.kwargs: kwargs,
            }
        )

    return wrapper
