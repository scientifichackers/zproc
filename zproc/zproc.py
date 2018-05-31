import atexit
import inspect
import os
import pickle
import signal
from functools import wraps
from multiprocessing import Process
from typing import Callable
from uuid import UUID, uuid1

import zmq
from time import sleep

from zproc.utils import reap_ptree, get_ipc_paths, Message, STATE_DICT_DYNAMIC_METHODS, \
    serialize_func, handle_server_response, method_injector
from zproc.zproc_server import ZProcServer, zproc_server_proc

signal.signal(signal.SIGTERM, reap_ptree)  # Add handler for the SIGTERM signal


class ZeroState:
    def __init__(self, uuid: UUID):
        """
        :param uuid: A ``UUID`` object for identifying the zproc server.

                     | You can use the UUID to reconstruct a ZeroState object, from any Process, at any time.

        :ivar uuid: Passed on from ``__init__()``

        | Allows accessing state stored on the zproc server, through a dict-like API.
        | Communicates to the zproc server using the ROUTER-DEALER pattern.

        | Don't share a ZeroState object between Process/Threads.
        | A ZeroState object is not thread-safe.

        Boasts the following ``dict``-like members:

        - Magic  methods:
            __contains__(),  __delitem__(), __eq__(), __getitem__(), __iter__(), __len__(), __ne__(), __setitem__()
        - Methods:
            clear(), copy(), fromkeys(), get(), items(),  keys(), pop(), popitem(), setdefault(), update(), values()
        """

        self.uuid = uuid
        self.identity = os.urandom(5)

        self.zmq_ctx = zmq.Context()

        self.server_ipc_path, self.bcast_ipc_path = get_ipc_paths(self.uuid)

        self.server_sock = self.zmq_ctx.socket(zmq.DEALER)
        self.server_sock.setsockopt(zmq.IDENTITY, self.identity)
        self.server_sock.connect(self.server_ipc_path)

        self.sub_sock = self._new_sub_sock()

    def _new_sub_sock(self):
        sock = self.zmq_ctx.socket(zmq.SUB)
        sock.connect(self.bcast_ipc_path)

        sock.setsockopt(zmq.SUBSCRIBE, b'')

        return sock

    def _sub_recv(self, sock):
        while True:
            ident, response = sock.recv_multipart()

            if ident != self.identity:
                return handle_server_response(pickle.loads(response))

    def _req_rep(self, request):
        self.server_sock.send_pyobj(request, protocol=pickle.HIGHEST_PROTOCOL)  # send msg
        response = self.server_sock.recv_pyobj()  # wait for reply
        return handle_server_response(response)

    def _get_state_method(self, name):
        def state_method(*args, **kwargs):
            return self._req_rep({
                Message.server_action: ZProcServer.state_method.__name__,
                Message.method_name: name,
                Message.args: args,
                Message.kwargs: kwargs
            })

        return state_method

    def go_live(self):
        self.sub_sock.close()
        self.sub_sock = self._new_sub_sock()

    def atomic(self, fn, *args, **kwargs):
        """
        | Run the ``fn`` in an *atomic* way.
        |
        | No Process shall access the state in any way whilst ``fn`` is running.
        | This helps avoid race-conditions, almost entirely.

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

        return self._req_rep({
            Message.server_action: ZProcServer.state_func.__name__,
            Message.func: serialize_func(fn),
            Message.args: args,
            Message.kwargs: kwargs
        })

    def atomify(self):
        """
        | Hack on a normal looking function to make an atomic operation out of it.
        | Allows making an arbitrary number of operations on sate, atomic.
        |
        | Just a little syntactic sugar over :func:`~ZeroState.atomic()`

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

    def get_when_change(self, *keys, live=True):
        """
        | Block until a change is observed.

        :param keys: | Observe for changes in these ``dict`` key(s).
                     | If no key is provided, any change in the ``state`` is respected.
        :param live: Whether to get "live" updates. See :ref:`state_watching`.
        :return: Roughly,
            .. code:: python

                if len(keys) == 1
                    return state.get(key)

                if len(keys) > 1
                    return [state.get(key) for key in keys]

                if len(keys) == 0 (Observe change in all keys)
                    return state.copy()
        """

        if live:
            sock = self._new_sub_sock()
        else:
            sock = self.sub_sock

        num_keys = len(keys)

        try:
            if num_keys == 1:
                key = keys[0]

                while True:
                    old, new = self._sub_recv(sock)

                    if new.get(key) != old.get(key):
                        return new
            elif num_keys:
                while True:
                    old, new = self._sub_recv(sock)

                    for key in keys:
                        if new.get(key) != old.get(key):
                            return [new.get(key) for key in keys]
            else:
                while True:
                    old, new = self._sub_recv(sock)

                    if new != old:
                        return new
        finally:
            if live:
                sock.close()

    def get_when(self, test_fn, *, live=True):
        """
        | Block until ``test_fn(state: ZeroState)`` returns a True-like value
        |
        | Roughly,

        .. code:: python

            if test_fn(state)
                return state.copy()

        :param test_fn: A ``function``, which is called on each state-change.
        :param live: Whether to get "live" updates. See :ref:`state_watching`.
        :return: state
        :rtype: ``dict``
        """

        if live:
            sock = self._new_sub_sock()
        else:
            sock = self.sub_sock

        new = self.copy()

        try:
            while True:
                if test_fn(new):
                    return new
                else:
                    new = self._sub_recv(sock)[-1]
        finally:
            if live:
                sock.close()

    def get_when_equal(self, key, value, *, live=True):
        """
        | Block until ``state.get(key) == value``.

        :param key: ``dict`` key
        :param value: ``dict`` value.
        :param live: Whether to get "live" updates. See :ref:`state_watching`.
        :return: ``state.get(key)``
        """

        if live:
            sock = self._new_sub_sock()
        else:
            sock = self.sub_sock

        new = self.get(key)

        try:
            while True:
                if new == value:
                    return new
                else:
                    new = self._sub_recv(sock)[-1].get(key)
        finally:
            if live:
                sock.close()

    def get_when_not_equal(self, key, value, *, live=True):
        """
        | Block until ``state.get(key) != value``.

        :param key: ``dict`` key.
        :param value: ``dict`` value.
        :param live: Whether to get "live" updates. See :ref:`state_watching`.
        :return: ``state.get(key)``
        """

        if live:
            sock = self._new_sub_sock()
        else:
            sock = self.sub_sock
        try:
            new = self.get(key)

            while True:
                if new != value:
                    return new
                else:
                    new = self._sub_recv(sock)[-1].get(key)
        finally:
            if live:
                sock.close()

    def close(self):
        """
        Close this ZeroState and disconnect with the ZProcServer
        """

        self.server_sock.close()
        self.sub_sock.close()

    def copy(self):
        return self._req_rep({Message.server_action: ZProcServer.reply_state.__name__})

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
        return self._get_state_method(name)(*args, **kwargs)

    return remote_method


method_injector(ZeroState, STATE_DICT_DYNAMIC_METHODS, _get_remote_method)


def _child_proc(self: 'ZeroProcess'):
    state = ZeroState(self.uuid)

    target_params = inspect.signature(self.target).parameters.copy()

    if 'kwargs' in target_params:
        target_kwargs = {'state': state, 'props': self.kwargs['props'], 'proc': self}
    else:
        target_kwargs = {}
        if 'state' in target_params:
            target_kwargs['state'] = state
        if 'props' in target_params:
            target_kwargs['props'] = self.kwargs['props']
        if 'proc' in target_params:
            target_kwargs['proc'] = self

    tries = 0
    while True:
        try:
            tries += 1
            self.target(**target_kwargs)
        except self.kwargs['retry_for'] as e:
            if self.kwargs['max_tries'] is not None and tries > self.kwargs['max_tries']:
                raise e

            target_kwargs['props'] = self.kwargs['retry_props']
            sleep(self.kwargs['retry_delay'])
        else:
            break


class ZeroProcess:
    def __init__(self, uuid: UUID, target: Callable, **kwargs):
        """
        Provides a high level wrapper over ``multiprocessing.Process``.

        :param uuid: A :class:`UUID` object for identifying the zproc server.

                     | You may use this to reconstruct a :class:`ZeroState` object, from any Process, at any time.

        :param target: The Callable to be invoked by the start() method.

                        | It is run inside a ``multiprocessing.Process`` with following kwargs:
                        | ``target(state=<ZeroState>, props=<props>, proc=<ZeroProcess>)``

                        | You may omit these, shall you not want them.

        :param props: (optional) Passed on to the target. By default, it is set to ``None``

        :param start: (optional) Automatically call :func:`.start()` on the process. By default, it is set to ``True``.

        :param retry_for: (optional) Automatically retry  whenever a particular exception is raised. By default, it is an empty ``tuple``

                          | For example,
                          | ``retry_for=(ConnectionError, ValueError)``

                          | To retry for *any* exception, just do
                          | ``retry_for=(Exception,)``


        :param retry_delay: (optional) The delay in seconds, before auto-retrying. By default, it is set to 5 secs

        :param retry_props: (optional) Provide different ``props`` to a Process when it's retrying. By default, it is the same as ``props``

                            Used to control how your application behaves, under retry conditions.


        :param max_retries: (optional) Give up after this many attempts. By default, it is set to ``None``.

                            | The exception that caused the Process to give up shall be re-raised.
                            | A value of ``None`` will result in an *infinite* number of retries.

        """

        assert callable(target), '"target" must be a Callable, not {}!'.format(type(target))

        self.uuid = uuid
        self.target = target
        self.kwargs = kwargs

        self.kwargs.setdefault('props', None)
        self.kwargs.setdefault('start', True)
        self.kwargs.setdefault('retry_for', ())
        self.kwargs.setdefault('retry_delay', ())
        self.kwargs.setdefault('retry_props', self.kwargs['props'])
        self.kwargs.setdefault('max_retries', None)

        self.child_proc = Process(target=_child_proc, args=(self,))

        if self.kwargs['start']:
            self.start()

    def start(self):
        """
        Start this process

        :return: the process PID
        """

        try:
            if not self.is_alive:
                self.child_proc.start()
        except AssertionError:  # occurs when a Process was started, but not alive
            pass

        return self.child_proc.pid

    def stop(self):
        """Stop this process if it's alive"""

        if self.is_alive:
            self.child_proc.terminate()

    @property
    def is_alive(self):
        """
        | whether the child process is alive.
        |
        | Roughly, a process object is alive;
        | from the moment the start() method returns,
        | until the child process is stopped manually (using stop()) or naturally exits
        """

        return self.child_proc and self.child_proc.is_alive()

    @property
    def pid(self):
        """
        | The process ID.
        | Before the process is started, this will be None.
        """

        if self.child_proc is not None:
            return self.child_proc.pid

    @property
    def exitcode(self):
        """
        | The child’s exit code.
        | This will be None if the process has not yet terminated.
        | A negative value -N indicates that the child was terminated by signal N.
        """

        if self.child_proc is not None:
            return self.child_proc.exitcode


class Context:
    def __init__(self, background=False):
        """
        A Context holds information about the current process.

        It is responsible for the creation and management of Processes.

        | Don't share a Context object between Process/Threads.
        | A Context object is not thread-safe.

        :param background: | Whether to run processes under this context as background tasks.
                           | Background tasks keep running even when your main (parent) script finishes execution.

        :ivar state: :class:`ZeroState` object. The global state.
        :ivar child_pids: ``set[int]``. The pid(s) of Process(s) alive in this Context.
        :ivar child_procs: ``list[:class:`ZeroProcess`]``. The child Process(s) created in this Context.
        :ivar background: Passed from constructor.
        :ivar uuid:  A ``UUID`` for identifying the zproc server.
        :ivar server_proc: A ``multiprocessing.Process`` object for the server.
        """

        self.child_pids = set()
        self.child_procs = []
        self.background = background

        self.uuid = uuid1()

        self.server_proc = Process(target=zproc_server_proc, args=(self.uuid,))
        self.server_proc.start()

        if not background:
            atexit.register(reap_ptree)  # kill all the child procs when main script exits

        self.state = ZeroState(self.uuid)

    def process(self, target, **kwargs):
        """
        Produce a child process bound to this context.

        :param target: Passed on to :class:`ZeroProcess`'s constructor.
        :param \*\*kwargs: Optional keyword arguments that :class:`ZeroProcess` takes.
        """

        proc = ZeroProcess(self.uuid, target, **kwargs)

        self.child_procs.append(proc)

        return proc

    def processify(self, **kwargs):
        """
        The decorator version of :func:`~Context.process`

        :param \*\*kwargs: Optional keyword arguments that :class:`ZeroProcess` takes.
        :return: A processify decorator, which itself returns a :class:`ZeroProcess` instance.
        :rtype: function
        """

        def processify_decorator(func):
            return self.process(func, **kwargs)

        return processify_decorator

    def process_factory(self, *targets: Callable, count=1, **kwargs):
        """
        Produce multiple child process(s) bound to this context.

        :param targets: Passed on to :class:`ZeroProcess`'s constructor.
        :param count: The number of processes to spawn for each target
        :param \*\*kwargs: Optional keyword arguments that :class:`ZeroProcess` takes.
        :return: spawned processes
        :rtype: list[ZeroProcess]
        """

        child_procs = []
        for target in targets:
            for _ in range(count):
                child_procs.append(ZeroProcess(self.uuid, target, **kwargs))
        self.child_procs += child_procs

        return child_procs

    def _get_watcher_decorator(self, fn_name, *args, **kwargs):
        def watcher_decorator(fn):
            def watcher_proc(state, props, proc):
                target_params = inspect.signature(fn).parameters.copy()

                if 'kwargs' in target_params:
                    target_kwargs = {'state': state, 'props': props, 'proc': proc}
                else:
                    target_kwargs = {}
                    if 'state' in target_params:
                        target_kwargs['state'] = state
                    if 'props' in target_params:
                        target_kwargs['props'] = props
                    if 'proc' in target_params:
                        target_kwargs['proc'] = proc

                while True:
                    getattr(state, fn_name)(*args, **kwargs)
                    fn(**target_kwargs)

            return self.process(watcher_proc)

        return watcher_decorator

    def call_when_change(self, *keys, live=False):
        """Decorator version of :func:`~ZeroState.get_when_change()`"""

        return self._get_watcher_decorator('get_when_change', *keys, live=live)

    def call_when(self, test_fn, *, live=False):
        """Decorator version of :func:`~ZeroState.get_when()`"""

        return self._get_watcher_decorator('get_when', test_fn, live=live)

    def call_when_equal(self, key, value, *, live=False):
        """Decorator version of :func:`~ZeroState.get_when_equal()`"""

        return self._get_watcher_decorator('get_when_equal', key, value, live=live)

    def call_when_not_equal(self, key, value, *, live=False):
        """Decorator version of :func:`~ZeroState.get_when_not_equal()`"""

        return self._get_watcher_decorator('get_when_not_equal', key, value, live=live)

    def start_all(self):
        """Call :func:`~ZeroProcess.start()` on all the child processes of this Context"""
        for proc in self.child_procs:
            if not proc.is_alive:
                self.child_pids.add(proc.start())

    def stop_all(self):
        """Call :func:`~ZeroProcess.stop()` on all the child processes of this Context"""
        for proc in self.child_procs:
            pid = proc.pid
            proc.stop()

            try:
                self.child_pids.remove(pid)
            except KeyError:
                pass

    def close(self):
        """
        Close this context and stop all processes associated with it.

        Once closed, you shouldn't use this Context again.
        """

        self.stop_all()

        if self.server_proc.is_alive():
            self.server_proc.terminate()

        self.state.close()
