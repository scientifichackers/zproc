import functools
import itertools
import os
import pickle
import time
from typing import Union, Hashable

import zmq

from zproc import tools, util
from zproc.server import ServerFn, Msg

ZMQ_IDENTITY_LEN = 8


def _state_watcher_decorator_gen(self: "State", live: bool):
    """Generates a template for a state watcher mainloop."""

    def decorator(wrapped_fn):
        @functools.wraps(wrapped_fn)
        def wrapper():
            if live:
                subscribe_sock = self._subscribe_sock_gen()
            else:
                subscribe_sock = self._subscribe_sock

            try:
                return wrapped_fn(subscribe_sock)
            finally:
                if live:
                    subscribe_sock.close()

        return wrapper

    return decorator


class State:
    def __init__(self, server_address):
        """
        Allows accessing state stored on the zproc server, through a dict-like API.

        Communicates to the zproc server using the ZMQ sockets.

        Don't share a State object between Processes / Threads.
        A State object is not thread-safe.

        Boasts the following ``dict``-like members, for accessing the state:

        - Magic  methods:
            ``__contains__()``,  ``__delitem__()``, ``__eq__()``,
            ``__getitem__()``, ``__iter__()``,
            ``__len__()``, ``__ne__()``, ``__setitem__()``

        - Methods:
            ``clear()``, ``copy()``, ``fromkeys()``, ``get()``,
            ``items()``,  ``keys()``, ``pop()``, ``popitem()``,
            ``setdefault()``, ``update()``, ``values()``

        :param server_address:
            The address of zproc server.
            (See :ref:`zproc-server-address-spec`)

            If you are using a :py:class:`Context`, then this is automatically provided.

        :ivar server_address: Passed on from constructor
        """

        self._zmq_ctx = zmq.Context()
        self._zmq_ctx.setsockopt(zmq.LINGER, 0)

        self.server_address = server_address
        self._dealer_sock_address, self._subscribe_sock_address = server_address

        self._identity = os.urandom(ZMQ_IDENTITY_LEN)

        self._dealer_sock = self._zmq_ctx.socket(zmq.DEALER)
        self._dealer_sock.setsockopt(zmq.IDENTITY, self._identity)
        self._dealer_sock.connect(self._dealer_sock_address)

        self._subscribe_sock = self._subscribe_sock_gen()

    def _subscribe_sock_gen(self):
        sock = self._zmq_ctx.socket(zmq.SUB)
        sock.connect(self._subscribe_sock_address)

        # prevents consuming our own updates, resulting in an circular message
        sock.setsockopt(zmq.SUBSCRIBE, self._identity)
        sock.setsockopt(zmq.INVERT_MATCHING, 1)

        return sock

    @staticmethod
    def _subscribe(subscribe_sock, timeout, start_time=None):
        old_timeout = subscribe_sock.getsockopt(zmq.RCVTIMEO)

        if timeout is not None:
            subscribe_sock.setsockopt(zmq.RCVTIMEO, int(timeout * 1000))
        else:
            subscribe_sock.setsockopt(zmq.RCVTIMEO, -1)

        try:
            response = util.handle_remote_response(
                pickle.loads(subscribe_sock.recv()[ZMQ_IDENTITY_LEN:])
            )
        except zmq.error.Again:
            raise TimeoutError("Timed-out while waiting for a state update.")
        else:
            if (
                timeout is not None
                and start_time is not None
                and time.time() - start_time > timeout
            ):
                raise TimeoutError("Timed-out while waiting for a state update.")
            return response
        finally:
            subscribe_sock.setsockopt(zmq.RCVTIMEO, old_timeout)

    def _req_rep(self, request):
        self._dealer_sock.send_pyobj(request, protocol=pickle.HIGHEST_PROTOCOL)
        response = self._dealer_sock.recv_pyobj()

        return util.handle_remote_response(response)

    def get_when_change(
        self,
        *keys: Hashable,
        exclude: bool = False,
        live: bool = True,
        timeout: Union[None, float, int] = None
    ):
        """
        | Block until a change is observed.

        :param \*keys:
            Observe for changes in these ``dict`` key(s).

            If no key is provided, any change in the ``state`` is respected.
        :param exclude:
            Reverse the lookup logic i.e.,

            Watch for changes in all ``dict`` keys *except* \*keys.

            If \*keys is not provided, then this has no effect.
        :param live:
            Whether to get "live" updates. (See :ref:`live-events`)
        :param timeout:
            Sets the timeout in seconds. By default it is set to ``None``.

            If the value is 0, it will return immediately, with a ``TimeoutError``,
            if no update is available.

            If the value is ``None``, it will block until an update is available.

            For all other values, it will wait for and update,
            for that amount of time before returning with a ``TimeoutError``.

        :return: Roughly,

        .. code-block:: python

            if exclude:
                return state.copy()

            if len(keys) == 0:
                return state.copy()

            if len(keys) == 1:
                return state.get(key)

            if len(keys) > 1:
                return [state.get(key) for key in keys]
        """

        num_keys = len(keys)

        if num_keys:
            if exclude:

                def select_keys(old_state, new_state):
                    return (
                        key
                        for key in itertools.chain(old_state.keys(), new_state.keys())
                        if key not in keys
                    )

            else:

                def select_keys(old, new_state):
                    return (
                        key
                        for key in itertools.chain(old.keys(), new_state.keys())
                        if key in keys
                    )

            @_state_watcher_decorator_gen(self, live)
            def _get_state(sock):
                if timeout is None:
                    start_time = None
                else:
                    start_time = time.time()

                while True:
                    old_state, new_state = self._subscribe(sock, timeout, start_time)

                    for key in select_keys(old_state, new_state):
                        try:
                            old_val, new_val = old_state[key], new_state[key]
                        except KeyError:  # In a way, this implies something changed
                            return new_state
                        else:
                            if new_val != old_val:
                                return new_state

        else:

            @_state_watcher_decorator_gen(self, live)
            def _get_state(sock):
                return self._subscribe(sock, timeout)[1]

        current_state = _get_state()

        if exclude or num_keys == 0:
            return current_state
        elif num_keys == 1:
            return current_state.get(keys[0])
        else:
            return [current_state.get(key) for key in keys]

    def get_when(self, test_fn, *, live=True, timeout=None):
        """
         Block until ``test_fn(state)`` returns a True-like value.

         Where, ``state`` is a :py:class:`State` instance.

         Roughly, ``if test_fn(state): return state.copy()``

        :param test_fn: A ``function``, which is called on each state-change.
        :param live: Whether to get "live" updates. (See :ref:`live-events`)
        :param timeout: Sets the timeout in seconds. By default it is set to ``None``.

                        If the value is 0, it will return immediately, with a ``TimeoutError``,
                        if no update is available.

                        If the value is ``None``, it will block until an update is available.

                        For all other values, it will wait for and update,
                        for that amount of time before returning with a ``TimeoutError``.

        :return: state
        :rtype: ``dict``
        """

        @_state_watcher_decorator_gen(self, live)
        def mainloop(sock):
            if timeout is None:
                start_time = None
            else:
                start_time = time.time()
            latest_state = self.copy()

            while True:
                if test_fn(latest_state):
                    return latest_state

                latest_state = self._subscribe(sock, timeout, start_time)[-1]

        return mainloop()

    def get_when_equal(self, key, value, *, live=True, timeout=None):
        """
        Block until ``state.get(key) == value``.

        :param key: ``dict`` key
        :param value: ``dict`` value.
        :param live: Whether to get "live" updates. (See :ref:`live-events`)
        :param timeout: Sets the timeout in seconds. By default it is set to ``None``.

                        If the value is 0, it will return immediately, with a ``TimeoutError``,
                        if no update is available.

                        If the value is ``None``, it will block until an update is available.

                        For all other values, it will wait for and update,
                        for that amount of time before returning with a ``TimeoutError``.

        :return: ``state.get(key)``
        """

        @_state_watcher_decorator_gen(self, live)
        def mainloop(sock):
            if timeout is None:
                start_time = None
            else:
                start_time = time.time()
            latest_key = self.get(key)

            while True:
                if latest_key == value:
                    return latest_key

                latest_key = self._subscribe(sock, timeout, start_time)[-1].get(key)

        return mainloop()

    def get_when_not_equal(self, key, value, *, live=True, timeout=None):
        """
        Block until ``state.get(key) != value``.

        :param key: ``dict`` key.
        :param value: ``dict`` value.
        :param live: Whether to get "live" updates. (See :ref:`live-events`)
        :param timeout: Sets the timeout in seconds. By default it is set to ``None``.

                        If the value is 0, it will return immediately, with a ``TimeoutError``,
                        if no update is available.

                        If the value is ``None``, it will block until an update is available.

                        For all other values, it will wait for and update,
                        for that amount of time before returning with a ``TimeoutError``.

        :return: ``state.get(key)``
        """

        @_state_watcher_decorator_gen(self, live)
        def mainloop(sock):
            if timeout is None:
                start_time = None
            else:
                start_time = time.time()
            latest_key = self.get(key)

            while True:
                if latest_key != value:
                    return latest_key

                latest_key = self._subscribe(sock, timeout, start_time)[-1].get(key)

        return mainloop()

    def go_live(self):
        """
        Clear the events buffer, thus removing past events that were stored.

        (See :ref:`live-events`)
        """

        self._subscribe_sock.close()
        self._subscribe_sock = self._subscribe_sock_gen()

    def ping(self, **kwargs):
        """
        Ping the zproc server corresponding to this State's Context

        :param kwargs: Keyword arguments that :py:func:`ping` takes, except ``server_address``.
        :return: Same as :py:func:`ping`
        """

        return tools.ping(self.server_address, **kwargs)

    def close(self):
        """
        Close this State and disconnect with the Server
        """

        self._dealer_sock.close()
        self._subscribe_sock.close()
        util.close_zmq_ctx(self._zmq_ctx)

    def copy(self):
        return self._req_rep({Msg.server_fn: ServerFn.state_reply})

    def keys(self):
        return self.copy().keys()

    def items(self):
        return self.copy().items()

    def values(self):
        return self.copy().values()

    def __repr__(self):
        return "<{} value: {}>".format(State.__qualname__, self.copy())


_GENERATED_STATE_METHODS = {
    "__contains__",
    "__delitem__",
    "__eq__",
    "__getitem__",
    "__iter__",
    "__len__",
    "__ne__",
    "__setitem__",
    "clear",
    "fromkeys",
    "get",
    "pop",
    "popitem",
    "setdefault",
    "update",
}


def _remote_method_gen(state_method_name: str):
    """
    Generates a method for the State class,
    that will call the "method_name" on the dict stored as the state on the server,
    and return the result.

    Glorified RPC.

    (These could've been static methods in the State class,
    enabling better code completion in IDEs.
    But that's a little hard to maintain.)
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


for name in _GENERATED_STATE_METHODS:
    setattr(State, name, _remote_method_gen(name))
