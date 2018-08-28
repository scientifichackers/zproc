import marshal
import os
import pathlib
import signal
import sys
import time
import traceback
import types
import typing
import uuid

import psutil
import zmq

ipc_base_dir = pathlib.Path.home() / ".tmp" / "zproc"
if not ipc_base_dir.exists():
    ipc_base_dir.mkdir(parents=True)


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


def convert_to_exceptions(retry_for):
    yield SignalException  # catches all signals converted using `signal_to_exception()`

    for i in retry_for:
        if type(i) == signal.Signals:
            signal_to_exception(i)
        elif issubclass(i, BaseException):
            yield i
        else:
            raise ValueError(
                'The items of "retry_for" MUST be a subclass of `BaseException` or of type `signal.Signals`, not `{}`.'.format(
                    repr(i)
                )
            )


def restore_signal_exception_behavior(e):
    if isinstance(e, SignalException):
        signal.signal(e.sig, signal.SIG_DFL)


def bind_to_random_address(sock: zmq.Socket) -> str:
    try:
        address = "ipc://" + str(ipc_base_dir / str(uuid.uuid1()))
        sock.bind(address)
    except zmq.error.ZMQError:
        port = sock.bind_to_random_port("tcp://*")
        address = "tcp://127.0.0.1:{}".format(port)
    return address


def serialize_fn(fn: types.FunctionType) -> typing.Tuple[bytes, str]:
    return marshal.dumps(fn.__code__), fn.__name__


def deserialize_fn(serialized_fn: typing.Tuple[bytes, str]) -> types.FunctionType:
    return types.FunctionType(
        marshal.loads(serialized_fn[0]), globals(), serialized_fn[1]
    )


def handle_remote_response(response):
    # if the reply is a remote Exception, re-raise it!
    if isinstance(response, RemoteException):
        response.reraise()
    else:
        return response


def close_zmq_ctx(ctx: zmq.Context):
    ctx.destroy()
    ctx.term()


def clean_process_tree(*signal_handler_args):
    for process in psutil.Process().children(recursive=True):
        os.kill(process.pid, signal.SIGTERM)

    if len(signal_handler_args):
        exitcode = signal_handler_args[0]
    else:
        exitcode = 0
    os._exit(exitcode)


def handle_crash(exc, retry_delay, tries, max_tries, process_repr):
    msg = "\nZProc crash report:\n"

    if isinstance(exc, SignalException):
        msg += "\tSignal - {}\n".format(repr(exc.sig))
    else:
        traceback.print_exc()

    msg += "\t{}\n".format(process_repr)
    msg += "\tTried - {} time(s)\n".format(tries)

    if max_tries is not None and tries >= max_tries:
        msg += "\t**Max tries reached!**\n"
        restore_signal_exception_behavior(exc)
    else:
        msg += "\tNext retry in - {} sec\n".format(retry_delay)
    print(msg)

    time.sleep(retry_delay)


def chunk_gen(it, size, count):
    if it is None:
        return None
    else:
        return [it[i * size : (i + 1) * size] for i in range(count)]
