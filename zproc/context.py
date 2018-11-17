import atexit
import functools
import multiprocessing
import pprint
import signal
import time
from contextlib import suppress
from typing import Callable, Union, Hashable, Any, List, Mapping, Sequence, Tuple, cast

from . import util
from .consts import DEFAULT_NAMESPACE
from .process import Process
from .server import tools
from .state.state import State
from .task.map_plus import map_plus
from .task.api import Workers


class ProcessList(list):
    def __str__(self):
        return ProcessList.__qualname__ + ": " + pprint.pformat(list(self))

    def __repr__(self):
        return "<" + self.__str__() + ">"

    @staticmethod
    def _wait_or_catch_exc(
        process: Process, timeout: Union[int, float] = None
    ) -> Union[Exception, Any]:
        try:
            return process.wait(timeout)
        except Exception as e:
            return e

    def wait(
        self, timeout: Union[int, float] = None, safe: bool = False
    ) -> List[Union[Any, Exception]]:
        """
        Call :py:meth:`~Process.wait()` on all the Processes in this list.

        :param timeout:
            Same as :py:meth:`~Process.wait()`.

            This parameter controls the timeout for all the Processes combined,
            not a single :py:meth:`~Process.wait()` call.
        :param safe:
            Suppress any errors that occur while waiting for a Process.

            The return value of failed :py:meth:`~Process.wait()` calls are substituted with the ``Exception`` that occurred.
        :return:
            A ``list`` containing the values returned by child Processes of this Context.
        """
        if safe:
            _wait = self._wait_or_catch_exc
        else:
            _wait = Process.wait

        if timeout is None:
            return [_wait(process) for process in self]
        else:
            final = time.time() + timeout
            return [_wait(process, final - time.time()) for process in self]

    def start_all(self):
        """
        Call :py:meth:`~Process.start()` on all the child processes of this Context

        Ignores if a Process is already started, unlike :py:meth:`~Process.start()`,
        which throws an ``AssertionError``.
        """
        with suppress(AssertionError):
            for process in self:
                process.start()

    def stop_all(self):
        """
        Call :py:meth:`~Process.stop()` on all the Processes in this list.

        Retains the same order as ``Context.process_list``.

        :return:
            A ``list`` containing the exitcodes of the child Processes of this Context.
        """
        return [proc.stop() for proc in self]


class Context:
    #: The :py:class:`multiprocessing.Process` object for the server.
    server_process: multiprocessing.Process

    def __init__(
        self,
        server_address: str = None,
        *,
        start_server: bool = True,
        backend: Callable = multiprocessing.Process,
        wait: bool = False,
        cleanup: bool = True,
        namespace: str = DEFAULT_NAMESPACE,
        **process_kwargs
    ) -> None:
        r"""
        Provides a high level interface to :py:class:`State` and :py:class:`Process`.

        Primarily used to manage and launch processes.

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
        #: A :py:class:`ProcessList` object containing all Processes created under this Context.
        self.process_list = ProcessList()
        #: Passed on from the constructor. This is read-only.
        self.backend = backend
        #: Passed on from the constructor. This is read-only.
        self.namespace = namespace
        #: Passed on from the constructor.
        self.process_kwargs = process_kwargs

        self.process_kwargs.setdefault("namespace", self.namespace)
        self.process_kwargs.setdefault("backend", self.backend)

        self.server_address = cast(str, server_address)
        """The server's address.
            
        This holds the address this Context is connected to,
        not necessarily the value provided in the constructor.
        
        This is read-only."""

        if start_server:
            self.start_server()

        assert self.server_address is not None, (
            "Couldn't determine the server address. "
            "Hint: Either provide the `server_address` parameter, "
            "or pass `start_server=True`."
        )

        self.state = State(self.server_address, namespace=self.namespace)
        self.workers = Workers(self.server_address, namespace=self.namespace)

        # register cleanup before wait, so that wait runs before cleanup.
        # (order of execution is reversed)
        if cleanup:
            atexit.register(util.clean_process_tree)
            if util.is_main_thread():
                signal.signal(signal.SIGTERM, util.clean_process_tree)
        if wait:
            atexit.register(self.wait)

    def __str__(self):
        return "%s - server: %r at %#x" % (
            self.__class__.__qualname__,
            self.server_address,
            id(self),
        )

    def __repr__(self):
        return util.enclose_in_brackets(self.__str__())

    def start_server(self) -> Tuple[multiprocessing.Process, str]:
        ret = tools.start_server(self.server_address, backend=self.backend)
        self.server_process, self.server_address = ret
        return ret

    def _process(
        self, target: Callable = None, **process_kwargs
    ) -> Union[Process, Callable]:
        r"""
        Produce a child process bound to this context.

        Can be used both as a function and decorator:

        .. code-block:: python
            :caption: Usage

            @zproc.process(pass_context=True)  # you may pass some arguments here
            def p1(ctx):
                print('hello', ctx)


            @zproc.process  # or not...
            def p2(state):
                print('hello', state)


            def p3(state):
                print('hello', state)

            zproc.process(p3)  # or just use as a good ol' function

        :param target:
            Passed on to the :py:class:`Process` constructor.

            *Must be omitted when using this as a decorator.*

        :param \*\*process_kwargs:
            .. include:: /api/context/params/process_kwargs.rst

        :return: The :py:class:`Process` instance produced.
        """
        process = Process(
            self.server_address, target, **{**self.process_kwargs, **process_kwargs}
        )
        self.process_list.append(process)
        return process

    def spwan(self, *targets: Callable, count: int = 1, **process_kwargs):
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

        if not targets:

            def wrapper(target: Callable):
                return self.spwan(target, count=count, **process_kwargs)

            return wrapper

        return ProcessList(
            self._process(target, **process_kwargs)
            for _ in range(count)
            for target in targets
        )

    def map_process(
        self,
        target: Callable,
        map_iter: Sequence[Any] = None,
        *,
        map_args: Sequence[Sequence[Any]] = None,
        args: Sequence = None,
        map_kwargs: Sequence[Mapping[str, Any]] = None,
        kwargs: Mapping = None,
        **process_kwargs
    ):
        process_kwargs.setdefault("pass_state", False)

        def _target(*a, **k):
            return self._process(target, args=a, kwargs=k, **process_kwargs)

        return ProcessList(
            map_plus(_target, map_iter, map_args, args, map_kwargs, kwargs)
        )

    def _create_call_when_xxx_decorator(
        self,
        get_when_xxx_fn_name: str,
        process_kwargs: dict,
        *state_watcher_args,
        **state_watcher_kwargs
    ):
        # can't work without the state!
        pass_state = process_kwargs.pop("pass_state", True)

        def decorator(wrapped_fn):
            if pass_state:

                def watcher_process(state, *args, **kwargs):
                    get_when_xxx_fn = getattr(state, get_when_xxx_fn_name)

                    while True:
                        wrapped_fn(
                            get_when_xxx_fn(
                                *state_watcher_args, **state_watcher_kwargs
                            ),
                            state,
                            *args,
                            **kwargs
                        )

            else:

                def watcher_process(state, *args, **kwargs):
                    get_when_xxx_fn = getattr(state, get_when_xxx_fn_name)

                    while True:
                        wrapped_fn(
                            get_when_xxx_fn(
                                *state_watcher_args, **state_watcher_kwargs
                            ),
                            *args,
                            **kwargs
                        )

            watcher_process = self._process(watcher_process, **process_kwargs)
            functools.update_wrapper(watcher_process.target, wrapped_fn)

            return watcher_process

        return decorator

    def call_when_change(
        self,
        *keys: Hashable,
        exclude: bool = False,
        live: bool = False,
        **process_kwargs
    ):
        """
        Decorator version of :py:meth:`~State.get_when_change()`.

        .. include:: /api/context/call_when_change.rst

        .. code-block:: python
            :caption: Example

            import zproc

            ctx = zproc.Context()

            @ctx.call_when_change('gold')
            def test(snap, state):
                print(snap['gold'], state)
        """
        return self._create_call_when_xxx_decorator(
            "get_when_change", process_kwargs, *keys, exclude=exclude, live=live
        )

    def call_when(self, test_fn: Callable, *, live: bool = False, **process_kwargs):
        """
        Decorator version of :py:meth:`~State.get_when()`.

        .. include:: /api/context/call_when.rst

        .. code-block:: python
            :caption: Example

            import zproc

            ctx = zproc.Context()

            @ctx.get_state_when(lambda state: state['trees'] == 5)
            def test(snap, state):
                print(snap['trees'], state)
        """
        return self._create_call_when_xxx_decorator(
            "get_when", process_kwargs, test_fn, live=live
        )

    def call_when_equal(
        self, key: Hashable, value: Any, *, live: bool = False, **process_kwargs
    ):
        """
        Decorator version of :py:meth:`~State.get_when_equal()`.

        .. include:: /api/context/call_when_equality.rst

        .. code-block:: python
            :caption: Example

            import zproc

            ctx = zproc.Context()

            @ctx.call_when_equal('oranges', 5)
            def test(snap, state):
                print(snap['oranges'], state)
        """
        return self._create_call_when_xxx_decorator(
            "get_when_equal", process_kwargs, key, value, live=live
        )

    def call_when_not_equal(
        self, key: Hashable, value: Any, *, live: bool = False, **process_kwargs
    ):
        """
        Decorator version of :py:meth:`~State.get_when_not_equal()`.

        .. include:: /api/context/call_when_equality.rst

        .. code-block:: python
            :caption: Example

            import zproc

            ctx = zproc.Context()

            @ctx.call_when_not_equal('apples', 5)
            def test(snap, state):
                print(snap['apples'], state)
        """
        return self._create_call_when_xxx_decorator(
            "get_when_not_equal", process_kwargs, key, value, live=live
        )

    def call_when_none(self, key: Hashable, *, live: bool = False, **process_kwargs):
        """
        Decorator version of :py:meth:`~State.get_when_none()`.

        .. include:: /api/context/call_when_equality.rst
        """
        return self._create_call_when_xxx_decorator(
            "get_when_none", process_kwargs, key, live=live
        )

    def call_when_not_none(
        self, key: Hashable, *, live: bool = False, **process_kwargs
    ):
        """
        Decorator version of :py:meth:`~State.get_when_not_none()`.

        .. include:: /api/context/call_when_equality.rst
        """
        return self._create_call_when_xxx_decorator(
            "get_when_not_none", process_kwargs, key, live=live
        )

    def call_when_available(
        self, key: Hashable, *, live: bool = False, **process_kwargs
    ):
        """
        Decorator version of :py:meth:`~State.get_when_available()`.

        .. include:: /api/context/call_when_equality.rst
        """
        return self._create_call_when_xxx_decorator(
            "get_when_available", process_kwargs, key, live=live
        )

    def wait(
        self, timeout: Union[int, float] = None, safe: bool = False
    ) -> List[Union[Any, Exception]]:
        """
        alias for :py:meth:`ProcessList.wait()`
        """
        return self.process_list.wait(timeout, safe)

    def start_all(self):
        """
        alias for :py:meth:`ProcessList.start_all()`
        """
        return self.process_list.stop_all()

    def stop_all(self):
        """
        alias for :py:meth:`ProcessList.stop_all()`
        """
        return self.process_list.stop_all()

    def ping(self, **kwargs):
        r"""
        Ping the zproc server.

        :param \*\*kwargs: Keyword arguments that :py:func:`ping` takes, except ``server_address``.
        :return: Same as :py:func:`ping`
        """
        return tools.ping(self.server_address, **kwargs)
