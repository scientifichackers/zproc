import multiprocessing
from typing import List, Mapping, Sequence, Any, Callable

import zmq

from zproc import util, serializer
from zproc.consts import DEFAULT_NAMESPACE, EMPTY_MULTIPART
from zproc.server.tools import ping
from .result import SequenceTaskResult, SimpleTaskResult
from .worker import worker_process


class Swarm:
    def __init__(self, server_address: str, *, namespace: str = DEFAULT_NAMESPACE):
        #: Passed on from the constructor.
        self.server_address = server_address
        #: Passed on from the constructor.
        self.namespace = namespace
        #: A ``list`` of :py:class:`multiprocessing.Process` objects for the wokers spawned.
        self.worker_list = []  # type: List[multiprocessing.Process]

        self._zmq_ctx = util.create_zmq_ctx()
        self._server_meta = util.get_server_meta(self._zmq_ctx, server_address)
        self._task_push = self._zmq_ctx.socket(zmq.PUSH)
        self._task_push.connect(self._server_meta.task_proxy_in)

    def ping(self, **kwargs):
        return ping(self.server_address, **kwargs)

    @property
    def count(self) -> int:
        """
        Returns the number of workers currently alive.

        This property can be set manully,
        in order to change the number of workers that *should* be alive.
        """
        return sum(1 for w in self.worker_list if w.is_alive())

    @count.setter
    def count(self, value: int):
        value -= self.count
        if value > 0:
            for _ in range(value):
                recv_conn, send_conn = multiprocessing.Pipe()

                process = multiprocessing.Process(
                    target=worker_process, args=[self.server_address, send_conn]
                )
                process.start()

                with recv_conn:
                    rep = recv_conn.recv_bytes()
                if rep:
                    serializer.loads(rep)

                self.worker_list.append(process)
        elif value < 0:
            # Notify remaining workers to finish up, and close shop.
            for _ in range(-value):
                self._task_push.send_multipart(EMPTY_MULTIPART)

    def start(self, count: int = None):
        if count is None:
            self.count = multiprocessing.cpu_count()
        else:
            self.count = count

    def stop(self, force: bool = False):
        if force:
            for p in self.worker_list:
                p.terminate()
        else:
            self.count = 0

    def run(
        self,
        target: Callable = None,
        args: Sequence = None,
        kwargs: Mapping = None,
        *,
        pass_state: bool = False,
        lazy: bool = False,
    ):
        if target is None:

            def wrapper(*a, **k):
                return self.run(target, a, k, pass_state=pass_state, lazy=lazy)

            return wrapper

        task_id = util.generate_task_id()
        if args is None:
            args = ()
        if kwargs is None:
            kwargs = {}
        params = (None, None, args, None, kwargs)
        task = (target, params, pass_state, self.namespace)

        self._task_push.send_multipart(
            [util.encode_chunk_id(task_id, -1), serializer.dumps(task)]
        )

        res = SimpleTaskResult(self.server_address, task_id)
        if lazy:
            return res
        return res.value

    def map_lazy(
        self,
        target: Callable,
        map_iter: Sequence[Any] = None,
        *,
        map_args: Sequence[Sequence[Any]] = None,
        args: Sequence = None,
        map_kwargs: Sequence[Mapping[str, Any]] = None,
        kwargs: Mapping = None,
        pass_state: bool = False,
        num_chunks: int = None,
    ) -> SequenceTaskResult:
        r"""
        Functional equivalent of ``map()`` in-built function,
        but executed in a parallel fashion.

        Distributes the iterables,
        provided in the ``map_*`` arguments to ``num_chunks`` no of worker nodes.

        The idea is to:
            1. Split the the iterables provided in the ``map_*`` arguments into ``num_chunks`` no of equally sized chunks.
            2. Send these chunks to ``num_chunks`` number of worker nodes.
            3. Wait for all these worker nodes to finish their task(s).
            4. Combine the acquired results in the same sequence as provided in the ``map_*`` arguments.
            5. Return the combined results.

            *Steps 3-5 can be done lazily, on the fly with the help of an iterator*

        :param target:
            The ``Callable`` to be invoked inside a :py:class:`Process`.

            *It is invoked with the following signature:*

                ``target(map_iter[i], *map_args[i], *args, **map_kwargs[i], **kwargs)``

            *Where:*

                - ``i`` is the index of n\ :sup:`th` element of the Iterable(s) provided in the ``map_*`` arguments.

                - ``args`` and ``kwargs`` are passed from the ``**process_kwargs``.

            The ``pass_state`` Keyword Argument of allows you to include the ``state`` arg.
        :param map_iter:
            A sequence whose elements are supplied as the *first* positional argument to the ``target``.
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
        :param pass_state:
            Weather this process needs to access the state.

            If this is set to ``False``,
            then the ``state`` argument won't be provided to the ``target``.

            If this is set to ``True``,
            then a :py:class:`State` object is provided as the first Argument to the ``target``.

            Unlike :py:class:`Process` it is set to ``False`` by default.
            (To retain a similar API to in-built ``map()``)
        :param num_chunks:
            The number of worker nodes to use.

            By default, it is set to ``multiprocessing.cpu_count()``
            (The number of CPU cores on your system)
        :param lazy:
            Wheteher to return immediately put
        :return:
            The result is quite similar to ``map()`` in-built function.

            It returns a :py:class:`Iterable` which contatins,
            the return values of the ``target`` function,
            when applied to every item of the Iterables provided in the ``map_*`` arguments.

            The actual "processing" starts as soon as you call this function.

            The returned :py:class:`Iterable` only fetches the results from the worker processes.

        .. note::
            - If ``len(map_iter) != len(maps_args) != len(map_kwargs)``,
              then the results will be cut-off at the shortest Sequence.

        See :ref:`worker_map` for Examples.
        """
        if num_chunks is None:
            num_chunks = multiprocessing.cpu_count()

        lengths = [len(i) for i in (map_iter, map_args, map_kwargs) if i is not None]
        assert (
            lengths
        ), "At least one of `map_iter`, `map_args`, or `map_kwargs` must be provided as a non-empty Sequence."

        length = min(lengths)

        assert (
            length > num_chunks
        ), "`length`(%d) cannot be less than `num_chunks`(%d)" % (length, num_chunks)

        chunk_length, extra = divmod(length, num_chunks)
        if extra:
            chunk_length += 1
        task_id = util.generate_task_id((chunk_length, length, num_chunks))

        iter_chunks = util.make_chunks(map_iter, chunk_length, num_chunks)
        args_chunks = util.make_chunks(map_args, chunk_length, num_chunks)
        kwargs_chunks = util.make_chunks(map_kwargs, chunk_length, num_chunks)

        target_bytes = serializer.dumps_fn(target)

        for index in range(num_chunks):
            params = (
                iter_chunks[index],
                args_chunks[index],
                args,
                kwargs_chunks[index],
                kwargs,
            )
            task = (params, pass_state, self.namespace)

            self._task_push.send_multipart(
                [
                    util.encode_chunk_id(task_id, index),
                    target_bytes,
                    serializer.dumps(task),
                ]
            )

        return SequenceTaskResult(self.server_address, task_id)

    def map(self, *args, **kwargs) -> list:
        return self.map_lazy(*args, **kwargs).as_list

    def __del__(self):
        try:
            self._task_push.close()
            util.close_zmq_ctx(self._zmq_ctx)
        except Exception:
            pass
