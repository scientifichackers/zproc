import atexit
import inspect
import os
import pickle
import signal
from functools import partial
from multiprocessing import Process, current_process

import zmq

from .zproc_server import Message, state_server, get_random_ipc, ZProcServerException, ZProcServer

# from time import sleep

inception_msg = """
Looks like you haven't had the usual lecture about doing multiprocessing. 
Let me take some time to explain what you just did.

You launched a child process, inside a child process. 
Let that sink in.
What you just did is nothing short of the movie "Inception"

I'm not responsible for what comes after. 
Don't come crying.

Here are the basic rules for multi-processing, as I understand them.

1. Synchronization primitives (locks) are extremely hard to use correctly, so just don't use them at all.
2. The existence of global mutable state indicates a flaw in the application’s design, 
   which you should review and change.
3. Don't launch processes inside processes.
4. Don't launch processes inside processes.
5. Don't launch processes inside processes.
...

Hope we all learned something today.
"""
DICT_ATTRS = (
    '__contains__',
    '__delitem__',
    '__eq__',
    '__format__',
    '__getitem__',
    '__iter__',
    '__len__',
    '__ne__',
    '__setitem__',
    'clear',
    'copy',
    'fromkeys',
    'get',
    'items',
    'keys',
    'pop',
    'popitem',
    'setdefault',
    'update',
    'values'
)


class ZeroStateLock:
    def __init__(self, state):
        self.state = state
        self.sock, self.ipc_path, self.locked_state, = None, None, None

    def __enter__(self):
        self.ipc_path, self.locked_state = self.state._req_rep({Message.action: ZProcServer.lock_state.__name__})
        return self.locked_state

    def __exit__(self, exc_type, exc_val, exc_tb):
        ctx = zmq.Context()
        self.sock = ctx.socket(zmq.PUSH)
        self.sock.connect(self.ipc_path)
        self.sock.send_pyobj(self.locked_state, protocol=pickle.HIGHEST_PROTOCOL)
        self.sock.close()


class ZeroState:
    """
    | Allows accessing state stored on the zproc server,
    | through a dict-like interface,
    | by communicating the state over zeromq.

    :param ipc_path: The ipc path of the zproc servers

    | It provides the following methods, as a substitute for traditional synchronization primitives.

    - get_when_equal()
    - get_when_not_equal()

    - get_when_change()
    - get_state_when_change()

    - get_state_when()


    | These methods are the reason why ZProc is better than traditional multi-processing.
    | They allow you to watch for changes in your state, without having to worry about irrelevant details.

    .. note:: | While the zproc server is very efficient at handling stuff,
              | You should use this feature wisely.
              | Adding a lot of synchronization handlers will ultimately slow down your application.
              |
              | If you're interested in the mathematics of it,
              | Each new synchronization handler increases complexity, linearly.
              | The frequency at which you update the state also affects the complexity linearly.
              |
              | Keep these in mind when developing performance-critical applications.

    | It also provides the following methods, to make the state feel like a dict

    - __contains__()
    - __delitem__()
    - __eq__()
    - __format__()
    - __getitem__()
    - __iter__()
    - __len__()
    - __ne__()
    - __setitem__()
    - clear()
    - copy()
    - fromkeys()
    - get()
    - items()
    - keys()
    - pop()
    - popitem()
    - setdefault()
    - update()
    - values()

    """

    def __init__(self, ipc_path):
        self._ctx = zmq.Context()
        self._sock = self._ctx.socket(zmq.DEALER)
        self._sock.connect(ipc_path)
        # sleep(1)

        super().__init__()

    def _req_rep(self, msg):
        """Send a request (containing msg) to server and return the reply"""
        self._sock.send_pyobj(msg, protocol=pickle.HIGHEST_PROTOCOL)
        data = self._sock.recv_pyobj()

        if isinstance(data, ZProcServerException):
            data.reraise()
        else:
            return data

    def _req_rep_pull(self, msg):
        """Call req_rep(msg) and then pull from the ipc_path returned in reply"""
        ipc_path = self._req_rep(msg)

        sock = self._ctx.socket(zmq.PULL)
        sock.connect(ipc_path)
        data = sock.recv_pyobj()

        sock.close()

        if isinstance(data, ZProcServerException):
            data.reraise()
        else:
            return data

    def lock_state(self):
        """
        :return: ZeroStateLock

        | Sometimes, you want to lock the state to a certain Process.
        |
        | More specifically, you don't want any other process to access the state, for a little while.
        | More abstractly, this feature allows you to do a bunch of operations on the state as one, atomic operation.
        |
        | Meant to be used as a context manager only.


        .. code-block:: python
            :caption: Example

            with state.lock_state() as locked_state:
                # Do something with the locked_state (a dict)
                # BTW, other processes may NOT access the state here !

            # other processes are free to access the state now

        | The locked_state is automatically synchronized with global state when the context manager exits.
        """
        return ZeroStateLock(self)

    def get_when_not_equal(self, key, value):
        """
        | Block until :code:`state.get(key) != value`.

        :param key: the key in state dict
        :param value: the desired value to wait for
        :return: :code:`state.get(key)`

        .. code-block:: python
            :caption: Example

            >>> state['foo'] = 'bar'

            >>> # blocks until foo is set to anything other than 'foobar'
            >>> state.get_when_not_equal('foo', 'foobar')
            'bar'
        """
        return self._req_rep_pull(
            {Message.action: ZProcServer.add_val_change_handler.__name__, Message.key: key, Message.value: value})

    def get_when_equal(self, key, value):
        """
        | Block until :code:`state.get(key) == value`.

        :param key: the key in state dict
        :param value: the desired value to wait for
        :return: :code:`state.get(key)`
        """
        if self._req_rep_pull(
                {Message.action: ZProcServer.add_equals_handler.__name__, Message.key: key, Message.value: value}):
            return value

    def get_when_change(self, key):
        """
        | Block until a state change is observed in provided key,
        | then return :code:`state.get(key)`.

        :param key: the key (of state dict) to watch for changes
        :return: :code:`state.get(key)`

        .. code-block:: python
            :caption: Example

            >>> state['foo'] = 'bar'

            >>> # blocks until foo is set to anything other than 'bar'
            >>> state.get_when_change('foo') # will block forever...
        """
        return self._req_rep_pull({Message.action: ZProcServer.add_val_change_handler.__name__, Message.key: key})

    def get_state_when_change(self, *keys):
        """
        | Block until a state change is observed,
        | then return state.

        :param \*keys: only watch for changes in these keys (of state dict)
        :return: :code:`state`
        :rtype: dict
        """
        return self._req_rep_pull({Message.action: ZProcServer.add_change_handler.__name__, Message.keys: keys})

    def get_state_when(self, test_fn, *args, **kwargs):
        """
        | Block until testfn() returns a True-like value,
        | then return state.
        |
        | Roughly,
        | :code:`if test_fn(state, *args, **kwargs): return state`

        :param test_fn: | A callable that shall be called on each state-change.
                        | :code:`test_fn(state, *args, **kwargs)`
        :param args: Passed on to test_fn.
        :param kwargs: Passed on to test_fn.
        :return: :code:`state`.
        :rtype: dict

        .. code-block:: python
            :caption: Example

            def foo_is_bar(state):
                return state['foo'] == 'bar'

            state.get_when(foo_is_bar) # blocks until foo is bar!

        .. note:: | args and kwargs are assumed to be static.
                  |
                  | Their values will remain same throughout the life-time of the handler,
                  | irrespective of whether you change them in your code.
                  |
                  | If you have variables that are not static, you should put them in the state.

        .. note:: | The test_fn should be pure in general; meaning it shouldn't access variables from your code.
                  | (Actually, it can't, since its run inside a different namespace)
                  |
                  | It does have access to the state though, which is enough for most use-cases.
                  |
                  | If you try to access local variables without putting them through the args,
                  | an :code:`AttributeError: Can't pickle local object` shall be returned.
        """
        return self._req_rep_pull({
            Message.action: ZProcServer.add_condition_handler.__name__,
            Message.testfn: test_fn,
            Message.args: args,
            Message.kwargs: kwargs
        })

    def _get_remote_attr(self, name):
        dictattr = getattr(dict, name)

        if callable(dictattr):
            def remote_attr(*args, **kwargs):
                return self._req_rep({
                    Message.action: ZProcServer.get_state_callable.__name__,
                    Message.attr_name: name,
                    Message.args: args,
                    Message.kwargs: kwargs
                })

            return remote_attr
        else:
            return self._req_rep({
                Message.action: ZProcServer.get_state_attr.__name__,
                Message.attr_name: name,
            })

    def __getattr__(self, item):
        if item in DICT_ATTRS:
            return self._get_remote_attr(item)
        else:
            raise AttributeError

    def copy(self):
        return self._req_rep({Message.action: ZProcServer.send_state.__name__})

    def keys(self):
        return self.copy().keys()

    def items(self):
        return self.copy().items()

    def values(self):
        return self.copy().values()

    def __repr__(self):
        return '<ZeroState {0}>'.format(self.copy())

    def __contains__(self, *args, **kwargs):
        return self._get_remote_attr('__contains__')(*args, **kwargs)

    def __delitem__(self, *args, **kwargs):
        return self._get_remote_attr('__delitem__')(*args, **kwargs)

    def __eq__(self, *args, **kwargs):
        return self._get_remote_attr('__eq__')(*args, **kwargs)

    def __format__(self, *args, **kwargs):
        return self._get_remote_attr('__format__')(*args, **kwargs)

    def __getitem__(self, *args, **kwargs):
        return self._get_remote_attr('__getitem__')(*args, **kwargs)

    def __iter__(self, *args, **kwargs):
        return self._get_remote_attr('__iter__')(*args, **kwargs)

    def __len__(self, *args, **kwargs):
        return self._get_remote_attr('__len__')(*args, **kwargs)

    def __ne__(self, *args, **kwargs):
        return self._get_remote_attr('__ne__')(*args, **kwargs)

    def __setitem__(self, *args, **kwargs):
        return self._get_remote_attr('__setitem__')(*args, **kwargs)


def terminate_safe(pid):
    """Send SIGTERM to a pid. Ignore if it doesn't exist"""
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, TypeError):
        pass


class ZeroProcess:
    """
    Provides a high level wrapper over multiprocessing.Process.
    """

    def __init__(self, ipc_path, target, props, background=False):
        """
        :param ipc_path: the ipc path of the zproc server (associated with the context)
        :param target: | The callable object to be invoked by the start() method.
                       |
                       | It is run inside a child process with following args:
                       | :code:`target(state: ZeroState, props, proc: ZeroProcess)`
                       |
                       | The target may or may not have these arguments.
                       | ZProc will adjust according to your function!
                       | The order of these arguments must be preserved.

        :param props: passed on to the target at start(), useful for composing re-usable processes
        :param background: | Whether to run processes as background tasks.
                           | Background tasks keep running even when your main (parent) script finishes execution.

        :ivar target: Passed from constructor.
        :ivar props: Passed from constructor.
        :ivar background: Passed from constructor.
        """
        assert callable(target), "target must be a callable!"

        def child(ipc_path, target, props, proc):
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

        self._child_proc = Process(target=child, args=(ipc_path, target, props, self))

        self.target = target
        self.props = props
        self.background = background

    def start(self):
        """
        Start the child process

        :return: the process PID
        """
        if current_process().name != 'MainProcess':
            print(inception_msg)

        if not self.is_alive:
            self._child_proc.start()

        if not self.background:
            atexit.register(partial(terminate_safe, pid=self._child_proc.pid))

        return self._child_proc.pid

    def stop(self):
        """Stop the child process if it's alive"""
        if self.is_alive:
            self._child_proc.terminate()

    @property
    def is_alive(self):
        """
        | whether the child process is alive.
        |
        | Roughly, a process object is alive;
        | from the moment the start() method returns,
        | until the child process is stopped manually (using stop()) or naturally exits/
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
    def __init__(self, background=False):
        """
        | Create a new Context,
        | by starting the zproc server,
        | and generating a random ipc path to communicate with it.
        |
        | All child process under a Context are instances of ZeroProcess and hence,
        | retain the same API as that of a ZeroProcess instance.
        |
        | You may access the state (ZeroState instance) from the "state" attribute, like so - :code:`Context.state`
        |
        | A Context object is generally, thread-safe.

        :param background: | Whether to all run processes under this context as background tasks.
                           | Background tasks keep running even when your main (parent) script finishes execution.

        :ivar child_pids: A :code:`set` of pids (:code:`int`) of running processes under this Context.
        :ivar child_procs: A :code:`list` of :code:`ZeroProcess` instances launched under this Context.
        :ivar state: The :code:`ZeroState` object associated with this Context.
        :ivar background: Passed from constructor.
        """

        self.child_pids = set()
        self.child_procs = []
        self.background = background

        self._ipc_path = get_random_ipc()
        self._server_proc = Process(target=state_server, args=(self._ipc_path,))
        self._server_proc.start()

        if not self.background:
            atexit.register(partial(terminate_safe, pid=self._server_proc.pid))

        self.state = ZeroState(self._ipc_path)

    def process(self, target, props=None):
        """
        Produce a child process bound to this context.

        :param target: the callable to be invoked by the start() method (inside a child process)
        :param props: passed on to the target at start(), useful for composing re-usable processes
        :return: A ZeroProcess instance
        """
        proc = ZeroProcess(self._ipc_path, target, props, self.background)

        self.child_procs.append(proc)

        return proc

    def process_factory(self, *targets: callable, props=None, count=1):
        """
        Produce multiple child process(s) bound to this context.

        :param targets: callable(s) to be invoked by the start() method (inside a child process)
        :param props: passed on to all the targets at start(), useful for composing re-usable processes
        :param count: The number of child processes to spawn for each target
        :return: list containing ZeroProcess instances
        """
        child_procs = []
        for target in targets:
            for _ in range(count):
                child_procs.append(ZeroProcess(self._ipc_path, target, props, self.background))

        self.child_procs += child_procs

        return child_procs

    def stop_all(self):
        """Call ZeroProcess.stop() on all the child processes of this Context"""
        for proc in self.child_procs:
            pid = proc.pid
            proc.stop()

            self.child_pids.remove(pid)

    def start_all(self):
        """Call ZeroProcess.start() on all the child processes of this Context"""
        for proc in self.child_procs:
            if not proc.is_alive:
                self.child_pids.add(proc.start())

    def close(self):
        """
        | Close this context and stop all processes associated with it.
        | Once closed, you shouldn't use this Context again.
        """
        self.stop_all()

        if self._server_proc.is_alive():
            self._server_proc.terminate()

        del self.state
