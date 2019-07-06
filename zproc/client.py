import atexit
import multiprocessing
import pprint
import signal
from textwrap import indent
from typing import Callable

from zproc.process.process_methods import ProcessMethods
from . import util, atomic
from .consts import DEFAULT_NAMESPACE
from .server import tools
from .state.state_methods import StateMethods
from .task.swarm import Swarm


class Client:
    server_process: multiprocessing.Process
    """
    The :py:class:`multiprocessing.Process` object for the server.    
    (Readonly)
    """

    server_address: str
    """
    The server's address.
    (Readonly)
    """

    process_kwargs: dict
    """
    Passed from the constructor.
    """

    _namespace: str
    _state: StateMethods
    _process: ProcessMethods

    ping = StateMethods.ping
    time = StateMethods.time
    when = StateMethods.when
    when_available = StateMethods.when_available
    when_change = StateMethods.when_change
    when_change_raw = StateMethods.when_change_raw
    when_equal = StateMethods.when_equal
    when_not_equal = StateMethods.when_not_equal
    when_falsy = StateMethods.when_falsy
    when_truthy = StateMethods.when_truthy
    when_none = StateMethods.when_none
    when_not_none = StateMethods.when_not_none

    spawn = ProcessMethods.spawn
    spawn_map = ProcessMethods.spawn_map
    wait = ProcessMethods.wait
    start_all = ProcessMethods.start_all
    stop_all = ProcessMethods.stop_all

    keys = atomic.keys
    values = atomic.values
    items = atomic.items
    call = atomic.call
    apply = atomic.apply
    get = atomic.get
    set = atomic.set
    merge = atomic.merge

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
        if start_server:
            self.server_process, self.server_address = tools.start_server(
                server_address, backend=backend
            )

        assert self.server_address is not None, (
            "Couldn't determine the server address. "
            "Hint: Either provide the `server_address` parameter, "
            "or pass `start_server=True`."
        )

        # register cleanup before wait, so that wait runs before cleanup.
        # (order of execution is reversed)
        if cleanup:
            atexit.register(util.clean_process_tree)
            if util.is_main_thread():
                signal.signal(signal.SIGTERM, util.clean_process_tree)
        if wait:
            atexit.register(self.wait)

        self._state = StateMethods(self)
        self.namespace = namespace
        self.process_kwargs = process_kwargs
        self._process = ProcessMethods(self)
        if value is not None:
            self.merge(value)

    @property
    def namespace(self) -> str:
        return self._namespace

    @namespace.setter
    def namespace(self, value: str):
        self._state.namespace = value
        self._namespace = value

    def __str__(self):
        pretty = "↳" + indent(pprint.pformat(self.copy()), " " * 2)[1:]
        return f"{self.__class__.__qualname__} to {self.server_address!r} at {id(self):#x}\n{pretty}"

    def __repr__(self):
        return util.enclose_in_brackets(self.__str__())

    def create_swarm(self, count: int = None):
        swarm = Swarm(self.server_address, namespace=self.namespace)
        swarm.start(count)
        return swarm
