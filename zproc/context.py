import atexit
import collections
import functools
import multiprocessing
import pickle
import signal
from typing import (
    Tuple,
    Callable,
    Union,
    Hashable,
    Iterable,
    Any,
    List,
    Mapping,
    Generator,
    Sequence,
)

import zmq

from zproc import processdef, tools, util
from zproc.process import Process
from zproc.state import State

# holds the details about a task
TaskDetail = collections.namedtuple("TaskDetail", ["task_number", "chunk_count"])

# holds the details of a chunk in the task
ChunkDetail = collections.namedtuple("ChunkDetail", ["list_index"])


class Context:
    def __init__(
        self,
        server_address: tuple = None,
        *,
        wait: bool = False,
        cleanup: bool = True,
        server_backend: Callable = multiprocessing.Process,
        **process_kwargs
    ):
        """
        Provides a high level interface to :py:class:`State` and :py:class:`Process`.

        Primarily used to manage and launch processes.

        All processes launched using a Context, share the same state.

        Don't share a Context object between Processes / Threads.
        A Context object is not thread-safe.

        :param server_address:
            The address of the server.
            (See :ref:`zproc-server-address-spec`)

            If set to ``None``,
            then a new server is started and a random address will be used.

            Otherwise, it will connect to an existing server with the address provided.

            .. caution::

                If you provide a "server_address", be sure to manually start the server,
                as described here - :ref:`start-server`.

        :param wait:
            Wait for all running process to finish their work before exiting.

            Alternative to manually calling :py:meth:`~Context.wait_all` at exit.

        :param cleanup:
            Whether to cleanup the process tree before exiting.

            Registers a signal handler for ``SIGTERM``, and an ``atexit`` handler.

        :param server_backend:
            Passed on to :py:func:`start_server` as ``backend``.

        :param \*\*process_kwargs:
            Keyword arguments that :py:class:`~Process` takes,
            except ``server_address`` and ``target``.

            If provided, these will be used while creating
            processes using this Context.

        :ivar state:
            A :py:class:`State` instance.

        :ivar process_list:
            A list of child ``Process``\ (s) created under this Context.

        :ivar worker_list:
            A list of worker ``Process``\ (s) created under this Context.
            Used for :py:meth:`Context.process_map`.

        :ivar server_process:
            A ``multiprocessing.Process`` object for the server, or None.

        :ivar server_address:
            The server's address as a 2 element ``tuple``.
        """

        self._kwargs = process_kwargs

        if server_address is None:
            self.server_process, self.server_address = tools.start_server(
                server_address, backend=server_backend
            )
        else:
            self.server_process, self.server_address = None, server_address
        self.state = State(self.server_address)

        self.process_list = []
        self.worker_list = []

        self._push_sock = self.state._zmq_ctx.socket(zmq.PUSH)
        self._push_address = util.bind_to_random_address(self._push_sock)

        self._pull_sock = self.state._zmq_ctx.socket(zmq.PULL)
        self._pull_address = util.bind_to_random_address(self._pull_sock)

        self._task_counter = 0

        # Dict[_TaskDetail, Dict[_ChunkDetail, Any]]
        self._task_chunk_results = collections.defaultdict(dict)

        if cleanup:
            signal.signal(signal.SIGTERM, util.clean_process_tree)
            atexit.register(util.clean_process_tree)
        if wait:
            atexit.register(self.wait_all)

    def process(
        self, target: Union[None, Callable] = None, **process_kwargs
    ) -> Union[Process, Callable]:
        """
        Produce a child process bound to this context.

        Can be used both as a function and decorator:

        .. code-block:: python
            :caption: Usage

            @zproc.process()  # you may pass some arguments here
            def my_process1(state):
                    print('hello')


            @zproc.process  # or not...
            def my_process2(state):
                print('hello')


            def my_process3(state):
                print('hello')

            zproc.process(my_process3)  # or just use as a good ol' function

        :param target:
            Passed on to the :py:class:`Process` constructor.

            SHOULD be omitted when using this as a decorator.

        :param \*\*process_kwargs:
            Keyword arguments that :py:class:`Process` takes, except ``server_address`` and ``target``.

        :return: The :py:class:`Process` instance produced.
        """

        if not callable(target):

            def decorator(fn, **kwargs):
                return self.process(fn, **kwargs)

            return functools.partial(decorator, **process_kwargs)

        process_kwargs.update(self._kwargs)

        process = Process(self.server_address, target, **process_kwargs)
        self.process_list.append(process)
        return process

    def process_factory(self, *targets: Callable, count: int = 1, **process_kwargs):
        """
        Produce multiple child process(s) bound to this context.

        :param \*targets:
            Passed on to the :py:class:`Process` constructor, one at a time.

        :param count:
            The number of processes to spawn for each item in ``targets``.

        :param \*\*process_kwargs:
            Keyword arguments that :py:class:`Process` takes, except ``server_address`` and ``target``.

        :return:
            The ``list`` of :py:class:`Process` instance(s) produced.
        """

        return [
            self.process(target, **process_kwargs)
            for target in targets
            for _ in range(count)
        ]

    def _populate_workers(self, size: int, new: bool = False):
        if not new:
            size -= len([worker for worker in self.worker_list if worker.is_alive])

        if size > 0:
            for _ in range(size):
                self.worker_list.append(
                    self.process(
                        processdef.process_map_worker,
                        # must be in reverse order for this to work
                        # i.e. first pull addr, then push addr.
                        args=(self._pull_address, self._push_address),
                    )
                )
        elif size < 0:
            # Notify "size" no. of workers to finish up, and close shop.
            for _ in range(-size):
                self._push_sock.send_pyobj(0)

    def _pull_results_for_task(
        self, task_detail: TaskDetail
    ) -> Generator[Any, None, None]:
        """
        PULL "count" results from the process pool.
        Also arranges the results in-order.
        """

        task_chunks = self._task_chunk_results[task_detail]

        while len(task_chunks) < task_detail.chunk_count:
            this, list_index, chunk_result = util.handle_remote_response(
                self._pull_sock.recv_pyobj()
            )
            self._task_chunk_results[this][list_index] = chunk_result

        for i in sorted(task_chunks.keys()):
            yield from task_chunks[i]

    def process_map(
        self,
        target: Callable,
        map_iter: Sequence[Any] = None,
        *,
        map_args: Sequence[Iterable[Any]] = None,
        args=None,
        map_kwargs: Sequence[Mapping[str, Any]] = None,
        kwargs=None,
        count: int = None,
        stateful: bool = False,
        new=False
    ) -> Generator[Any, None, None]:
        """
        Functional equivalent of ``map()`` in-built function, but executed in a parallel fashion.

        Distributes the iterables provided in the ``map_*`` arguments to ``count`` no of worker :py:class:`Process`\ (s).

        (Aforementioned worker processes are visible here: :py:attr:`Context.worker_list`)

        The idea is to:
            1. Split the the iterables provided in the ``map_*`` arguments into ``count`` number of equally sized chunks.
            2. Send these chunks to ``count`` number of worker :py:class:`Process`\ (s).
            3. Wait for all these worker :py:class:`Process`\ (s) to finish their task(s).
            4. Combine the acquired results in the same sequence as provided in the ``map_*`` arguments.
            5. Return the combined results.

            *Steps 3-5 are done lazily, on the fly with the help of a* ``generator``

        .. note::
            This function will NOT spawn new worker :py:class:`Process`\ (s), each time it is called.

            Existing workers will be used if a sufficient amount is available.
            If the workers are busy, then this will wait for them to finish up their current work.

            Use the ``new=True`` Keyword Argument to spawn new workers, irregardless of existing ones.

            You need not worry about shutting down workers.
            ZProc will take care of that automatically.

        :param target:
            The ``Callable`` to be invoked inside a :py:class:`Process`.

            *It is invoked with the following signature:*

                ``target(state, map_iter[i], *map_args[i], *args, **map_kwargs[i], **kwargs)``

            *Where:*

                - ``state`` is a :py:class:`State` instance.
                  (Disabled by default. Use the ``stateful`` Keyword Argument to enable)

                - ``i`` is the index of n\ :sup:`th` element of the Iterable(s) provided in the ``map_*`` arguments.

                - ``args`` and ``kwargs`` are passed from the ``**process_kwargs``.

            P.S. The ``stateful`` Keyword Argument of :py:class:`Process` allows you to omit the ``state`` arg.

        :param map_iter:
            A sequence whose elements are supplied as the *first* positional argument (after ``state``) to the ``target``.

        :param map_args:
            A sequence whose elements are supplied as positional arguments (``*args``) to the ``target``.

        :param map_kwargs:
            A sequence whose elements are supplied as keyword arguments (``**kwargs``) to the ``target``.

        :param args:
            The argument tuple for ``target``, supplied after ``map_iter`` and ``map_args``.

            By default, it is an empty ``tuple``.

        :param kwargs:
            A dictionary of keyword arguments for ``target``.

            By default, it is an empty ``dict``.

        :param stateful:
            Weather this process needs to access the state.

            If this is set to ``False``,
            then the ``state`` argument won't be provided to the ``target``.

            If this is set to ``True``,
            then a :py:class:`State` object is provided as the first Argument to the ``target``.

            Unlike :py:class:`Process` it is set to ``False`` by default.
            (To retain a similar API to in-built ``map()``)

        :param new:
            Weather to spawn new workers.

            If it is set to ``True``,
            then it will spawn new workers, irregardless of existing ones.

            If it is set to ``False``,
            then ``size - len(Context.worker_list)`` will be spawned.

            Un-used workers are thrashed automatically.

        :param count:
            The number of worker :py:class:`.Process` (s) to use.

            By default, it is set to ``multiprocessing.cpu_count()``
            (The number of CPU cores on your system)


        :return:
            The result is quite similar to ``map()`` in-built function.

            It returns a ``generator`` whose elements are the return value of the ``target`` function,
            when applied to every item of the Iterables provided in the ``map_*`` arguments.

            The actual "processing" starts as soon as you call this function.

            The returned ``generator`` only "waits" for the results from the worker processes.

        .. warning::
            - If ``len(map_iter) != len(maps_args) != len(map_kwargs)``,
              then the results will be cut-off at the shortest Sequence.

        See :ref:`process_map` for Examples.
        """

        if count is None:
            count = multiprocessing.cpu_count()
        if args is None:
            args = ()
        if kwargs is None:
            kwargs = {}

        task_detail = TaskDetail(task_number=self._task_counter, chunk_count=count)
        self._task_counter += 1
        self._populate_workers(count, new)

        lengths = [len(i) for i in (map_iter, map_args, map_kwargs) if i is not None]
        assert (
            lengths
        ), 'At least one of "map_iter", "map_args", or "map_kwargs" must be provided as a non-empty sequence.'

        chunk_size, extra = divmod(min(lengths), count)
        if extra:
            chunk_size += 1

        chunks = (
            util.chunk_gen(map_iter, chunk_size, count),
            util.chunk_gen(map_args, chunk_size, count),
            util.chunk_gen(map_kwargs, chunk_size, count),
        )
        # print(smallest, chunk_size, count, chunks)

        for i in range(count):
            self._push_sock.send_pyobj(
                (
                    task_detail,
                    i,
                    None if chunks[0] is None else chunks[0][i],
                    None if chunks[1] is None else chunks[1][i],
                    None if chunks[2] is None else chunks[2][i],
                    stateful,
                    target,
                    args,
                    kwargs,
                ),
                protocol=pickle.HIGHEST_PROTOCOL,
            )

        return self._pull_results_for_task(task_detail)

    def _create_watcher_decorator(
        self, state_watcher_fn_name: str, process_kwargs: dict, *args, **kwargs
    ):
        stateful = process_kwargs.pop("stateful", True)

        def decorator(wrapped_fn):
            if stateful:

                def watcher_process(state, *wrapped_fn_args, **wrapped_fn_kwargs):
                    state_watcher_fn = getattr(state, state_watcher_fn_name)

                    while True:
                        state_watcher_fn(*args, **kwargs)
                        wrapped_fn(state, *wrapped_fn_args, **wrapped_fn_kwargs)

            else:

                def watcher_process(state, *wrapped_fn_args, **wrapped_fn_kwargs):
                    state_watcher_fn = getattr(state, state_watcher_fn_name)

                    while True:
                        state_watcher_fn(*args, **kwargs)
                        wrapped_fn(*wrapped_fn_args, **wrapped_fn_kwargs)

            watcher_process = self.process(watcher_process, **process_kwargs)
            functools.update_wrapper(watcher_process.target, wrapped_fn)

            return watcher_process

        return decorator

    def call_when_change(
        self,
        *keys: Hashable,
        exclude: bool = False,
        live: bool = True,
        **process_kwargs
    ):
        """
        Decorator version of :py:meth:`~State.get_when_change()`.

        Spawns a new Process that watches the state and calls the wrapped function forever.

        :param \*\*process_kwargs: Keyword arguments that :py:class:`Process` takes, except ``server_address``.

        All other parameters have same meaning as :py:meth:`~State.get_when_change()`

        :return: A decorator function

                The decorator function will return the :py:class:`Process` instance created

        .. code-block:: python
            :caption: Example

            import zproc

            ctx = zproc.Context()

            @ctx.call_when_change()
            def test(state):
                print(state)
        """

        return self._create_watcher_decorator(
            "get_when_change", process_kwargs, *keys, exclude, live=live
        )

    def call_when(self, test_fn: Callable, *, live: bool = True, **process_kwargs):
        """
        Decorator version of :py:meth:`~State.get_when()`.

        Spawns a new Process that watches the state and calls the wrapped function forever.

        :param \*\*process_kwargs: Keyword arguments that :py:class:`Process` takes, except ``server_address``.

        All other parameters have same meaning as :py:meth:`~State.get_when()`

        :return: A decorator function

                The decorator function will return the :py:class:`Process` instance created


        .. code-block:: python
            :caption: Example

            import zproc

            ctx = zproc.Context()

            @ctx.get_state_when(lambda state: state['foo'] == 5)
            def test(state):
                print(state)
        """

        return self._create_watcher_decorator(
            "get_when", process_kwargs, test_fn, live=live
        )

    def call_when_equal(
        self, key: Hashable, value: Any, *, live: bool = True, **process_kwargs
    ):
        """
        Decorator version of :py:meth:`~State.get_when_equal()`.

        Spawns a new Process that watches the state and calls the wrapped function forever.

        :param \*\*process_kwargs: Keyword arguments that :py:class:`Process` takes, except ``server_address``.

        All other parameters have same meaning as :py:meth:`~State.get_when_equal()`

        :return: A decorator function

                The decorator function will return the :py:class:`Process` instance created


        .. code-block:: python
            :caption: Example

            import zproc

            ctx = zproc.Context()

            @ctx.call_when_equal('foo', 5)
            def test(state):
                print(state)
        """

        return self._create_watcher_decorator(
            "get_when_equal", process_kwargs, key, value, live=live
        )

    def call_when_not_equal(
        self, key: Hashable, value: Any, *, live: bool = True, **process_kwargs
    ):
        """
        Decorator version of :py:meth:`~State.get_when_not_equal()`.

        Spawns a new Process that watches the state and calls the wrapped function forever.

        :param \*\*process_kwargs: Keyword arguments that :py:class:`Process` takes, except ``server_address``.

        All other parameters have same meaning as :py:meth:`~State.get_when_not_equal()`

        :return:
            A decorator function

            The decorator function will return the :py:class:`Process` instance created


        .. code-block:: python
            :caption: Example

            import zproc

            ctx = zproc.Context()

            @ctx.call_when_not_equal('foo', 5)
            def test(state):
                print(state)
        """

        return self._create_watcher_decorator(
            "get_when_not_equal", process_kwargs, key, value, live=live
        )

    def wait_all(self) -> List[Tuple[Process, Any]]:
        """
        Call :py:meth:`~Process.wait()` on all the child processes of this Context.
        (Excluding the worker processes)

        :return:
            A ``list`` of 2-value ``tuple`` (s),
            containing a :py:class:`Process` object and the value returned by its ``target``.
        """

        return [(process, process.wait()) for process in self.process_list]

    def start_all(self):
        """
        Call :py:meth:`~Process.start()` on all the child processes of this Context

        Ignores if a Process is already started, unlike :py:meth:`~Process.start()`,
        which throws an ``AssertionError``.
        """

        for process in self.process_list:
            try:
                process.start()
            except AssertionError:
                pass

    def stop_all(self):
        """Call :py:meth:`~Process.stop()` on all the child processes of this Context"""

        for proc in self.process_list:
            proc.stop()

    def ping(self, **kwargs):
        """
        Ping the zproc server.

        :param \*\*kwargs: Keyword arguments that :py:func:`ping` takes, except ``server_address``.
        :return: Same as :py:func:`ping`
        """
        return tools.ping(self.server_address, **kwargs)

    def close(self):
        """
        Close this context and stop all processes associated with it.

        Once closed, you shouldn't use this Context again.
        """

        self.stop_all()

        if self.server_process is not None:
            self.server_process.terminate()

        self._push_sock.close()
        self._pull_sock.close()

        self.state.close()  # The zmq Context will be implicitly closed here.
