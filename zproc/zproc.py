import atexit
import marshal
import os
import signal
from functools import partial
from multiprocessing import Process, current_process
# from time import sleep
from types import FunctionType

import zmq

from .zproc_server import ACTIONS, MSGS, state_server, get_random_ipc

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
2. The existence of global mutable state indicates a flaw in the application’s design, which you should review and change.
3. Don't launch processes inside processes.
4. Don't launch processes inside processes.
5. Don't launch processes inside processes.
...

Hope we all learned something today.
"""


def pysend(sock, msg):
    data = marshal.dumps(msg)
    # print('sending',msg, data)
    return sock.send(data)
    # print('sent')


def pyrecv(sock):
    # print('recv')
    data = marshal.loads(sock.recv())
    # print('recv', data)
    return data


def kill_if_alive(pid):
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass


class ZeroState:
    """
    | Allows accessing state stored on the zproc server,
    | through a dict-like interface,
    | by communicating the state over zeromq.

    :param ipc_path: The ipc path of the zproc servers

    | It provides the following methods, to make it feel like a dict

    - get()
    - pop()
    - popitem()
    - clear()
    - update()
    - setdefault()
    - clear()
    - items()
    - keys()
    - values()
    - __setitem__()  | :code:`state['foo'] = 'bar'`
    - __delitem__()  | :code:`del state['foo']`
    - __getitem__()  | :code:`state['foo']`
    - __contains__() | :code:`'foo' in state`
    - __eq__ ()      | :code:`{'foo': 'bar'} == state`
    - __ne__ ()      | :code:`{'foo': 'bar'} != state`
    - __copy__()     | :code:`state_copy = state.copy()`

    | It also provides the following methods, as a substitute for traditional synchronization primitives.

    - get_when_change()
    - get_val_when_change()
    - get_when()

    | These methods are the reason why ZProc is better than traditional multi-processing.
    | They allow you to watch for changes directly in your state, without having to worry about irrelevant details.

    .. note:: | While the zproc server is very efficient at handling stuff,
              | You should use this feature wisely.
              | Adding a lot of synchronization handlers will ultimately slow down your application.
              |
              | If you're interested in the mathematics of it,
              | Each new synchronization handler increases complexity, linearly.
              | The frequency at which you update the state also affects the complexity linearly.
              |
              | Keep these in mind when developing performance-critical applications.

    """

    def __init__(self, ipc_path):
        self._ctx = zmq.Context()
        self._sock = self._ctx.socket(zmq.DEALER)
        self._sock.connect(ipc_path)
        # sleep(1)

    def _get(self, msg):
        pysend(self._sock, msg)
        return pyrecv(self._sock)

    def get_when_change(self, *keys):
        """
        | Block until a state change is observed,
        | then return the state.
        |
        | Useful for synchronization between processes

        :param keys: only watch for changes in these keys (of state dict)
        :return: dict (state)


        """

        ipc_path = self._get({MSGS.ACTION: ACTIONS.add_chng_hand, MSGS.state_keys: keys})

        sock = self._ctx.socket(zmq.PULL)
        sock.connect(ipc_path)
        state = marshal.loads(sock.recv())
        sock.close()

        return state

    def get_val_when_change(self, key):
        """
        | Block until a state change is observed in provided key,
        | then return value of that key.
        |
        | Useful for synchronization between processes

        :param key: the key (of state dict) to watch for changes
        :return: value corresponding to the key, in the state
        """
        ipc_path = self._get({MSGS.ACTION: ACTIONS.add_val_chng_hand, MSGS.state_key: key})

        sock = self._ctx.socket(zmq.PULL)
        sock.connect(ipc_path)
        val = marshal.loads(sock.recv())
        sock.close()

        return val

    def get_when(self, test_fn: FunctionType, *args, **kwargs):
        """
        | Block until testfn() returns a True-like value,
        | then return the state.
        |
        | Useful for synchronization between processes

        :param test_fn: | A user-defined function that shall be called on each state-change.
                        | :code:`test_fn(state, *args, **kwargs)`
        :param args: Passed on to test_fn.
        :param kwargs: Passed on to test_fn.
        :return: dict (state)

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
        """
        assert isinstance(test_fn, FunctionType), 'fn must be a user-defined function, not ' + str(test_fn.__class__)

        ipc_path = self._get({
            MSGS.ACTION: ACTIONS.add_cond_hand,
            MSGS.testfn: test_fn.__code__,
            MSGS.args: args,
            MSGS.kwargs: kwargs
        })

        sock = self._ctx.socket(zmq.PULL)
        sock.connect(ipc_path)
        response = marshal.loads(sock.recv())
        sock.close()

        return response

    def get_state_as_dict(self):
        """Get the state from the zproc server and return as dict"""
        return self._get({MSGS.ACTION: ACTIONS.get_state})

    def items(self):
        return self.get_state_as_dict().items()

    def keys(self):
        return self.get_state_as_dict().keys()

    def values(self):
        return self.get_state_as_dict().values()

    def pop(self, key, default=None):
        return self._get({MSGS.ACTION: ACTIONS.pop, MSGS.args: (key, default)})

    def popitem(self):
        return self._get({MSGS.ACTION: ACTIONS.popitem})

    def get(self, key, default=None):
        return self._get({MSGS.ACTION: ACTIONS.get, MSGS.args: (key, default)})

    def clear(self):
        return self._get({MSGS.ACTION: ACTIONS.clear})

    def update(self, *args, **kwargs):
        return self._get({MSGS.ACTION: ACTIONS.update, MSGS.args: args, MSGS.kwargs: kwargs})

    def setdefault(self, key, default=None):
        return self._get({MSGS.ACTION: ACTIONS.setdefault, MSGS.args: (key, default)})

    def __str__(self):
        return str(self.get_state_as_dict())

    def __repr__(self):
        return '<ZeroState {0}>'.format(str(self))

    def __copy__(self):
        return self.get_state_as_dict()

    def __setitem__(self, key, value):
        return self._get({MSGS.ACTION: ACTIONS.setitem, MSGS.args: (key, value)})

    def __delitem__(self, key):
        return self._get({MSGS.ACTION: ACTIONS.delitem, MSGS.args: (key,)})

    def __getitem__(self, item):
        return self._get({MSGS.ACTION: ACTIONS.getitem, MSGS.args: (item,)})

    def __contains__(self, item):
        return self._get({MSGS.ACTION: ACTIONS.contains, MSGS.args: (item,)})

    def __eq__(self, other):
        return self._get({MSGS.ACTION: ACTIONS.eq, MSGS.args: (other,)})

    def __ne__(self, other):
        return self._get({MSGS.ACTION: ACTIONS.ne, MSGS.args: (other,)})


class ZeroProcess:
    """
    Provides a high level wrapper over multiprocessing.Process and zeromq\n

    the target is run inside a child process and shares state with the parent using a ZeroState object.
    """

    def __init__(self, ipc_path, target, props, background=False):
        """
        :param ipc_path: the ipc path of the zproc server (associated with the context)
        :param target: the callable object to be invoked by the start() method (inside a child process)
        :param props: passed on to the target at start(), useful for composing re-usable processes
        :param background: Whether to run processes as background tasks.\n
                           Background tasks keep running even when your main (parent) script finishes execution.
        """
        assert callable(target), "Mainloop must be a callable!"

        def child(ipc_path, target, props):
            zstate = ZeroState(ipc_path)
            target(zstate, props)

        self._child_proc = Process(target=child, args=(ipc_path, target, props))
        self.target = target
        self.is_background = background

    def start(self):
        """
        Start the child process

        :return: the process PID
        """
        if current_process().name != 'MainProcess': print(inception_msg)

        if not self.is_alive:
            self._child_proc.start()

        if not self.is_background:
            atexit.register(partial(kill_if_alive, pid=self._child_proc.pid))

        return self._child_proc.pid

    def stop(self):
        """Stop the child process if it's alive"""
        if self.is_alive:
            self._child_proc.terminate()

    @property
    def is_alive(self):
        """
        whether the child process is alive.

        Roughly, a process object is alive\n
            from the moment the start() method returns\n
            until the child process is stopped manually (using stop()) or naturally exits
        """
        return self._child_proc and self._child_proc.is_alive()

    @property
    def pid(self):
        """
        The process ID.\n
        Before the process is started, this will be None.
        """
        if self._child_proc is not None:
            return self._child_proc.pid

    @property
    def exitcode(self):
        """
        The child’s exit code.\n
        This will be None if the process has not yet terminated.\n
        A negative value -N indicates that the child was terminated by signal N.\n
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
        | All child process under a Context are instances of ZeroProcess and hence, retain the same API as that of a ZeroProcess instance.\n\n
        |
        | You may access the state (ZeroState instance) from the "state" attribute, like so - :code:`Context.state`
        |
        | A Context object is generally, thread-safe.\n

        :param background: Whether to all run processes under this context as background tasks.\n
                           Background tasks keep running even when your main (parent) script finishes execution.
        """

        self.child_pids = set()
        self.child_procs = []
        self.is_background = background

        self._ipc_path = get_random_ipc()
        self._state_proc = Process(target=state_server, args=(self._ipc_path,))
        self._state_proc.start()

        if not self.is_background:
            atexit.register(partial(kill_if_alive, pid=self._state_proc.pid))

        self.state = ZeroState(self._ipc_path)

    def process(self, target, props=None):
        """
        Produce a child process bound to this context.

        :param targets: the callable to be invoked by the start() method (inside a child process)
        :param props: passed on to the target at start(), useful for composing re-usable processes
        :return: A ZeroProcess instance
        """
        proc = ZeroProcess(self._ipc_path, target, props, self.is_background)

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
                child_procs.append(ZeroProcess(self._ipc_path, target, props, self.is_background))

        self.child_procs += child_procs

        return child_procs

    def stop_all(self):
        """Call ZeroProcess.stop() on all the child processes of this Context"""
        for proc in self.child_procs:
            proc.stop()

    def start_all(self):
        """Call ZeroProcess.start() on all the child processes of this Context"""
        pids = set()

        for proc in self.child_procs:
            pids.add(proc.start())

        self.child_pids.update(pids)

        return pids

    def close(self):
        """Close this context and stop all processes associated with it."""
        if self._state_proc.is_alive:
            self._state_proc.terminate()

        for proc in self.child_procs:
            proc.stop()
