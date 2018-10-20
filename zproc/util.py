import os
import pathlib
import pickle
import signal
import threading
import time
import traceback
import uuid
from typing import Optional, Any

import itsdangerous
import psutil
import zmq

from . import exceptions

ipc_base_dir = pathlib.Path.home() / ".tmp" / "zproc"
if not ipc_base_dir.exists():
    ipc_base_dir.mkdir(parents=True)


class Serializer:
    @staticmethod
    def dumps(obj):
        return pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)

    @staticmethod
    def loads(bytes_obj):
        return handle_remote_exc(pickle.loads(bytes_obj))


def get_signed_serializer(secret_key, *args, **kwargs):
    return itsdangerous.Serializer(secret_key, *args, **kwargs, serializer=Serializer)


def get_serializer(secret_key: Optional[str] = None):
    if secret_key is None:
        return Serializer()

    return get_signed_serializer(secret_key)


def handle_remote_exc(response):
    # if the reply is a remote Exception, re-raise it!
    if isinstance(response, exceptions.RemoteException):
        response.reraise()

    return response


def send(obj: Any, sock: zmq.Socket, serializer):
    return sock.send(serializer.dumps(obj))


def recv(sock: zmq.Socket, serializer, *, silent=True):
    if silent:
        while True:
            try:
                return serializer.loads(sock.recv())
            except itsdangerous.BadSignature:
                continue
    else:
        return serializer.loads(sock.recv())


class SecretKeyHolder:
    def __init__(self, secret_key: Optional[str]) -> None:
        self.secret_key = secret_key

    @property
    def secret_key(self):
        return self._secret_key

    @secret_key.setter
    def secret_key(self, secret_key: Optional[str]):
        self._secret_key = secret_key
        self._serializer = get_serializer(self._secret_key)


def convert_to_exceptions(retry_for):
    if retry_for is not None:
        yield exceptions.SignalException  # catches all signals converted using `signal_to_exception()`

        for i in retry_for:
            if type(i) == signal.Signals:
                exceptions.signal_to_exception(i)
            elif issubclass(i, BaseException):
                yield i
            else:
                raise ValueError(
                    'The items of "retry_for" MUST be a subclass of `BaseException` or of type `signal.Signals`, not `{}`.'.format(
                        repr(i)
                    )
                )


def restore_signal_exception_behavior(e):
    if isinstance(e, exceptions.SignalException):
        signal.signal(e.sig, signal.SIG_DFL)


def bind_to_random_ipc(sock: zmq.Socket) -> str:
    address = "ipc://" + str(ipc_base_dir / str(uuid.uuid1()))
    sock.bind(address)

    return address


def bind_to_random_tcp(sock: zmq.Socket) -> str:
    port = sock.bind_to_random_port("tcp://*")
    address = "tcp://0.0.0.0:{}".format(port)

    return address


def bind_to_random_address(sock: zmq.Socket) -> str:
    try:
        return bind_to_random_ipc(sock)
    except zmq.error.ZMQError:
        return bind_to_random_tcp(sock)


def close_zmq_ctx(ctx: zmq.Context):
    ctx.destroy()
    ctx.term()


def clean_process_tree(*signal_handler_args):
    """Kill all Processes in the current Process tree, recursively."""
    for process in psutil.Process().children(recursive=True):
        os.kill(process.pid, signal.SIGTERM)
        print("Stopped:", process)

    try:
        signum = signal_handler_args[0]
    except IndexError:
        pass
    else:
        os._exit(signum)


def handle_crash(exc, retry_delay, tries, max_tries, process_repr):
    msg = "\nZProc crash report:\n"

    if isinstance(exc, exceptions.SignalException):
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


def is_main_thread():
    return threading.current_thread() == threading.main_thread()


def create_zmq_ctx() -> zmq.Context:
    ctx = zmq.Context()
    ctx.setsockopt(zmq.LINGER, 0)

    return ctx
