import atexit
import inspect
import signal
from functools import wraps
from multiprocessing import Process

from zproc.zproc_server import *

signal.signal(signal.SIGTERM, reap_ptree)  # Add handler for the SIGTERM signal


class ZeroState:
    """
    | Allows accessing state stored on the zproc server, through a dict-like API,
    | by communicating over zeromq.

    :param ipc_path: The ipc path of the zproc servers

    | Provides several strategies for synchronization.
    | These allow you to *watch* for changes in your state, without `Busy Waiting`_!
    |
    | **Methods**:
    | Use these when you want *instantaneous* state updates

    .. _Busy Waiting: https://en.wikipedia.org/wiki/Busy_waiting

    - :func:`~zproc.zproc.ZeroState.get_when_equal`
    - :func:`~zproc.zproc.ZeroState.get_when_not_equal`
    - :func:`~zproc.zproc.ZeroState.get_when_change`
    - :func:`~zproc.zproc.ZeroState.get_when`

    | **Decorators**:
    | Use these when you want each and *every* state update
    | Note: They're not currently available, wait for next release..

    - :func:`~zproc.zproc.ZeroState.when_equal`
    - :func:`~zproc.zproc.ZeroState.when_not_equal`
    - :func:`~zproc.zproc.ZeroState.when_change`
    - :func:`~zproc.zproc.ZeroState.when`

    | ``dict`` - like methods:

    - Magic  methods:
        __contains__(),  __delitem__(), __eq__(), __getitem__(), __iter__(), __len__(), __ne__(), __setitem__()
    - Methods:
        clear(), copy(), fromkeys(), get(), items(),  keys(), pop(), popitem(), setdefault(), update(), values()
    """

    def __init__(self, ipc_path):
        self._ctx = zmq.Context()
        self._sock = self._ctx.socket(zmq.DEALER)
        self._sock.connect(ipc_path)

    def _request(self, msg):
        """Send a request (containing msg) to server, and return the reply"""

        self._sock.send_pyobj(msg, protocol=pickle.HIGHEST_PROTOCOL)  # send msg
        data = self._sock.recv_pyobj()  # wait for reply

        # if the reply is a remote Exception, re-raise it!
        if isinstance(data, ZProcServerException):
            data.reraise()
        else:
            return data

    def _request_and_wait(self, msg):
        """Call req_rep(msg), and then PULL from the ipc_path returned in reply"""

        ipc_path = self._request(msg)

        sock = self._ctx.socket(zmq.PULL)
        sock.connect(ipc_path)
        data = sock.recv_pyobj()

        sock.close()

        # if the reply is a remote Exception, re-raise it!
        if isinstance(data, ZProcServerException):
            data.reraise()
        else:
            return data

    def _get_state_rpc_func(self, name):
        def state_rpc_func(*args, **kwargs):
            return self._request({
                Message.method_name: ZProcServer.state_rpc.__name__,
                Message.func_name: name,
                Message.args: args,
                Message.kwargs: kwargs
            })

        return state_rpc_func

    def atomic(self, fn, *args, **kwargs):
        """
        | Run the ``fn`` in an *atomic* way.
        |
        | No other function shall access the state in any way whilst ``fn`` is running.
        | This helps avoid race-conditions, to some degree.

        :param fn: A user-defined function.
        :param args: Passed on to fn
        :param kwargs: Passed on to fn
        :return: Roughly, ``fn(state, *args, **kwargs)``

        .. code:: python

            from zproc import Context

            ctx = Context()
            state = ctx.state

            state['count'] = 0

            def increment(state):
                return state['count'] += 1

            print(state.atomic(increment)) # 1
        """

        return self._request({
            Message.method_name: ZProcServer.rpc.__name__,
            Message.func: serialize_func(fn),
            Message.args: args,
            Message.kwargs: kwargs
        })

    def atomify(self):
        """
        | Hack on a normal looking function to make an atomic operation out of it.
        | Allows making an arbitrary number of operations on sate, atomic.
        |
        | Just a little syntactic sugar over :func:`~zproc.zproc.ZeroState.atomic`

        :return: An atomic decorator, which itself returns - ``wrapped_fn(state, *args, **kwargs)``
        :rtype: function

        .. code:: python

            from zproc import Context

            ctx = Context()
            state = ctx.state

            state['count'] = 0

            @atomify()
            def increment(state):
                return state['count'] += 1

            print(increment()) # 1
        """

        def atomic_decorator(fn):
            @wraps(fn)
            def atomic_wrapper(*args, **kwargs):
                return self.atomic(fn, *args, **kwargs)

            return atomic_wrapper

        return atomic_decorator

    def get_when_equal(self, key, value):
        """
        | Block until ``state.get(key) == value``.

        :param key: ``dict`` key
        :param value: the desired value to wait for
        :return: ``state.get(key)``
        """

        self._request_and_wait({
            Message.method_name: ZProcServer.register_get_when_equal.__name__,
            Message.key: key,
            Message.value: value
        })
        return value

    def get_when_not_equal(self, key, value):
        """
        | Block until ``state.get(key) != value``.

        :param key: ``dict`` key
        :param value: the desired value to wait for
        :return: ``state.get(key)``
        """

        return self._request_and_wait({
            Message.method_name: ZProcServer.register_get_when_not_equal.__name__,
            Message.key: key,
            Message.value: value
        })

    def get_when_change(self, *keys):
        """
        | Block until a change is observed in ``state.get(key)``.

        :param \*keys: ``dict`` key(s)
        :return: Roughly,

        .. code:: python

            if len(keys) == 1:
                return state.get(key)
            elif len(keys):
                return (state.get(key) for key in keys)
            else:
                return state.copy()

        .. note:: | This only watches for changes from the time you call it.
                  | It doesn't imply that you will receive each and every state update,
                  | so don't expect it to do that!
                  | Use  :func:`~zproc.zproc.ZeroState.when_change` for that.
        """

        return self._request_and_wait({
            Message.method_name: ZProcServer.register_get_when_change.__name__,
            Message.keys: keys
        })

    def get_when(self, test_fn, *args, **kwargs):
        """
        | Block until ``test_fn(state, *args, **kwargs)`` returns a True-like value
        |
        | Roughly,

        .. code:: python

            if test_fn(state, *args, **kwargs):
                return state.copy()


        :param test_fn: A function defined at the top level of a module (using ``def``, not ``lambda``). Called on each state-change
        :param args: Passed on to test_fn.
        :param kwargs: Passed on to test_fn.
        :return: state.
        :rtype: ``dict``

        .. caution:: | The ``test_fn`` is serialized using ``pickle``.
                  | If you write a ``test_fn`` that accesses **non-pickle-able** variables,
                  | expect a ``PicklingError`` to be raised.
                  |
                  | Its considered good practice to pass static variables through ``*args``/``*kwargs``,
                  | instead of accessing them directly.

        """

        return self._request_and_wait({
            Message.method_name: ZProcServer.register_get_when.__name__,
            Message.func: serialize_func(test_fn),
            Message.args: args,
            Message.kwargs: kwargs
        })

    def close(self):
        """
        Close this ZeroState by disconnecting with the ZProcServer
        """

        self._sock.close()

    def copy(self):
        return self._request({Message.method_name: ZProcServer.send_state.__name__})

    def keys(self):
        return self.copy().keys()

    def items(self):
        return self.copy().items()

    def values(self):
        return self.copy().values()

    def __repr__(self):
        return '<ZeroState {}>'.format(self.copy())


def _get_remote_method(name):
    def remote_method(self, *args, **kwargs):
        return self._get_state_rpc_func(name)(*args, **kwargs)

    return remote_method


method_injector(ZeroState, STATE_DICT_DYNAMIC_METHODS, _get_remote_method)


def _child_proc(ipc_path, target, props, proc):
    num_args = len(inspect.getfullargspec(target).args)

    if num_args == 0:
        return target()
    elif num_args == 1:
        target(ZeroState(ipc_path))
    elif num_args == 2:
        target(ZeroState(ipc_path), props)
    elif num_args == 3:
        target(ZeroState(ipc_path), props, proc)
    else:
        raise ValueError('target can have a maximum of 3 arguments:  (state, props, proc)')


class ZeroProcess:
    """
    Provides a high level wrapper over multiprocessing.Process.
    """

    def __init__(self, ipc_path, target, props):
        """
        :param ipc_path: the ipc path of the zproc server (associated with the context)
        :param target: | The callable object to be invoked by the start() method.
                       |
                       | It is run inside a ``Process`` with following args:
                       | ``target(state: ZeroState, props, proc: ZeroProcess)``
                       |
                       | The target may or may not have these arguments.
                       | ZProc will adjust according to your function!
                       | The order of these arguments must be preserved.

        :param props: passed on to the target at start(), useful for composing re-usable processes
        :ivar target: Passed from constructor.
        :ivar props: Passed from constructor.
        :ivar background: Passed from constructor.
        """

        assert callable(target), "target must be a callable!"

        self._child_proc = Process(target=_child_proc, args=(ipc_path, target, props, self))

        self.target = target
        self.props = props

    def start(self):
        """
        Start this process

        :return: the process PID
        """

        try:
            if not self.is_alive:
                self._child_proc.start()
        except AssertionError:  # occurs when a Process was started, but not alive
            pass

        return self._child_proc.pid

    def stop(self):
        """Stop this process if it's alive"""

        if self.is_alive:
            self._child_proc.terminate()

    @property
    def is_alive(self):
        """
        | whether the child process is alive.
        |
        | Roughly, a process object is alive;
        | from the moment the start() method returns,
        | until the child process is stopped manually (using stop()) or naturally exits
        """

        return self._child_proc and self._child_proc.is_alive()

    @property
    def pid(self):
        """
        | The process ID.
        | Before the process is started, this will be None.
        """

        if self._child_proc is not None:
            return self._child_proc.pid

    @property
    def exitcode(self):
        """
        | The child’s exit code.
        | This will be None if the process has not yet terminated.
        | A negative value -N indicates that the child was terminated by signal N.
        """

        if self._child_proc is not None:
            return self._child_proc.exitcode


class Context:
    def __init__(self, background=False, keep_alive=False):
        """
        | Create a new Context,
        | by starting the zproc server,
        | and generating a random ipc path to communicate with it.
        |
        | All child process under a Context are instances of ZeroProcess and hence,
        | retain the same API as that of a ZeroProcess instance.
        |
        | You may access the state (ZeroState instance) from the "state" attribute, like so - ``Context.state``
        |
        | A Context object is generally, not thread-safe.

        :param background: | Whether to run processes under this context as background tasks.
                           | Background tasks keep running even when your main (parent) script finishes execution.
        :param keep_alive: Keep the processes under this Context always alive.

        :ivar child_pids: A ``set[int]``, containing pid(s) of running processes under this Context.
        :ivar child_procs: A ``list[ZeroProcess]`` containing processes created under this Context.
        :ivar state: The ``ZeroState`` object associated with this Context.
        :ivar background: Passed from constructor.
        """

        self.child_pids = set()
        self.child_procs = []
        self.background = background

        self._ipc_path = get_random_ipc()
        self._server_proc = Process(target=state_server, args=(self._ipc_path,))
        self._server_proc.start()

        self._keep_alive = keep_alive

        if not background:
            atexit.register(reap_ptree)  # kill all the child procs when main script exits

        self.state = ZeroState(self._ipc_path)

    def process(self, target, props=None, start=True):
        """
        Produce a child process bound to this context.

        :param target: the callable to be invoked by the start() method (inside a child process)
        :param props: passed on to the target at start(), useful for composing re-usable processes
        :param start: Automatically call start() on the process.
        :return: the process created
        :rtype: ZeroProcess
        """

        proc = ZeroProcess(self._ipc_path, target, props)

        self.child_procs.append(proc)

        if start:
            proc.start()

        return proc

    def processify(self, props=None, start=True):
        """
        | Hack on a normal looking function, to create a Process out of it.
        | Meant to be used as a decorator
        |
        | Just a little syntactic sugar over ``proc = Context().process(); proc.start()``

        :param props: passed on to the target at start(), useful for composing re-usable processes
        :param start: Automatically call start() on the process.
        :return: A processify decorator, which itself returns the process (ZeroProcess).
        :rtype: function
        """

        def processify_decorator(func):
            proc = self.process(func, props)

            if start:
                proc.start()

            return proc

        return processify_decorator

    def process_factory(self, *targets: callable, props=None, count=1, start=True):
        """
        Produce multiple child process(s) bound to this context.

        :param targets: callable(s) to be invoked by the start() method (inside a child process)
        :param props: passed on to all the targets at start(), useful for composing re-usable processes
        :param count: The number of child processes to spawn for each target
        :param start: Automatically call start() on the process(s).
        :return: spawned processes
        :rtype: list[ZeroProcess]
        """

        child_procs = []
        for target in targets:
            for _ in range(count):
                child_procs.append(ZeroProcess(self._ipc_path, target, props))
        self.child_procs += child_procs

        if start:
            for proc in child_procs:
                proc.start()

        return child_procs

    def start_all(self):
        """Call start() on all the child processes of this Context"""
        for proc in self.child_procs:
            if not proc.is_alive:
                self.child_pids.add(proc.start())

    def stop_all(self):
        """Call stop() on all the child processes of this Context"""
        for proc in self.child_procs:
            pid = proc.pid
            proc.stop()

            try:
                self.child_pids.remove(pid)
            except KeyError:
                pass

    def close(self):
        """
        | Close this context and stop all processes associated with it.
        | Once closed, you shouldn't use this Context again.
        """

        self.stop_all()

        if self._server_proc.is_alive():
            self._server_proc.terminate()

        self.state.close()
