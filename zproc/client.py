import multiprocessing
import pprint
import signal
from textwrap import indent
from typing import Callable, Any, Union, Mapping, Sequence, Hashable, List, Optional

from decouple import config

from zproc.process.api import ProcessAPI
from zproc.state.api import StateAPI, StateWatcher
from . import util, atomicity
from .consts import DEFAULT_NAMESPACE
from .server import tools
from .task.swarm import Swarm


class Client:
    keys = atomicity.keys
    values = atomicity.values
    items = atomicity.items
    call = atomicity.call
    apply = atomicity.apply
    get = atomicity.get
    set = atomicity.set
    update = atomicity.update
    __contains__ = atomicity.__contains__
    clear = atomicity.clear

    _namespace: bytes

    def __init__(
        self,
        server_address: str = None,
        *,
        value: dict = None,
        start_server: bool = True,
        backend: Callable = multiprocessing.Process,
        wait: bool = False,
        cleanup: bool = True,
        namespace: str = DEFAULT_NAMESPACE,
        **process_kwargs,
    ) -> None:
        r"""
        The main interface class for ZProc.

        Can be used to launch processes and access state, stored on a server process.

        All processes launched using a Context, share the same state.

        Don't share a Context object between Processes / Threads.
        A Context object is not thread-safe.

        :param server_address:
            The address of the server.

            If this is set to ``None``, a random address will be generated.
        :param start_server:
            Whether to start the ZProc server.
            It is started automatically by default.

            If this is set to ``None``, then you must either -

            - Start a server using a different Context object.
            - Start one manually, using :py:func:`start_server`.

            In both cases,
            it the user's responsibility to make sure that the ``server_address`` argument
            is satisfied.

            .. note::

                If the server is not started before-hand,
                the Context object will block infinitely, waiting for the server to respond.

                In case you want to play around,
                the :py:func:`ping` function is handy,
                since it let's you *detect* the presence of a server at a given address.
        :param backend:
            .. include:: /api/snippets/backend.rst
        :param wait:
            Wait for all running process to finish their work before exiting.

            Alternative to manually calling :py:meth:`~Context.wait` at exit.
        :param cleanup:
            Whether to cleanup the process tree before exiting.

            Registers a signal handler for ``SIGTERM``, and an ``atexit`` handler.
        :param \*\*process_kwargs:
            Keyword arguments that :py:class:`~Process` takes,
            except ``server_address`` and ``target``.

            If provided,
            these will be used while creating processes using this Context.
        """
        self.namespace = namespace

        self.process_kwargs: dict = process_kwargs
        """Passed from the constructor."""

        self.server_address: str = server_address
        """The server's address. (Readonly)"""

        self.server_process: Optional[multiprocessing.Process] = None
        """The :py:class:`multiprocessing.Process` object for the server. (Readonly)"""

        self.wait_enabled = wait
        """Passed from the constructor. (Readonly)"""
        self.cleanup_enabled = cleanup
        """Passed from the constructor. (Readonly)"""
        self.backend = backend
        """Passed from the constructor. (Readonly)"""

        if server_address is None:
            server_address = config("ZPROC_SERVER_ADDRESS", default=None)
        if start_server:
            self.server_process, self.server_address = tools.start_server(
                server_address, backend=backend
            )
        assert self.server_address is not None, (
            "Couldn't determine the server address. "
            "Hint: Either provide the `server_address` parameter, "
            "or pass `start_server=True`."
        )

        self._process = ProcessAPI(self)
        self._state = StateAPI(self)

        if value is not None:
            self.update(value)

        if cleanup and util.is_main_thread():
            signal.signal(signal.SIGTERM, util.clean_process_tree)
        util.register_atexit(wait, self._process.wait, cleanup)

    @property
    def namespace(self) -> str:
        """The namespace to use while communicating with the server."""
        return self._namespace.decode()

    @namespace.setter
    def namespace(self, value: str):
        self._namespace = value.encode()

    def __str__(self):
        pretty = "↳" + indent(pprint.pformat(self.get()), " " * 2)[1:]
        return f"{self.__class__.__qualname__} to {self.server_address!r} at {id(self):#x}\n{pretty}"

    def __repr__(self):
        return util.enclose_in_brackets(self.__str__())

    def ready(self, value):
        pass

    def fork(self, *, value=None, namespace: str = None):
        if value is None:
            value = {}
        if namespace is None:
            namespace = self.namespace

        return Client(
            server_address=self.server_address,
            value=self.get().update(value),
            start_server=False,
            backend=self.backend,
            wait=self.wait_enabled,
            cleanup=self.cleanup_enabled,
            namespace=namespace,
            **self.process_kwargs,
        )

    def create_swarm(self, count: int = None):
        swarm = Swarm(self.server_address, namespace=self.namespace)
        swarm.start(count)
        return swarm

    #
    # Generated by codegen.py
    #

    def ping(self, **kwargs):
        """
        Ping the zproc server connected to this Client.

        :param kwargs: Keyword arguments that :py:func:`ping` takes, except ``server_address``.
        :return: Same as :py:func:`ping`
        """
        return self._state.ping(**kwargs)

    def time(self) -> float:

        return self._state.time()

    def when(
        self,
        test_fn,
        *,
        args: Sequence = None,
        kwargs: Mapping = None,
        live: bool = False,
        timeout: float = None,
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
        return self._state.when(
            test_fn,
            args=args,
            kwargs=kwargs,
            live=live,
            timeout=timeout,
            start_time=start_time,
            count=count,
        )

    def when_available(self, key: Hashable, **when_kwargs) -> StateWatcher:
        """
        Block until ``key in state``, and then return a copy of the state.

        .. include:: /api/state/get_when_equality.rst
        """
        return self._state.when_available(key, **when_kwargs)

    def when_change(
        self,
        *keys: Hashable,
        exclude: bool = False,
        live: bool = False,
        timeout: float = None,
        start_time: bool = None,
        count: int = None,
    ) -> StateWatcher:
        """
        Block until a change is observed, and then return a copy of the state.

        .. include:: /api/state/get_when_change.rst
        """
        return self._state.when_change(
            exclude=exclude,
            live=live,
            timeout=timeout,
            start_time=start_time,
            count=count,
            *keys,
        )

    def when_change_raw(
        self,
        *,
        live: bool = False,
        timeout: float = None,
        start_time: bool = None,
        count: int = None,
    ) -> StateWatcher:
        """
        A low-level hook that emits each and every state update.
        All other state watchers are built upon this only.

        .. include:: /api/state/get_raw_update.rst
        """
        return self._state.when_change_raw(
            live=live, timeout=timeout, start_time=start_time, count=count
        )

    def when_equal(self, key: Hashable, value: Any, **when_kwargs) -> StateWatcher:
        """
        Block until ``state[key] == value``, and then return a copy of the state.

        .. include:: /api/state/get_when_equality.rst
        """
        return self._state.when_equal(key, value, **when_kwargs)

    def when_not_equal(self, key: Hashable, value: Any, **when_kwargs) -> StateWatcher:
        """
        Block until ``state[key] != value``, and then return a copy of the state.

        .. include:: /api/state/get_when_equality.rst
        """
        return self._state.when_not_equal(key, value, **when_kwargs)

    def when_falsy(self, key: Hashable, **when_kwargs) -> StateWatcher:

        return self._state.when_falsy(key, **when_kwargs)

    def when_truthy(self, key: Hashable, **when_kwargs) -> StateWatcher:

        return self._state.when_truthy(key, **when_kwargs)

    def when_none(self, key: Hashable, **when_kwargs) -> StateWatcher:
        """
        Block until ``state[key] is None``, and then return a copy of the state.

        .. include:: /api/state/get_when_equality.rst
        """
        return self._state.when_none(key, **when_kwargs)

    def when_not_none(self, key: Hashable, **when_kwargs) -> StateWatcher:
        """
        Block until ``state[key] is not None``, and then return a copy of the state.

        .. include:: /api/state/get_when_equality.rst
        """
        return self._state.when_not_none(key, **when_kwargs)

    def spawn(self, *targets: Callable, count: int = 1, **process_kwargs):
        r"""
        Produce one or many child process(s) bound to this context.

        :param \*targets:
            Passed on to the :py:class:`Process` constructor, one at a time.

        :param count:
            The number of processes to spawn for each item in ``targets``.

        :param \*\*process_kwargs:
            .. include:: /api/context/params/process_kwargs.rst

        :return:
            A ``ProcessList`` of the :py:class:`Process` instance(s) produced.
        """
        return self._process.spawn(count=count, *targets, **process_kwargs)

    def spawn_map(
        self,
        target: Callable,
        map_iter: Sequence[Any] = None,
        *,
        map_args: Sequence[Sequence[Any]] = None,
        args: Sequence = None,
        map_kwargs: Sequence[Mapping[str, Any]] = None,
        kwargs: Mapping = None,
        **process_kwargs,
    ):

        return self._process.spawn_map(
            target,
            map_iter,
            map_args=map_args,
            args=args,
            map_kwargs=map_kwargs,
            kwargs=kwargs,
            **process_kwargs,
        )

    def wait(
        self, timeout: Union[int, float] = None, safe: bool = False
    ) -> List[Union[Any, Exception]]:
        """
        alias for :py:meth:`ProcessList.wait()`
        """
        return self._process.wait(timeout, safe)

    def start_all(self):
        """
        alias for :py:meth:`ProcessList.start_all()`
        """
        return self._process.start_all()

    def stop_all(self):
        """
        alias for :py:meth:`ProcessList.stop_all()`
        """
        return self._process.stop_all()

    #
    # End of generated code
    #
