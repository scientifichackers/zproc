import multiprocessing
import os
import signal
import time
from typing import Callable, Union, Sequence, Mapping, Optional, Iterable, Type

import zmq

from zproc import util, exceptions, serializer
from zproc.child import ChildProcess
from zproc.consts import DEFAULT_NAMESPACE


class Process:
    _result = None  # type:None
    _has_returned = False

    def __init__(
        self,
        server_address: str,
        target: Callable,
        *,
        args: Sequence = None,
        kwargs: Mapping = None,
        start: bool = True,
        pass_context: bool = True,
        retry_for: Iterable[Union[signal.Signals, Type[BaseException]]] = (),
        retry_delay: Union[int, float] = 5,
        max_retries: Optional[int] = 0,
        retry_args: tuple = None,
        retry_kwargs: dict = None,
        backend: Callable = multiprocessing.Process,
        namespace: str = DEFAULT_NAMESPACE,
    ) -> None:
        """
        Provides a higher level interface to :py:class:`multiprocessing.Process`.

        Please don't share a Process object between Processes / Threads.
        A Process object is not thread-safe.

        :param server_address:
            .. include:: /api/snippets/server_address.rst

            If you are using a :py:class:`Context`, then this is automatically provided.
        :param target:
            The Callable to be invoked inside a new process.

            *The* ``target`` *is invoked with the following signature:*

            .. code-block:: python

                target(state, *args, **kwargs)

            *Where:*

            - ``state`` is a :py:class:`State` instance.
            - ``args`` and ``kwargs`` are passed from the constructor.
        :param args:
            The argument tuple for ``target``.

            By default, it is an empty ``tuple``.
        :param kwargs:
            A dictionary of keyword arguments for ``target``.

            By default, it is an empty ``dict``.
        :param pass_state:
            Weather this process needs to access the state.

            If this is set to ``False``,
            then the ``state`` argument won't be provided to the ``target``.

            *If this is enabled, the* ``target`` *is invoked with the following signature:*

            .. code-block:: python

                target(*args, **kwargs)

            *Where:*

            - ``args`` and ``kwargs`` are passed from the constructor.

            Has no effect if ``pass_context`` is set to ``True``.
        :param pass_context:
            Weather to pass a :py:class:`Context` to this process.

            If this is set to ``True``,
            then the first argument to ``target`` will be a new :py:class:`Context` object

            This will take the place of the default - :py:class:`State`.

            *If this is enabled, the* ``target`` *is invoked with the following signature*:

            .. code-block:: python

                target(ctx, *args, **kwargs)

            *Where:*

            - ``ctx`` is a :py:class:`Context` object.
            - ``args`` and ``kwargs`` are passed from the constructor.

            .. note::
                The :py:class:`Context` object provided here,
                will be a new object, NOT the one used to create this process.

                Such that,
                this new :py:class:`Context` can be used to spwan new processes,
                that share the same state.

                **This is the recommended way to create nested processes
                that share the same state.**


        :param start:
            Automatically call :py:meth:`.start()` on the process.
        :param retry_for:
            Retry only when one of these ``Exception``/``signal.Signals`` is raised.

            .. code-block:: python
                :caption: Example

                import signal

                # retry if a ConnectionError, ValueError or signal.SIGTERM is received.
                ctx.spawn(
                    my_process,
                    retry_for=(ConnectionError, ValueError, signal.SIGTERM)
                )

            To retry for *any* Exception - ``retry_for=(Exception, )``

            The items of this sequence MUST be a subclass of ``BaseException`` or of type ``signal.Signals``.
        :param retry_delay:
            The delay in seconds, before retrying.
        :param max_retries:
            Maximum number of retries before giving up.
            If set to ``None``, the Process will never stop retrying.

            After "max_tries", any Exception / Signal will exhibit default behavior.
        :param retry_args:
            Used in place of ``args`` when retrying.

            If set to ``None``, then it has no effect.
        :param retry_kwargs:
            Used in place of ``kwargs`` when retrying.

            If set to ``None``, then it has no effect.
        :param backend:
            .. include:: /api/snippets/backend.rst
        """
        #: Passed on from the constructor.
        self.server_address = server_address
        #: Passed on from the constructor.
        self.namespace = namespace
        #: Passed on from the constructor.
        self.target = target

        if args is None:
            args = ()
        if kwargs is None:
            kwargs = {}

        self._zmq_ctx = util.create_zmq_ctx()

        self._result_sock = self._zmq_ctx.socket(zmq.PAIR)
        # The result socket is meant to be used only after the process completes (after `join()`).
        # That implies -- we shouldn't need to wait for the result message.
        self._result_sock.setsockopt(zmq.RCVTIMEO, 0)
        result_address = util.bind_to_random_address(self._result_sock)
        #: The :py:class:`multiprocessing.Process` instance for the child process.
        self.child = backend(
            target=ChildProcess,
            kwargs=dict(
                target=self.target,
                server_address=self.server_address,
                namespace=self.namespace,
                pass_context=pass_context,
                target_args=args,
                target_kwargs=kwargs,
                retry_for=retry_for,
                retry_delay=retry_delay,
                max_retries=max_retries,
                retry_args=retry_args,
                retry_kwargs=retry_kwargs,
                result_address=result_address,
            ),
        )
        if start:
            self.child.start()

    def __str__(self):
        try:
            pid = self.pid
        except AttributeError:
            pid = None
        try:
            exitcode = self.exitcode
        except AttributeError:
            exitcode = None
        try:
            is_alive = self.is_alive
        except AttributeError:
            is_alive = False

        return "%s - pid: %r target: %s ppid: %r is_alive: %r exitcode: %r" % (
            Process.__qualname__,
            pid,
            util.callable_repr(self.target),
            os.getpid(),
            is_alive,
            exitcode,
        )

    def __repr__(self):
        return util.enclose_in_brackets(self.__str__())

    def start(self):
        """
        Start this Process

        If the child has already been started once, it will return with an :py:exc:`AssertionError`.

        :return: the process PID
        """
        self.child.start()
        return self.pid

    def _cleanup(self):
        self._result_sock.close()
        util.close_zmq_ctx(self._zmq_ctx)

    def stop(self):
        """
        Stop this process.

        Once closed, it should not, and cannot be used again.

        :return: :py:attr:`~exitcode`.
        """
        self.child.terminate()
        self._cleanup()
        return self.child.exitcode

    def wait(self, timeout: Union[int, float] = None):
        """
        Wait until this process finishes execution,
        then return the value returned by the ``target``.

        This method raises a a :py:exc:`.ProcessWaitError`,
        if the child Process exits with a non-zero exitcode,
        or if something goes wrong while communicating with the child.

        :param timeout:
            The timeout in seconds.

            If the value is ``None``, it will block until the zproc server replies.

            For all other values, it will wait for a reply,
            for that amount of time before returning with a :py:class:`TimeoutError`.

        :return:
            The value returned by the ``target`` function.
        """
        # try to fetch the cached result.
        if self._has_returned:
            return self._result

        if timeout is not None:
            target = time.time() + timeout
            while time.time() < target:
                self.child.join(timeout)

            if self.is_alive:
                raise TimeoutError(
                    f"Timed-out while waiting for Process to return. -- {self!r}"
                )
        else:
            self.child.join()
            if self.is_alive:
                return None
        exitcode = self.exitcode
        if exitcode != 0:
            raise exceptions.ProcessWaitError(
                f"Process finished with a non-zero exitcode ({exitcode}). -- {self!r}",
                exitcode,
                self,
            )
        try:
            self._result = serializer.loads(self._result_sock.recv())
        except zmq.error.Again:
            raise exceptions.ProcessWaitError(
                "The Process died before sending its return value. "
                "It probably crashed, got killed, or exited without warning.",
                exitcode,
            )

        self._has_returned = True
        self._cleanup()
        return self._result

    @property
    def is_alive(self):
        """
        Whether the child process is alive.

        Roughly, a process object is alive;
        from the moment the :py:meth:`start` method returns,
        until the child process is stopped manually (using :py:meth:`stop`) or naturally exits
        """
        return self.child.is_alive()

    @property
    def pid(self):
        """
        The process ID.

        Before the process is started, this will be None.
        """
        return self.child.pid

    @property
    def exitcode(self):
        """
        The child’s exit code.

        This will be None if the process has not yet terminated.
        A negative value ``-N`` indicates that the child was terminated by signal ``N``.
        """
        return self.child.exitcode
