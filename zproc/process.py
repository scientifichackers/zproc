import multiprocessing
import os
import signal
import time
import uuid
from typing import Callable, Union, Sequence

import zmq

from zproc import processdef, util


class Process:
    def __init__(
        self,
        server_address: tuple,
        target: Callable,
        *,
        args: tuple = None,
        kwargs: dict = None,
        start: bool = True,
        stateful: bool = True,
        retry_for: Sequence[Union[signal.Signals, Exception]] = (),
        retry_delay: Union[int, float] = 5,
        max_retries: Union[None, bool] = None,
        retry_args: Union[None, tuple] = None,
        retry_kwargs: Union[None, dict] = None,
        backend: Callable = multiprocessing.Process
    ):
        """
        Provides a higher level interface to ``multiprocessing.Process``.

        :param server_address:
            The address of zproc server.
            (See :ref:`zproc-server-address-spec`)

            If you are using a :py:class:`Context`, then this is automatically provided.

        :param target:
            The Callable to be invoked inside a new process.

            *The ``target`` is invoked with the following signature:*

            ``target(state, *args, **kwargs)``

            *Where:*

            - ``state`` is a :py:class:`State` instance.
            - ``args`` and ``kwargs`` are passed from the :py:class:`Process` constructor.

        :param stateful:
            Weather this process needs to access the state.

            If this is set to ``False``,
            then the ``state`` argument won't be provided to the ``target``.

            So, The ``target`` is invoked with the following signature:

            ``target(*args, **kwargs)``

            Where:

            - ``args`` and ``kwargs`` are passed from the :py:class:`Process` constructor.

        :param args:
            The argument tuple for ``target``.

            By default, it is an empty ``tuple``.

        :param kwargs:
            A dictionary of keyword arguments for ``target``.

            By default, it is an empty ``dict``.

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

        :ivar server_address: Passed on from constructor.
        :ivar target: Passed on from constructor.
        :ivar child: A ``multiprocessing.Process`` instance for the child process.
        """

        assert callable(target), '"target" must be a `Callable`, not `{}`'.format(
            type(target)
        )

        self.server_address = server_address
        self.target = target

        self._zmq_ctx = zmq.Context()
        self._zmq_ctx.setsockopt(zmq.LINGER, 0)
        self._result_sock = self._zmq_ctx.socket(zmq.PULL)

        if os.system == "posix":
            result_address = "ipc://" + str(util.ipc_base_dir) + str(uuid.uuid1())
            self._result_sock.bind(result_address)
        else:
            port = self._result_sock.bind_to_random_port("tcp://*")
            result_address = "tcp://127.0.0.1:{}".format(port)

        self.child = backend(
            target=processdef.child_process,
            args=(
                server_address,
                target,
                self.__repr__(),
                stateful,
                args,
                kwargs,
                retry_for,
                retry_delay,
                max_retries,
                retry_args,
                retry_kwargs,
                result_address,
            ),
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

        return "<{} pid: {} ppid: {} is_alive: {} exitcode: {} target: {}>".format(
            Process.__qualname__,
            pid,
            os.getpid(),
            repr(is_alive),
            repr(exitcode),
            repr(self.target.__qualname__),
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

    def wait(self, timeout: Union[None, int, float] = None):
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
        """

        start_time = time.time()
        if timeout is not None:
            self._result_sock.setsockopt(zmq.RCVTIMEO, int(timeout * 1000))
        else:
            self._result_sock.setsockopt(zmq.RCVTIMEO, -1)

        try:
            return self._return_value
        except AttributeError:
            try:
                self._return_value = self._result_sock.recv_pyobj()
            except zmq.error.Again:
                raise TimeoutError("Timed-out while waiting for Process to finish.")
            else:
                self._result_sock.close()
                self._zmq_ctx.destroy()
                self._zmq_ctx.term()

                elapsed = time.time() - start_time
                if timeout is None:
                    self.child.join()
                elif elapsed < timeout:
                    self.child.join(timeout - elapsed)

                if self.is_alive:
                    raise TimeoutError("Timed-out while waiting for Process to finish.")

                return self._return_value

    @property
    def is_alive(self):
        """
        Whether the child process is alive.

        Roughly, a process object is alive;
        from the moment the start() method returns,
        until the child process is stopped manually (using stop()) or naturally exits
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
        A negative value -N indicates that the child was terminated by signal N.
        """

        return self.child.exitcode
