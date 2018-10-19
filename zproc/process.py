import multiprocessing
import os
import signal
import uuid
from typing import Callable, Union, Sequence, Mapping, Any, Optional

import zmq

from . import util, exceptions
from .processdef import child_process


class Process(util.SecretKeyHolder):
    def __init__(
        self,
        target: Callable,
        server_address: str,
        *,
        stateful: bool = True,
        pass_context: bool = False,
        args: Sequence = None,
        kwargs: Mapping = None,
        retry_for: Sequence[Union[signal.Signals, Exception]] = (),
        retry_delay: Union[int, float] = 5,
        max_retries: Optional[bool] = None,
        retry_args: Optional[tuple] = None,
        retry_kwargs: Optional[dict] = None,
        start: bool = True,
        backend: Callable = multiprocessing.Process,
        namespace: str = "default",
        secret_key: Optional[str] = None
    ) -> None:
        """
        Provides a higher level interface to ``multiprocessing.Process``.

        Please don't share a Process object between Processes / Threads.
        A Process object is not thread-safe.

        :param server_address:
            The address of zproc server.

            If you are using a :py:class:`Context`, then this is automatically provided.

            Please read :ref:`server-address-spec` for a detailed explanation.

        :param target:
            The Callable to be invoked inside a new process.

            *The ``target`` is invoked with the following signature:*

            ``target(state, *args, **kwargs)``

            *Where:*

            - ``state`` is a :py:class:`State` instance.
            - ``args`` and ``kwargs`` are passed from the constructor.

        :param pass_context:
            Weather to pass a :py:class:`Context` to this process.

            If this is set to ``True``,
            then the first argument to ``target`` will be a :py:class:`Context` object
            in-place of the default - :py:class:`State`.

            In other words, The ``target`` is invoked with the following signature:

            ``target(ctx, *args, **kwargs)``

            Where:

            - ``ctx`` is a :py:class:`Context` object.
            - ``args`` and ``kwargs`` are passed from the constructor.

            .. note::
                The :py:class:`Context` object provided here,
                will be different than the one used to create this process.

                The new :py:class:`Context` object can be used to create nested processes
                that share the same state.

        :param stateful:
            Weather this process needs to access the state.

            If this is set to ``False``,
            then the ``state`` argument won't be provided to the ``target``.

            In other words, The ``target`` is invoked with the following signature:

            ``target(*args, **kwargs)``

            Where:

            - ``args`` and ``kwargs`` are passed from the constructor.

            Has no effect if ``pass_context`` is set to ``True``.

        :param start:
            Automatically call :py:meth:`.start()` on the process.

        :param retry_for:
            Retry only when one of these ``Exception``/``signal.Signals`` is raised.

            .. code-block:: python
                :caption: Example

                import signal

                # retry if a ConnectionError, ValueError or signal.SIGTERM is received.
                ctx.process(
                    my_process,
                    retry_for=(ConnectionError, ValueError, signal.SIGTERM)
                )

            To retry for *any* Exception - ``retry_for=(Exception, )``

            The items of this sequence MUST be a subclass of ``BaseException`` or of type ``signal.Signals``.

        :param retry_delay:
            The delay in seconds, before retrying.

        :param max_retries:
            Give up after this many attempts.

            A value of ``None`` will result in an *infinite* number of retries.

            After "max_tries", any Exception / Signal will exhibit default behavior.

        :param args:
            The argument tuple for ``target``.

            By default, it is an empty ``tuple``.

        :param kwargs:
            A dictionary of keyword arguments for ``target``.

            By default, it is an empty ``dict``.

        :param retry_args:
            Used in place of ``args`` when retrying.

            If set to ``None``, then it has no effect.

        :param retry_kwargs:
            Used in place of ``kwargs`` when retrying.

            If set to ``None``, then it has no effect.

        :param backend:
            The backend to use for launching the process(s).

            For example, you may use ``threading.Thread`` as the backend.

            .. warning::

                Not guaranteed to work well with anything other than ``multiprocessing.Process``.

        :ivar child:
            A ``multiprocessing.Process`` instance for the child process.
        :ivar server_address:
            Passed on from the constructor.
        :ivar target:
            Passed on from the constructor.
        :ivar namespace:
            Passed on from the constructor. This is read-only.
        """
        assert callable(target), '"target" must be a `Callable`, not `{}`'.format(
            type(target)
        )

        super().__init__(secret_key)

        self.server_address = server_address
        self.namespace = namespace
        self.target = target

        self._zmq_ctx = util.create_zmq_ctx()
        self._result_sock = self._zmq_ctx.socket(zmq.PULL)
        # The result socket is meant to be used only after the process completes (after join()).
        # That implies -- we shouldn't need to wait for the result message.
        self._result_sock.setsockopt(zmq.RCVTIMEO, 0)

        result_address = util.bind_to_random_address(self._result_sock)

        self.child = backend(
            target=child_process,
            args=[
                self.server_address,
                self.target,
                self.__repr__(),
                self.namespace,
                secret_key,
                stateful,
                pass_context,
                args,
                kwargs,
                retry_for,
                retry_delay,
                max_retries,
                retry_args,
                retry_kwargs,
                result_address,
            ],
        )

        if start:
            self.child.start()

    def __repr__(self):
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

        return "<%s pid: %r target: %r ppid: %r is_alive: %r exitcode: %r>" % (
            Process.__qualname__,
            pid,
            self.target.__module__ + "." + self.target.__qualname__,
            os.getpid(),
            is_alive,
            exitcode,
        )

    def start(self):
        """
        Start this Process

        If the child has already been started once, it will return with an :py:exc:`AssertionError`.

        :return: the process PID
        """
        self.child.start()
        return self.pid

    def stop(self):
        """
        Stop this process.

        Once closed, it should not, and cannot be used again.

        :return: :py:attr:`~exitcode`.
        """
        self.child.terminate()

        self._result_sock.close()
        util.close_zmq_ctx(self._zmq_ctx)

        return self.child.exitcode

    def wait(self, timeout: Optional[Union[int, float]] = None):
        """
        Wait until this process finishes execution,
        then return the value returned by the ``target``.

        :param timeout:
            The timeout in seconds.

            If the value is ``None``, it will block until the zproc server replies.

            For all other values, it will wait for a reply,
            for that amount of time before returning with a ``TimeoutError``.

        :return:
            The value returned by the ``target`` function.

        If the child finishes with a non-zero exitcode,
        or there is some error in retrieving the value returned by the ``target``,
        a :py:exc:`.ProcessWaitError` is raised.
        """
        # try to fetch the cached result.
        try:
            return self._return_value
        except AttributeError:
            self.child.join(timeout)

            if self.is_alive:
                raise TimeoutError(
                    "Timed-out while waiting for Process to return. -- %s" % repr(self)
                )

            exitcode = self.exitcode
            if exitcode != 0:
                raise exceptions.ProcessWaitError(
                    "Process returned with a non-zero exitcode. -- %s" % repr(self),
                    exitcode,
                    self,
                )

            try:
                self._return_value = util.recv(
                    self._result_sock, self._serializer
                )  # type: Any
            except zmq.error.Again:
                raise exceptions.ProcessWaitError(
                    "The Process died before sending its return value. "
                    "It probably crashed, got killed, or exited without warning.",
                    exitcode,
                )

            self._result_sock.close()
            self._zmq_ctx.destroy()
            self._zmq_ctx.term()

            return self._return_value

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
