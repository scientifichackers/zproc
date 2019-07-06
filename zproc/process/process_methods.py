import pprint
import time
from contextlib import suppress
from typing import Callable, Union, Any, List, Mapping, Sequence

from zproc.process.process import Process
from zproc.task.map_plus import map_plus


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

    def start(self):
        """
        Call :py:meth:`~Process.start()` on all the child processes of this Context

        Ignores if a Process is already started, unlike :py:meth:`~Process.start()`,
        which throws an ``AssertionError``.
        """
        with suppress(AssertionError):
            for process in self:
                process.start()

    def stop(self):
        """
        Call :py:meth:`~Process.stop()` on all the Processes in this list.

        Retains the same order as ``Context.process_list``.

        :return:
            A ``list`` containing the exitcodes of the child Processes of this Context.
        """
        return [proc.stop() for proc in self]


class ProcessMethods:
    plist: ProcessList

    def __init__(self, client):
        self.client = client

    @property
    def server_address(self) -> str:
        return self.client.server_address

    @property
    def process_kwargs(self) -> dict:
        return  self.client.process_kwargs

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
        self.plist.append(process)
        return process

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
        if not targets:

            def wrapper(target: Callable):
                return self.spawn(target, count=count, **process_kwargs)

            return wrapper

        if len(targets) * count == 1:
            return self._process(targets[0], **process_kwargs)

        return ProcessList(
            self._process(target, **process_kwargs)
            for _ in range(count)
            for target in targets
        )

    def spawn_map(
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
        return ProcessList(
            map_plus(
                lambda *args, **kwargs: self._process(
                    target, args=args, kwargs=kwargs, **process_kwargs
                ),
                map_iter,
                map_args,
                args,
                map_kwargs,
                kwargs,
            )
        )

    def wait(
        self, timeout: Union[int, float] = None, safe: bool = False
    ) -> List[Union[Any, Exception]]:
        """
        alias for :py:meth:`ProcessList.wait()`
        """
        return self.plist.wait(timeout, safe)

    def start_all(self):
        """
        alias for :py:meth:`ProcessList.start_all()`
        """
        return self.plist.start()

    def stop_all(self):
        """
        alias for :py:meth:`ProcessList.stop_all()`
        """
        return self.plist.stop()
