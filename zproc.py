import atexit
import marshal
import os
import signal
from functools import partial
from multiprocessing import Process, current_process
# from time import sleep
from types import FunctionType

import zmq

from zproc_server import ACTIONS, MSGS, state_server, get_random_ipc

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
    Allows accessing a remote state (dict) object, through a dict-like interface,
    by communicating the state over zeromq.
    """

    # next_ident = 0

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
        Block until a state change is observed,
        then return the state.

        Useful for synchronization between processes

        Args:
            *keys: only watch for changes in these keys (of state dict)

        Returns:
            dict: containing the state
        """

        ipc_path = self._get({MSGS.ACTION: ACTIONS.add_chng_hand, MSGS.state_keys: keys})

        sock = self._ctx.socket(zmq.PULL)
        sock.connect(ipc_path)
        state = marshal.loads(sock.recv())
        sock.close()

        return state

    def get_val_when_change(self, key):
        """
        Block until a state change is observed in a key,
        then return value of that key.

        Useful for synchronization between processes

        Args:
            key: the key to watch for changes

        Returns:
            value corresponding to the key in state dict
        """
        ipc_path = self._get({MSGS.ACTION: ACTIONS.add_val_chng_hand, MSGS.state_key: key})

        sock = self._ctx.socket(zmq.PULL)
        sock.connect(ipc_path)
        val = marshal.loads(sock.recv())
        sock.close()

        return val

    def get_when(self, test_fn):
        """
        Block until the provided testfn returns a True boolean value,
        then return the state.

        Args:
            test_fn: A user-defined function that shall be called on each state-change

        Notes:
            The condition should be pure in general; meaning it shouldn't access global variables from your code.
            (It actually can't since its run inside a different namespace)

            It does have access to the global state dict though, which is enough for most use-cases.

        Useful for synchronization between processes

        Returns:
            dict: containing the state
        """
        assert isinstance(test_fn, FunctionType), 'fn must be a user-defined function, not ' + str(test_fn.__class__)

        ipc_path = self._get({MSGS.ACTION: ACTIONS.add_cond_hand, MSGS.testfn: test_fn.__code__})

        sock = self._ctx.socket(zmq.PULL)
        sock.connect(ipc_path)
        response = marshal.loads(sock.recv())
        sock.close()

        return response

    def items(self):
        return self._get({MSGS.ACTION: ACTIONS.get_state}).items()

    def keys(self):
        return self._get({MSGS.ACTION: ACTIONS.get_state}).keys()

    def values(self):
        return self._get({MSGS.ACTION: ACTIONS.get_state}).values()

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
        return str(self._get({MSGS.ACTION: ACTIONS.get_state}))

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


class ZeroProcess:
    """
    Provides a high level wrapper over multiprocessing.Process and zeromq

    the target is start inside a child process and shares state with the parent using a ZeroState object.
    """

    def __init__(self, ipc_path, target, props, background=False):
        """
        Args:
            ipc_path: the ipc path for the state server (associated with the context)
            target: the callable object to be invoked by the start() method (inside a child process)
            props: passed on to the target at start(), useful for composing re-usable processes
            background: background: Whether to run processes as background tasks.
                        Background tasks keep running even when your main (parent) script exits.
        """
        assert callable(target), "Mainloop must be a callable!"

        def child(ipc_path, target, props):
            zstate = ZeroState(ipc_path)
            target(zstate, props)

        self._child_proc = Process(target=child, args=(ipc_path, target, props))
        self.target = target
        self.background = background

    def start(self):
        """
        Start the child process

        Returns:
            the process PID
        """
        if current_process().name != 'MainProcess': print(inception_msg)

        if not self.is_alive:
            self._child_proc.start()

        if not self.background:
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

        Roughly, a process object is alive
            from the moment the start() method returns
            until the child process is stopped manually (using stop()) or naturally exits
        """
        return self._child_proc and self._child_proc.is_alive()

    @property
    def pid(self):
        """
        The process ID.
        Before the process is started, this will be None.
        """
        if self._child_proc is not None:
            return self._child_proc.pid

    @property
    def exitcode(self):
        """
        The child’s exit code.
        This will be None if the process has not yet terminated.
        A negative value -N indicates that the child was terminated by signal N.
        """
        if self._child_proc is not None:
            return self._child_proc.exitcode


class Context:
    def __init__(self, background=False):
        """
        Initiate the context, by starting a state-manager server,
         and generate a random ipc path to communicate with it
        Args:
            background: Whether to run processes as background tasks.
                        Background tasks keep running even when your main (parent) script exits.
        """
        self.child_pids = set()
        self.child_procs = []
        self.background = background

        self._ipc_path = get_random_ipc()
        self._state_proc = Process(target=state_server, args=(self._ipc_path,))
        self._state_proc.start()

        if not self.background:
            atexit.register(partial(kill_if_alive, pid=self._state_proc.pid))

        self.state = ZeroState(self._ipc_path)

    def process(self, target, props=None):
        """
        Produce a single ZeroProcess instance, bound to this context given a single target

        Args:
            target: the callable object to be invoked by the start() method (inside a child process)
            props: passed on to the target at start(), useful for composing re-usable processes

        Returns:
            The ZeroProcess instance
        """
        proc = ZeroProcess(self._ipc_path, target, props, self.background)

        self.child_procs.append(proc)

        return proc

    def process_factory(self, *targets, props=None, count=1):
        """
        Produces multiple child process(s) (ZeroProcesses) provided some targets

        Args:
            *targets: callable(s) to be invoked by the start() method (inside a child process)
            props: passed on to all the targets at start(), useful for composing re-usable processes
            count: The number of child processes to spawn for each target

        Returns:
            The ZeroProcess instances produced
        """
        child_procs = []
        for target in targets:
            for _ in range(count):
                child_procs.append(ZeroProcess(self._ipc_path, target, props, self.background))

        self.child_procs += child_procs

        return child_procs

    def stop_all(self):
        for proc in self.child_procs:
            proc.stop()

    def start_all(self):
        pids = set()

        for proc in self.child_procs:
            pids.add(proc.start())

        self.child_pids.update(pids)

        return pids

    def close(self):
        if self._state_proc.is_alive:
            self._state_proc.terminate()

        for proc in self.child_procs:
            proc.stop()
