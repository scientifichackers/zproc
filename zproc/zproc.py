import atexit
import os
import pickle
import signal
from functools import wraps, update_wrapper
from multiprocessing import Process
from typing import Callable
from uuid import UUID, uuid1

import zmq
from time import sleep

from zproc.util import (
    get_ipc_paths_from_uuid,
    Message,
    serialize_func,
    handle_server_response,
    STATE_INJECTED_METHODS,
    handle_crash,
    signal_to_exception,
    SignalException,
    shutdown_current_process_tree,
    get_kwargs_for_function,
)
from zproc.zproc_server import ZProcServer


def ping(uuid: UUID, **kwargs):
    """
    Ping the ZProc Server

    :param uuid: The ``UUID`` object for identifying the Context.

                 You can use the UUID to reconstruct a ZeroState object, from any Process, at any time.
    :param timeout: (optional) Sets the timeout in seconds. By default it is set to :py:class:`None`.

                    If the value is 0, it will return immediately, with a :py:exc:`TimeoutError`.

                    If the value is :py:class:`None`, it will block until the ZProc Server replies.

                    For all other values, it will wait for a reply,
                    for that amount of time before returning with a :py:exc:`TimeoutError`.
    :param ping_data: (optional) Data to ping the server with.

                      By default, it is set to ``os.urandom(56)`` (56 random bytes of data).
    :return: The ZProc Server's ``pid`` if the ping was successful, else :py:class:`False`
    """

    kwargs.setdefault("timeout", None)
    kwargs.setdefault("ping_data", os.urandom(56))

    ctx = zmq.Context()
    ctx.setsockopt(zmq.LINGER, 0)
    sock = ctx.socket(zmq.DEALER)
    sock.connect(get_ipc_paths_from_uuid(uuid)[0])

    if kwargs["timeout"] is not None:
        sock.setsockopt(zmq.RCVTIMEO, int(kwargs["timeout"] * 1000))

    ping_msg = {
        Message.server_action: ZProcServer.ping.__name__,
        Message.ping_data: kwargs["ping_data"],
    }

    sock.send_pyobj(ping_msg, protocol=pickle.HIGHEST_PROTOCOL)  # send msg

    try:
        response = sock.recv_pyobj()  # wait for reply
    except zmq.error.Again:
        raise TimeoutError("Connection to ZProc Server timed out!")
    else:
        if response.get("ping_data") == kwargs["ping_data"]:
            return response["pid"]
        else:
            return False
    finally:
        sock.close()


def atomic(fn):
    """
    Hack on a normal looking function, to create an atomic operation out of it.

    No Process shall access the state in any way whilst fn is running.
    This helps avoid race-conditions, almost entirely.

    :return: wrapped function
    :rtype: function

    .. code:: python

        import zproc

        @zproc.atomic
        def increment(state):
            return state['count'] += 1

        ctx = zproc.Context()
        ctx.state['count'] = 0

        print(increment(ctx.state))  # 1
    """

    serialized_fn = serialize_func(fn)

    @wraps(fn)
    def wrapper(state, *args, **kwargs):
        return state._req_rep(
            {
                Message.server_action: ZProcServer.run_atomic_function.__name__,
                Message.func: serialized_fn,
                Message.args: args,
                Message.kwargs: kwargs,
            }
        )

    return wrapper


def _state_watcher_mainloop_executor(self, live, timeout):
    def watcher_loop_executor(fn):
        if live:
            sock = self._get_subscribe_sock()
        else:
            sock = self.subscribe_sock

        if timeout is not None:
            sock.setsockopt(zmq.RCVTIMEO, int(timeout * 1000))

        try:
            return fn(sock)
        except zmq.error.Again:
            raise TimeoutError("Timed-out waiting for an update")
        finally:
            if live:
                sock.close()
            elif timeout is not None:
                sock.setsockopt(zmq.RCVTIMEO, -1)

    return watcher_loop_executor


class ZeroState:
    def __init__(self, uuid: UUID):
        """
        Allows accessing state stored on the ZProc Server, through a dict-like API.

        Communicates to the ZProc Server using the ZMQ sockets.

        Don't share a ZeroState object between Process/Threads.
        A ZeroState object is not thread-safe.

        Boasts the following ``dict``-like members, to access the state:

        - Magic  methods:
            __contains__(),  __delitem__(), __eq__(), __getitem__(), __iter__(),
            __len__(), __ne__(), __setitem__()
        - Methods:
            clear(), copy(), fromkeys(), get(), items(),  keys(), pop(), popitem(),
             setdefault(), update(), values()

        :param uuid:
            A ``UUID`` object for identifying the Context.

            You can use the UUID to reconstruct a ZeroState object,
            from any Process, at any time.

        :ivar uuid: Passed on from constructor
        """

        self.uuid = uuid
        self.identity = os.urandom(5)

        self.zmq_ctx = zmq.Context()
        self.zmq_ctx.setsockopt(zmq.LINGER, 0)

        self.server_ipc_path, self.subscribe_ipc_path = get_ipc_paths_from_uuid(
            self.uuid
        )

        self.server_sock = self.zmq_ctx.socket(zmq.DEALER)
        self.server_sock.setsockopt(zmq.IDENTITY, self.identity)
        self.server_sock.connect(self.server_ipc_path)

        self.subscribe_sock = self._get_subscribe_sock()

    def _get_subscribe_sock(self):
        sock = self.zmq_ctx.socket(zmq.SUB)
        sock.connect(self.subscribe_ipc_path)
        sock.setsockopt(zmq.SUBSCRIBE, b"")
        return sock

    def _subscribe(self, sock):
        while True:
            identity, response = sock.recv_multipart()

            # only accept updates from other processes, not this one.
            if identity != self.identity:
                return handle_server_response(pickle.loads(response))

    def _req_rep(self, request):
        self.server_sock.send_pyobj(request, protocol=pickle.HIGHEST_PROTOCOL)
        response = self.server_sock.recv_pyobj()
        return handle_server_response(response)

    def get_when_change(self, *keys, live=True, timeout=None):
        """
        | Block until a change is observed.

        :param keys: Observe for changes in these ``dict`` key(s).

                     If no key is provided, any change in the ``state`` is respected.
        :param live: Whether to get "live" updates. See :ref:`state_watching`.
        :param timeout: Sets the timeout in seconds. By default it is set to :py:class:`None`.

                        If the value is 0, it will return immediately, with a :py:exc:`TimeoutError`,
                        if no update is available.

                        If the value is :py:class:`None`, it will block until an update is available.

                        For all other values, it will wait for and update,
                        for that amount of time before returning with a :py:exc:`TimeoutError`.

        :return: Roughly,

        .. code:: python

            if len(keys) == 1
                return state.get(key)

            if len(keys) > 1
                return [state.get(key) for key in keys]

            if len(keys) == 0
                return state.copy()
        """

        num_keys = len(keys)

        if num_keys == 1:
            key = keys[0]

            @_state_watcher_mainloop_executor(self, live, timeout)
            def mainloop(sock):
                while True:
                    old, new = self._subscribe(sock)
                    if old.get(key) != new.get(key):
                        return new

        elif num_keys:

            @_state_watcher_mainloop_executor(self, live, timeout)
            def mainloop(sock):
                while True:
                    old, new = self._subscribe(sock)
                    for key in keys:
                        if new.get(key) != old.get(key):
                            return [new.get(key) for key in keys]

        else:

            @_state_watcher_mainloop_executor(self, live, timeout)
            def mainloop(sock):
                while True:
                    old, new = self._subscribe(sock)
                    if new != old:
                        return new

    def get_when(self, test_fn, *, live=True, timeout=None):
        """
        | Block until ``test_fn(state: ZeroState)`` returns a True-like value
        |
        | Roughly,

        .. code:: python

            if test_fn(state)
                return state.copy()

        :param test_fn: A ``function``, which is called on each state-change.
        :param live: Whether to get "live" updates. See :ref:`state_watching`.
        :param timeout: Sets the timeout in seconds. By default it is set to :py:class:`None`.

                        If the value is 0, it will return immediately, with a :py:exc:`TimeoutError`,
                        if no update is available.

                        If the value is :py:class:`None`, it will block until an update is available.

                        For all other values, it will wait for and update,
                        for that amount of time before returning with a :py:exc:`TimeoutError`.

        :return: state
        :rtype: ``dict``
        """

        @_state_watcher_mainloop_executor(self, live, timeout)
        def mainloop(sock):
            latest_state = self.copy()
            while True:
                if test_fn(latest_state):
                    return latest_state
                else:
                    latest_state = self._subscribe(sock)[-1]

    def get_when_equal(self, key, value, *, live=True, timeout=None):
        """
        | Block until ``state.get(key) == value``.

        :param key: ``dict`` key
        :param value: ``dict`` value.
        :param live: Whether to get "live" updates. See :ref:`state_watching`.
        :param timeout: Sets the timeout in seconds. By default it is set to :py:class:`None`.

                        If the value is 0, it will return immediately, with a :py:exc:`TimeoutError`,
                        if no update is available.

                        If the value is :py:class:`None`, it will block until an update is available.

                        For all other values, it will wait for and update,
                        for that amount of time before returning with a :py:exc:`TimeoutError`.

        :return: ``state.get(key)``
        """

        @_state_watcher_mainloop_executor(self, live, timeout)
        def mainloop(sock):
            latest_key = self.get(key)
            while True:
                if latest_key == value:
                    return latest_key
                else:
                    latest_key = self._subscribe(sock)[-1].get(key)

    def get_when_not_equal(self, key, value, *, live=True, timeout=None):
        """
        | Block until ``state.get(key) != value``.

        :param key: ``dict`` key.
        :param value: ``dict`` value.
        :param live: Whether to get "live" updates. See :ref:`state_watching`.
        :param timeout: Sets the timeout in seconds. By default it is set to :py:class:`None`.

                        If the value is 0, it will return immediately, with a :py:exc:`TimeoutError`,
                        if no update is available.

                        If the value is :py:class:`None`, it will block until an update is available.

                        For all other values, it will wait for and update,
                        for that amount of time before returning with a :py:exc:`TimeoutError`.

        :return: ``state.get(key)``
        """

        @_state_watcher_mainloop_executor(self, live, timeout)
        def mainloop(sock):
            latest_key = self.get(key)
            while True:
                if latest_key != value:
                    return latest_key
                else:
                    latest_key = self._subscribe(sock)[-1].get(key)

    def go_live(self):
        """
        Clear the events buffer, thus removing past events that were stored.

        See :ref:`state_watching`.
        """

        self.subscribe_sock.close()
        self.subscribe_sock = self._get_subscribe_sock()

    def ping(self, **kwargs):
        """
        Ping the ZProc Server corresponding to this State's Context

        :param kwargs: Optional keyword arguments that :py:func:`ping` takes.
        :return: Same as :py:func:`ping`
        """

        return ping(self.uuid, **kwargs)

    def close(self):
        """
        Close this ZeroState and disconnect with the ZProcServer
        """

        self.server_sock.close()
        self.subscribe_sock.close()
        self.zmq_ctx.destroy()
        self.zmq_ctx.term()

    def copy(self):
        return self._req_rep({Message.server_action: ZProcServer.reply_state.__name__})

    def keys(self):
        return self.copy().keys()

    def items(self):
        return self.copy().items()

    def values(self):
        return self.copy().values()

    def __repr__(self):
        return "<ZeroState state: {} uuid: {}>".format(self.copy(), self.uuid)


def get_injected_method(method_name):
    def injected_method(self, *args, **kwargs):
        return self._req_rep(
            {
                Message.server_action: ZProcServer.call_method_on_state.__name__,
                Message.method_name: method_name,
                Message.args: args,
                Message.kwargs: kwargs,
            }
        )

    return injected_method


for method_name in STATE_INJECTED_METHODS:
    setattr(ZeroState, method_name, get_injected_method(method_name))


def _child_process(proc: "ZeroProcess"):
    state = ZeroState(proc.uuid)

    exceptions = [SignalException]
    for i in proc.kwargs["retry_for"]:
        if type(i) == signal.Signals:
            signal_to_exception(i)
        elif issubclass(i, BaseException):
            exceptions.append(i)
        else:
            raise ValueError(
                '"retry_for" must contain a `signals.Signal` or `Exception`, not `{}`'.format(
                    repr(type(i))
                )
            )
    exceptions = tuple(exceptions)

    target_kwargs = get_kwargs_for_function(
        proc.target, state, proc.kwargs["props"], proc
    )

    tries = 0
    while True:
        try:
            tries += 1
            proc.target(**target_kwargs)
        except exceptions as e:
            if (proc.kwargs["max_retries"] is not None) and (
                tries > proc.kwargs["max_retries"]
            ):
                raise e
            else:
                handle_crash(
                    proc,
                    e,
                    proc.kwargs["retry_delay"],
                    tries,
                    proc.kwargs["max_retries"],
                )

                if "props" in target_kwargs:
                    target_kwargs["props"] = proc.kwargs["retry_props"]
        else:
            break


class ZeroProcess:
    def __init__(self, uuid: UUID, target: Callable, **kwargs):
        """
        Provides a high level wrapper over :py:class:`Process`.

        :param uuid:
            A :py:class:`UUID` object for identifying the Context.

            You may use this to reconstruct a :py:class:`ZeroState` object,
            from any Process, at any time.
        :param target:
            The Callable to be invoked by the start() method.

            It is run inside a :py:class:`Process` with following kwargs:

            ``target(state, props, proc)``

            - state : :py:class:`ZeroState`.
            - props : Passed on from Constructor.
            - proc  : This ZeroProcess instance.

            You can omit these arguments, if you don't need them.
            However their names cannot change.

        :param props:
            (optional) Passed on to the target.

            By default, it is set to :py:class:`None`
        :param start:
            (optional) Automatically call :py:meth:`.start()` on the process.

            By default, it is set to ``True``.
        :param retry_for:
            (optional) Retry whenever a particular Exception / signal is raised.

            By default, it is an empty ``tuple``

            .. code:: python

                import signal

                # retry if a ConnectionError, ValueError or signal.SIGTERM is received.
                ctx.process(
                    my_process,
                    retry_for=(ConnectionError, ValueError, signal.SIGTERM)
                )

            To retry for *any* **Exception**:

            ``retry_for=(Exception,)``

            There is no such feature as retry for *any* **signal**, for now.
        :param retry_delay:
            (optional) The delay in seconds, before retrying.

            By default, it is set to 5 secs
        :param retry_props:
            (optional) Provide different ``props`` to a Process when it's "retrying".

            By default, it is the same as ``props``

            Can be used to control how your application behaves, under retry conditions.
        :param max_retries:
            (optional) Give up after this many attempts.

            By default, it is set to :py:class:`None`.

            A value of :py:class:`None` will result in an *infinite* number of retries.

            After "max_tries", any Exception / Signal will exhibit default behavior.

        :ivar uuid: Passed on from constructor.
        :ivar target: Passed on from constructor.
        :ivar kwargs: Passed on from constructor.
        :ivar child: The :py:class:`Process` object associated with this ZeroProcess.
        """

        assert callable(target), '"target" must be a `Callable`, not `{}`'.format(
            type(target)
        )

        self.uuid = uuid
        self.target = target
        self.kwargs = kwargs

        self.kwargs.setdefault("props", None)
        self.kwargs.setdefault("start", True)
        self.kwargs.setdefault("retry_for", ())
        self.kwargs.setdefault("retry_delay", 5)
        self.kwargs.setdefault("retry_props", self.kwargs["props"])
        self.kwargs.setdefault("max_retries", None)

        self.child = Process(target=_child_process, args=(self,))

        if self.kwargs["start"]:
            self.start()

    def __repr__(self):
        return "<ZeroProcess pid: {} target: {} uuid: {}>".format(
            self.pid, self.target, self.uuid
        )

    def start(self):
        """
        Start this Process

        If the child has already been started once, it will return with an :py:exc:`AssertionError`.

        :return: the process PID
        """

        self.child.start()
        return self.child.pid

    def stop(self):
        """
        Stop this process

        :return: :py:attr:`~exitcode`.
        """

        self.child.terminate()
        return self.child.exitcode

    def wait(self, timoeut=None):
        """
        Wait until the process finishes execution.

        :param timeout: If the value is :py:class:`None`, it will block until the ZProc Server replies.

                        For all other values, it will wait for a reply,
                        for that amount of time before returning with a :py:exc:`TimeoutError`.
        """

        self.child.join(timeout=timoeut)

        if self.child.is_alive():
            raise TimeoutError("Timed-out waiting for process to finish")

    @property
    def is_alive(self):
        """
        Whether the child process is alive.

        | Roughly, a process object is alive;
        | from the moment the start() method returns,
        | until the child process is stopped manually (using stop()) or naturally exits
        """

        return self.child and self.child.is_alive()

    @property
    def pid(self):
        """
        | The process ID.
        | Before the process is started, this will be None.
        """

        if self.child is not None:
            return self.child.pid

    @property
    def exitcode(self):
        """
        | The child’s exit code.
        | This will be None if the process has not yet terminated.
        | A negative value -N indicates that the child was terminated by signal N.
        """

        if self.child is not None:
            return self.child.exitcode


def _zproc_server_process(uuid: UUID):
    server = ZProcServer(uuid)

    def signal_handler(*args):
        server.close()
        shutdown_current_process_tree(*args)

    signal.signal(signal.SIGTERM, signal_handler)
    server.mainloop()


class Context:
    def __init__(self, background: bool = False, uuid: UUID = None, **process_kwargs):
        """
        A Context holds information about the current process.

        It is responsible for the creation and management of Processes.

        Each Context is also associated with a server process,
        which is used internally, to manage the state.

        Don't share a Context object between Process/Threads.
        A Context object is not thread-safe.

        :param background:
            Whether to run Processes under this Context as "background tasks".

            If enabled, it "waits" for all Process to finish their work,
            before your main script can exit.

            Avoids manually calling :py:meth:`~Context.wait_all`
        :param uuid:
            A :py:class:`UUID` object for identifying this Context,
            and the zproc server associated with it.

            By default, it is set to :py:class:`None`

            If uuid is :py:class:`None`,
            then one will be generated,
            and a new server process will be started.

            If a :py:class:`UUID` object is provided,
            then it will connect to an existing server process,
            corresponding to that uuid.

            .. caution::

                If you provide a custom uuid,
                then it's your responsibility to start the server manually,
                using :py:meth:`~Context.start_server`

                Also note that starting multiple server processes
                is bound to cause issues.
        :param \*\*process_kwargs:
            Optional keyword arguments that :py:class:`ZeroProcess` takes.

            If provided, these will be used while creating
            Processes under this Context.

        :ivar background:
            Passed from constructor.
        :ivar kwargs:
            Passed from constructor.
        :ivar uuid:
            A ``UUID`` for identifying the ZProc Server.
        :ivar state:
            A :py:class:`ZeroState` object connecting to the global state.
        :ivar process_list:
            A list of child Process(s) created under this Context.
        :ivar server_process:
            A :py:class:`Process` object for the server, or None.
        """

        self.process_list = []
        self.background = background
        self.process_kwargs = process_kwargs

        if uuid is None:
            self.uuid = uuid1()
            self.start_server()
        else:
            assert isinstance(
                uuid, UUID
            ), '"uuid" must be `None`, or an instance of `uuid.UUID`, not `{}`'.format(
                (type(uuid))
            )
            self.uuid = uuid
            self.server_process = None

        self.state = ZeroState(self.uuid)

        signal.signal(signal.SIGTERM, shutdown_current_process_tree)
        atexit.register(shutdown_current_process_tree)
        if background:
            atexit.register(self.wait_all)

    def start_server(self):
        """
        Start the ZProc Server.

        Automatically called at ``__init__()`` if custom "uuid" wasn't provided
        """

        self.server_process = Process(target=_zproc_server_process, args=(self.uuid,))
        self.server_process.start()

    def process(self, target, **kwargs):
        """
        Produce a child process bound to this context.

        :param target: Passed on to :py:class:`ZeroProcess`'s constructor.
        :param \*\*kwargs: Optional keyword arguments that :py:class:`ZeroProcess` takes.
        """

        _kwargs = self.process_kwargs.copy()
        _kwargs.update(kwargs)
        process = ZeroProcess(self.uuid, target, **_kwargs)
        self.process_list.append(process)
        return process

    def processify(self, **kwargs):
        """
        The decorator version of :py:meth:`~Context.process`

        :param \*\*kwargs: Optional keyword arguments that :py:class:`ZeroProcess` takes.
        :return: A wrapper function.

                The wrapper function will return the :py:class:`ZeroProcess` instance created
        :rtype: function
        """

        def processify_decorator(func):
            return self.process(func, **kwargs)

        return processify_decorator

    def process_factory(self, *targets: Callable, count=1, **kwargs):
        """
        Produce multiple child process(s) bound to this context.

        :param targets: Passed on to :py:class:`ZeroProcess`'s constructor.
        :param count: The number of processes to spawn for each target
        :param \*\*kwargs: Optional keyword arguments that :py:class:`ZeroProcess` takes.
        :return: spawned processes
        :rtype: :py:class:`list` ``[`` :py:class:`ZeroProcess` ``]``
        """

        procs = []
        for target in targets:
            for _ in range(count):
                procs.append(self.process(target, **kwargs))
        self.process_list += procs

        return procs

    def _get_watcher_process_wrapper(self, fn_name, process_kwargs, *args, **kwargs):
        def wrapper(fn):
            @self.processify(**process_kwargs)
            def watcher_process(state, props, proc):
                target_kwargs = get_kwargs_for_function(fn, state, props, proc)

                while True:
                    getattr(state, fn_name)(*args, **kwargs)
                    fn(**target_kwargs)

            update_wrapper(watcher_process.target, fn)
            return watcher_process

        return wrapper

    def call_when_change(self, *keys, live=False, **process_kwargs):
        """
        Decorator version of :py:meth:`~ZeroState.get_when_change()`

        Spawns a new Process that watches the state and calls the wrapped function,
        repeatedly

        :param process_kwargs: Passed on to :py:class:`ZeroProcess` constructor

        All other parameters have same meaning as :py:meth:`~ZeroState.get_when_change()`

        :return: A wrapper function

                The wrapper function will return the :py:class:`ZeroProcess` instance created
        :rtype: function

        .. code:: python

            import zproc

            ctx = zproc.Context()

            @ctx.call_when_change()
            def test(state):
                print(state)
        """

        return self._get_watcher_process_wrapper(
            "get_when_change", process_kwargs, *keys, live=live
        )

    def call_when(self, test_fn, *, live=False, **process_kwargs):
        """
        Decorator version of :py:meth:`~ZeroState.get_when()`

        Spawns a new Process that watches the state and calls the wrapped function,
        repeatedly

        :param process_kwargs: Passed on to :py:class:`ZeroProcess` constructor

        All other parameters have same meaning as :py:meth:`~ZeroState.get_when()`

        :return: A wrapper function

                The wrapper function will return the :py:class:`ZeroProcess` instance created
        :rtype: function

        .. code:: python

            import zproc

            ctx = zproc.Context()

            @ctx.get_state_when(lambda state: state['foo'] == 5)
            def test(state):
                print(state)
        """

        return self._get_watcher_process_wrapper(
            "get_when", process_kwargs, test_fn, live=live
        )

    def call_when_equal(self, key, value, *, live=False, **process_kwargs):
        """
        Decorator version of :py:meth:`~ZeroState.get_when_equal()`

        Spawns a new Process that watches the state and calls the wrapped function,
        repeatedly

        :param process_kwargs: Passed on to :py:class:`ZeroProcess` constructor

        All other parameters have same meaning as :py:meth:`~ZeroState.get_when_equal()`

        :return: A wrapper function

                The wrapper function will return the :py:class:`ZeroProcess` instance created
        :rtype: function

        .. code:: python

            import zproc

            ctx = zproc.Context()

            @ctx.call_when_equal('foo', 5)
            def test(state):
                print(state)
        """

        return self._get_watcher_process_wrapper(
            "get_when_equal", process_kwargs, key, value, live=live
        )

    def call_when_not_equal(self, key, value, *, live=False, **process_kwargs):
        """
        Decorator version of :py:meth:`~ZeroState.get_when_not_equal()`

        Spawns a new Process that watches the state and calls the wrapped function,
        repeatedly

        :param process_kwargs: Passed on to :py:class:`ZeroProcess` constructor

        All other parameters have same meaning as :py:meth:`~ZeroState.get_when_not_equal()`

        :return:
            A wrapper function

            The wrapper function will return the :py:class:`ZeroProcess` instance created
        :rtype: function

        .. code:: python

            import zproc

            ctx = zproc.Context()

            @ctx.call_when_not_equal('foo', 5)
            def test(state):
                print(state)
        """

        return self._get_watcher_process_wrapper(
            "get_when_not_equal", process_kwargs, key, value, live=live
        )

    def wait_all(self, *args, **kwargs):
        """
        Call :py:meth:`~ZeroProcess.wait()` on all the child processes of this Context.
        \*args and \*\*kwargs are passed on to :py:meth:`~ZeroProcess.wait()`
        """

        for proc in self.process_list:
            proc.wait()

    def start_all(self):
        """
        Call :py:meth:`~ZeroProcess.start()` on all the child processes of this Context

        Ignore if process is already started
        """

        for proc in self.process_list:
            try:
                proc.start()
            except AssertionError:
                pass

    def stop_all(self):
        """Call :py:meth:`~ZeroProcess.stop()` on all the child processes of this Context"""

        for proc in self.process_list:
            proc.stop()

    def ping(self, **kwargs):
        """
        Ping the ZProc Server corresponding to this Context

        :param kwargs: Optional keyword arguments that :py:func:`ping` takes.
        :return: Same as :py:func:`ping`
        """

        return ping(self.uuid, **kwargs)

    def close(self):
        """
        Close this context and stop all processes associated with it.

        Once closed, you shouldn't use this Context again.
        """

        self.stop_all()

        if self.server_process is not None:
            self.server_process.terminate()

        self.state.close()
