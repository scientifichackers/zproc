import os
import signal
import sys
from collections import deque
from pathlib import Path
from types import FunctionType
from typing import Tuple
from uuid import uuid1, UUID

import dill
import psutil

ipc_base_dir = Path.home().joinpath('.tmp')

if not ipc_base_dir.exists():
    ipc_base_dir.mkdir()


class RemoteException:
    def __init__(self):
        self.exc = sys.exc_info()

    def reraise(self):
        raise self.exc[0].with_traceback(self.exc[1], self.exc[2])

    def __str__(self):
        return str(self.exc)


class SignalException(Exception):
    def __init__(self, sig, frame):
        super().__init__('')
        self.sig = sig
        self.frame = frame


def signal_to_exception(sig):
    """Convert a signal to :py:exc:`SignalException`"""

    def handler(sig, frame):
        raise SignalException(sig, frame)

    signal.signal(sig, handler)


def de_serialize_func(fn_bytes: bytes) -> FunctionType:
    return dill.loads(fn_bytes)


def serialize_func(fn: FunctionType) -> bytes:
    return dill.dumps(fn)


def get_random_ipc() -> Tuple[str, str]:
    return get_ipc_paths(uuid1())


def handle_server_response(response):
    # if the reply is a remote Exception, re-raise it!
    if isinstance(response, RemoteException):
        response.reraise()
    else:
        return response


def get_ipc_paths(uuid: UUID) -> Tuple[str, str]:
    """Given a UUID, identifying the Context, return a tuple -> (<ROUTER/DEALER ipc path>, <PUB/SUB ipc path>)"""

    return 'ipc://' + str(ipc_base_dir.joinpath('zproc_server_' + str(uuid))), \
           'ipc://' + str(ipc_base_dir.joinpath('zproc_bcast_' + str(uuid)))


def method_injector(t: type, names: Tuple[str], get_method):
    for name in names:
        setattr(t, name, get_method(name))


def shutdown(*args):
    procs = psutil.Process().children(recursive=True)

    for proc in procs:
        os.kill(proc.pid, signal.SIGTERM)

    if len(args):
        os._exit(args[0])
    else:
        os._exit(0)


class Queue(deque):
    """A Queue that can be drained"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def enqueue(self, something):
        self.appendleft(something)

    def dequeue(self):
        self.pop()

    def drain(self):
        # create a copy of the deque, to prevent shit-storms while iterating :)
        iter_deque = self.copy()
        self.clear()

        while True:
            try:
                yield iter_deque.pop()
            except IndexError:
                break


_ZPROC_CRASH_REPORT = """
ZProc crash report:
    {}
    {}
    Next retry in - {} sec
    Tried - {} time(s)
    Pid - {}
"""

_ZPROC_FINAL_CRASH_REPORT = """
ZProc crash report:
    {}
    {}
    Tried - {} time(s)
    Pid - {}
    **Max tries reached!**
"""


def print_crash_report(proc, e, retry_delay, tries, max_tries):
    if isinstance(e, SignalException):
        msg = 'Signal - {}'.format(repr(e.sig))
    else:
        msg = 'Exception - {}'.format(repr(e))

    if max_tries != -1 and tries >= max_tries:
        print(_ZPROC_FINAL_CRASH_REPORT.format(proc, msg, retry_delay, tries))

        if isinstance(e, SignalException):
            signal.signal(e.sig, signal.SIG_DFL)
    else:
        print(_ZPROC_CRASH_REPORT.format(proc, msg, retry_delay, tries, proc.pid))


# static declarations

STATE_DICT_LIKE_METHODS = {
    '__contains__',
    '__delitem__',
    '__eq__',
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
}

DICT_MUTABLE_ACTIONS = {
    '__setitem__',
    '__delitem__',
    'setdefault',
    'pop',
    'popitem',
    'clear',
    'update',
}

STATE_DICT_DYNAMIC_METHODS = set(STATE_DICT_LIKE_METHODS) - {'__copy__', 'items', 'keys', 'values'}


class Message:
    server_action = 'action'

    args = 'args'
    kwargs = 'kwargs'

    func = 'fn'

    key = 'key'
    keys = 'keys'
    value = 'value'

    method_name = 'method'
    ping_data = 'ping'


WINDOWS_SIGNALS = (
    'SIGABRT',
    'SIGFPE',
    'SIGILL',
    'SIGINT',
    'SIGSEGV',
    'SIGTERM',
    'SIGBREAK'
)
