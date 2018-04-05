import atexit
import marshal
import os
import signal
from collections import defaultdict
from functools import partial
from multiprocessing import Process
from pathlib import Path
# from time import sleep
from types import FunctionType
from uuid import uuid1

import zmq


class ACTION:
    POP = 'pop'
    POPITEM = 'popitem'
    CLEAR = 'clear'
    UPDATE = 'update'
    SETDEFAULT = 'setdefault'
    SETITEM = '__setitem__'
    DELITEM = '__delitem__'

    GET = 'get'
    GETITEM = '__getitem__'
    CONTAINS = '__contains__'
    EQ = '__eq__'

    GET_STATE = 'get_state'
    STOP = 'STOP'

    ADD_CONDITION_HANDLER = 'add_condition_handler'
    ADD_STATE_HANDLER = 'add_state_handler'


ACTIONS_THAT_MUTATE = (
    ACTION.SETITEM,
    ACTION.DELITEM,
    ACTION.SETDEFAULT,
    ACTION.POP,
    ACTION.POPITEM,
    ACTION.CLEAR,
    ACTION.UPDATE,
)


class MSG:
    ACTION = 'action'
    ARGS = 'args'
    KWARGS = 'kwargs'

    TEST_FN = 'callable'
    IDENT = 'identity'

    STATE_KEY = 'state_key'


ipc_base_dir = Path.home().joinpath('.tmp')

if not ipc_base_dir.exists():
    ipc_base_dir.mkdir()


def get_random_ipc():
    return get_ipc_path(uuid1())


def get_ipc_path(uuid):
    return 'ipc://' + str(ipc_base_dir.joinpath(str(uuid)))


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


def state_server(ipc_path):
    def pysend(msg):
        return sock.send_multipart([ident, marshal.dumps(msg)])

    def pyrecv():
        ident, msg = sock.recv_multipart()
        return ident, marshal.loads(msg)

    def resolve_state_handlers():
        complete = []
        for state_key, handler_list in state_handlers.items():
            if state_key == '__all__':
                new = state
            else:
                new = state.get(state_key)

            for index, (ipc_path, old) in enumerate(handler_list):
                if old != new:
                    sock = ctx.socket(zmq.PUSH)
                    sock.bind(ipc_path)
                    sock.send(marshal.dumps(state))
                    sock.close()

                    complete.append((state_key, index))

        for state_key, index in complete:
            del state_handlers[state_key][index]

    def resolve_condition_handlers():
        complete = []
        for index, (ipc_path, test_fn) in enumerate(condition_handlers):
            if test_fn(state):
                sock = ctx.socket(zmq.PUSH)
                sock.bind(ipc_path)
                sock.send(marshal.dumps(state))
                sock.close()

                complete.append(index)

        for index in complete:
            del condition_handlers[index]

    ctx = zmq.Context()
    sock = ctx.socket(zmq.ROUTER)
    sock.bind(ipc_path)
    # sleep(1)
    state = {}
    condition_handlers = []
    state_handlers = defaultdict(list)

    while True:
        ident, msg = pyrecv()
        # print('server', msg, 'from', ident)
        action = msg.get(MSG.ACTION)

        if action is not None:
            if action == ACTION.GET_STATE:
                pysend(state)
            elif action == ACTION.STOP:
                break
            elif action == ACTION.ADD_CONDITION_HANDLER and MSG.TEST_FN in msg:
                ipc_path = get_random_ipc()
                condition_handlers.append((ipc_path, FunctionType(msg[MSG.TEST_FN], globals())))
                pysend(ipc_path)
                resolve_condition_handlers()
            elif action == ACTION.ADD_STATE_HANDLER:
                ipc_path = get_random_ipc()

                state_key = msg.get(MSG.STATE_KEY)
                if state_key is None:
                    state_handlers['__all__'].append((ipc_path, state.copy()))
                else:
                    state_handlers[state_key].append((ipc_path, state.get(state_key)))

                pysend(ipc_path)
                resolve_state_handlers()
            else:
                args, kwargs = msg.get(MSG.ARGS), msg.get(MSG.KWARGS)
                fn = getattr(state, action)

                if args is None:
                    if kwargs is None:
                        pysend(fn())
                    else:
                        pysend(fn(**kwargs))
                else:
                    if kwargs is None:
                        pysend(fn(*args))
                    else:
                        pysend(fn(*args, **kwargs))

            if action in ACTIONS_THAT_MUTATE:
                # print(state_handlers)
                resolve_state_handlers()
                resolve_condition_handlers()
                # print(state_handlers)


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

    def get_state_when_change(self, key=None):
        """
        Block until a state change is observed,
        then return the state.

        Useful for synchronization between processes

        Args:
            key: only watch for changes in this key of state dict

        Returns:
            dict: containing the state
        """
        ipc_path = self._get({MSG.ACTION: ACTION.ADD_STATE_HANDLER, MSG.STATE_KEY: key})

        sock = self._ctx.socket(zmq.PULL)
        sock.connect(ipc_path)
        state = marshal.loads(sock.recv())
        sock.close()

        return state

    def get_state_when(self, test_fn):
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

        ipc_path = self._get({MSG.ACTION: ACTION.ADD_CONDITION_HANDLER, MSG.TEST_FN: test_fn.__code__})

        sock = self._ctx.socket(zmq.PULL)
        sock.connect(ipc_path)
        response = marshal.loads(sock.recv())
        sock.close()

        return response

    def items(self):
        return self._get({MSG.ACTION: ACTION.GET_STATE}).items()

    def keys(self):
        return self._get({MSG.ACTION: ACTION.GET_STATE}).keys()

    def values(self):
        return self._get({MSG.ACTION: ACTION.GET_STATE}).values()

    def pop(self, key, default=None):
        return self._get({MSG.ACTION: ACTION.POP, MSG.ARGS: (key, default)})

    def popitem(self):
        return self._get({MSG.ACTION: ACTION.POPITEM})

    def get(self, key, default=None):
        return self._get({MSG.ACTION: ACTION.GET, MSG.ARGS: (key, default)})

    def clear(self):
        return self._get({MSG.ACTION: ACTION.CLEAR})

    def update(self, *args, **kwargs):
        return self._get({MSG.ACTION: ACTION.UPDATE, MSG.ARGS: args, MSG.KWARGS: kwargs})

    def setdefault(self, key, default=None):
        return self._get({MSG.ACTION: ACTION.SETDEFAULT, MSG.ARGS: (key, default)})

    def __str__(self):
        return str(self._get({MSG.ACTION: ACTION.GET_STATE}))

    def __setitem__(self, key, value):
        return self._get({MSG.ACTION: ACTION.SETITEM, MSG.ARGS: (key, value)})

    def __delitem__(self, key):
        return self._get({MSG.ACTION: ACTION.DELITEM, MSG.ARGS: (key,)})

    def __getitem__(self, item):
        return self._get({MSG.ACTION: ACTION.GETITEM, MSG.ARGS: (item,)})

    def __contains__(self, item):
        return self._get({MSG.ACTION: ACTION.CONTAINS, MSG.ARGS: (item,)})

    def __eq__(self, other):
        return self._get({MSG.ACTION: ACTION.EQ, MSG.ARGS: (other,)})


class ZeroProcess:
    """
    Provides a high level wrapper over multiprocessing.Process and zeromq

    the target is start inside a child process and shares state with the parent using a ZeroState object.
    """

    def __init__(self, ipc_path, target, props):
        """
        Args:
            ipc_path: the ipc path for the state server (associated with the context)
            target: the callable object to be invoked by the start() method (inside a child process)
            props: passed on to the target at start(), useful for composing re-usable processes
        """
        assert callable(target), "Mainloop must be a callable!"

        def child(ipc_path, target, props):
            zstate = ZeroState(ipc_path)
            target(zstate, props)

        self._child_proc = Process(target=child, args=(ipc_path, target, props))

    def start(self):
        """
        Start the child process

        Returns:
            the process PID
        """
        if not self.is_alive:
            self._child_proc.start()

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
    def __init__(self):
        self.child_pids = set()
        self._ipc_path = get_random_ipc()
        self._child_procs = []
        self._state_proc = Process(target=state_server, args=(self._ipc_path,), daemon=True)
        self._state_proc.start()
        # atexit.register(partial(kill_if_alive, pid=self._state_proc.pid))

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
        proc = ZeroProcess(self._ipc_path, target, props)

        self._child_procs.append(proc)

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
                child_procs.append(ZeroProcess(self._ipc_path, target, props))

        self._child_procs += child_procs

        return child_procs

    def stop_all(self):
        for proc in self._child_procs:
            proc.stop()

    def start_all(self):
        pids = set()

        for proc in self._child_procs:
            pids.add(proc.start())

        self.child_pids.update(pids)

        return pids

    def close(self):
        if self._state_proc.is_alive:
            self._state_proc.terminate()

        for proc in self._child_procs:
            proc.stop()
