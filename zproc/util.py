import inspect
import marshal
import os
import signal
import sys
import traceback
import types
from collections import deque
from pathlib import Path

import psutil
from time import sleep


ipc_base_dir = Path.home().joinpath(".tmp")

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
        super().__init__("")
        self.sig = sig
        self.frame = frame


def signal_to_exception(sig):
    """Convert a signal to :py:exc:`SignalException`"""

    def handler(sig, frame):
        raise SignalException(sig, frame)

    signal.signal(sig, handler)


def restore_signal_exception_behavior(e):
    if isinstance(e, SignalException):
        signal.signal(e.sig, signal.SIG_DFL)


def serialize_func(fn):
    return (marshal.dumps(fn.__code__), fn.__name__)


def deserialize_func(serialized_fn):
    return types.FunctionType(
        marshal.loads(serialized_fn[0]), globals(), serialized_fn[1]
    )


def handle_server_response(response):
    # if the reply is a remote Exception, re-raise it!
    if isinstance(response, RemoteException):
        response.reraise()
    else:
        return response


def cleanup_current_process_tree(*signal_handler_args):
    procs = psutil.Process().children(recursive=True)

    for proc in procs:
        os.kill(proc.pid, signal.SIGTERM)

    if len(signal_handler_args):
        os._exit(signal_handler_args[0])
    else:
        os._exit(0)


def get_kwargs_for_function(fn, state, props, proc):
    target_function_parameters = inspect.signature(fn).parameters.copy()

    if "kwargs" in target_function_parameters:
        kwargs = {"state": state, "props": props, "proc": proc}
    else:
        kwargs = {}
        if "state" in target_function_parameters:
            kwargs["state"] = state
        if "props" in target_function_parameters:
            kwargs["props"] = props
        if "proc" in target_function_parameters:
            kwargs["proc"] = proc

    return kwargs


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


def handle_crash(*, process, exc, retry_delay, tries, max_tries):
    msg = "\nZProc crash report:\n"

    if isinstance(exc, SignalException):
        msg += "\tSignal - {}\n".format(repr(exc.sig))
    else:
        traceback.print_exc()

    msg += "\t{}\n".format(process)
    msg += "\tTried - {} time(s)\n".format(tries)

    if max_tries is not None and tries >= max_tries:
        msg += "\t**Max tries reached!**\n"
        restore_signal_exception_behavior(exc)
    else:
        msg += "\tNext retry in - {} sec\n".format(retry_delay)

    print(msg)
    sleep(process.kwargs["retry_delay"])


# static declarations

STATE_DICT_LIKE_METHODS = {
    "__contains__",
    "__delitem__",
    "__eq__",
    "__getitem__",
    "__iter__",
    "__len__",
    "__ne__",
    "__setitem__",
    "clear",
    "copy",
    "fromkeys",
    "get",
    "items",
    "keys",
    "pop",
    "popitem",
    "setdefault",
    "update",
    "values",
}

STATE_INJECTED_METHODS = set(STATE_DICT_LIKE_METHODS) - {
    "__copy__",
    "items",
    "keys",
    "values",
}


class Message:
    server_method = "server"
    dict_method = "dict"

    args = "args"
    kwargs = "kwargs"

    func = "fn"

    key = "key"
    keys = "keys"
    value = "value"

    payload = "load"
    pid = "pid"


WINDOWS_SIGNALS = (
    "SIGABRT",
    "SIGFPE",
    "SIGILL",
    "SIGINT",
    "SIGSEGV",
    "SIGTERM",
    "SIGBREAK",
)
