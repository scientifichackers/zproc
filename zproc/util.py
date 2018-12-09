import os
import pathlib
import signal
import struct
import threading
import time
import uuid
from collections import deque
from contextlib import suppress, contextmanager, ExitStack
from itertools import islice
from textwrap import indent
from traceback import format_exc
from typing import Union, Iterable, Generator, Callable, Tuple, Sequence, Optional, Type

import psutil
import zmq

from zproc import exceptions
from zproc import serializer
from zproc.__version__ import __version__
from zproc.consts import (
    Msgs,
    Cmds,
    ServerMeta,
    DEFAULT_NAMESPACE,
    TASK_NONCE_LENGTH,
    TASK_INFO_FMT,
    CHUNK_INFO_FMT,
    TASK_ID_LENGTH,
)

IPC_BASE_DIR = pathlib.Path.home() / ".tmp" / "zproc"
if not IPC_BASE_DIR.exists():
    IPC_BASE_DIR.mkdir(parents=True)


def create_ipc_address(name: str) -> str:
    return "ipc://" + str(IPC_BASE_DIR / name)


def get_server_meta(zmq_ctx: zmq.Context, server_address: str) -> ServerMeta:
    with zmq_ctx.socket(zmq.DEALER) as dealer:
        dealer.connect(server_address)
        return req_server_meta(dealer)


_server_meta_req_cache = serializer.dumps(
    {Msgs.cmd: Cmds.get_server_meta, Msgs.namespace: DEFAULT_NAMESPACE}
)


def req_server_meta(dealer: zmq.Socket) -> ServerMeta:
    dealer.send(_server_meta_req_cache)
    server_meta = serializer.loads(dealer.recv())
    if server_meta.version != __version__:
        raise RuntimeError(
            "The server version didn't match. "
            "Please make sure the server (%r) is using the same version of ZProc as this client (%r)."
            % (server_meta.version, __version__)
        )
    return server_meta


def to_catchable_exc(
    retry_for: Iterable[Union[signal.Signals, Type[BaseException]]]
) -> Generator[Type[BaseException], None, None]:
    if retry_for is None:
        return

    # catches all signals converted using `signal_to_exception()`
    yield exceptions.SignalException

    for e in retry_for:
        if isinstance(e, signal.Signals):
            exceptions.signal_to_exception(e)
        elif issubclass(e, BaseException):
            yield e
        else:
            raise ValueError(
                "The items of `retry_for` must either be a sub-class of `BaseException`, "
                f"or an instance of `signal.Signals`. Not `{e!r}`."
            )


def bind_to_random_ipc(sock: zmq.Socket) -> str:
    address = "ipc://" + str(IPC_BASE_DIR / str(uuid.uuid1()))
    sock.bind(address)
    return address


def bind_to_random_tcp(sock: zmq.Socket) -> str:
    port = sock.bind_to_random_port("tcp://*")
    address = "tcp://0.0.0.0:%d" % port
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
    """Stop all Processes in the current Process tree, recursively."""
    parent = psutil.Process()
    procs = parent.children(recursive=True)
    if procs:
        print(f"[ZProc] Cleaning up {parent.name()!r} ({os.getpid()})...")

    for p in procs:
        with suppress(psutil.NoSuchProcess):
            p.terminate()
    _, alive = psutil.wait_procs(procs, timeout=0.5)  # 0.5 seems to work
    for p in alive:
        with suppress(psutil.NoSuchProcess):
            p.kill()

    try:
        signum = signal_handler_args[0]
    except IndexError:
        pass
    else:
        os._exit(signum)


def make_chunks(seq: Optional[Sequence], length: int, num_chunks: int):
    if seq is None:
        return [None] * num_chunks
    else:
        return [seq[i * length : (i + 1) * length] for i in range(num_chunks)]


def is_main_thread() -> bool:
    return threading.current_thread() == threading.main_thread()


def create_zmq_ctx(*, linger=False) -> zmq.Context:
    ctx = zmq.Context()
    if not linger:
        ctx.setsockopt(zmq.LINGER, 0)
    return ctx


def enclose_in_brackets(s: str) -> str:
    return f"<{s}>"


def callable_repr(c: Callable) -> str:
    return repr(c.__module__ + "." + c.__qualname__)


def generate_task_id(task_info: Tuple[int, int, int] = None) -> bytes:
    nonce = os.urandom(TASK_NONCE_LENGTH)
    if task_info is None:
        return nonce
    return nonce + struct.pack(TASK_INFO_FMT, *task_info)


def deconstruct_task_id(task_id: bytes) -> Optional[tuple]:
    if len(task_id) == TASK_NONCE_LENGTH:
        return None

    return struct.unpack(TASK_INFO_FMT, task_id[TASK_NONCE_LENGTH:])


def encode_chunk_id(task_id: bytes, index: int) -> bytes:
    return task_id + struct.pack(CHUNK_INFO_FMT, index)


def decode_chunk_id(chunk: bytes) -> Tuple[bytes, int]:
    return (
        chunk[:TASK_ID_LENGTH],
        struct.unpack(CHUNK_INFO_FMT, chunk[TASK_ID_LENGTH:])[0],
    )


def log_internal_crash(subsystem: str):
    basic_info = f"subsystem: {subsystem!r}\npid: {os.getpid()}"
    report = "\n\n".join((basic_info, format_exc()))
    report = indent(report, " " * 2)
    print(f"\n[ZProc] Internal crash report:\n{report}")


@contextmanager
def socket_factory(*sock_types):
    with ExitStack() as stack:
        ctx = stack.enter_context(zmq.Context())
        sockets = (stack.enter_context(ctx.socket(i)) for i in sock_types)
        yield (ctx, *sockets)


@contextmanager
def perf_counter():
    s = time.perf_counter()
    e = time.perf_counter()
    fr = e - s
    s = time.perf_counter()
    yield
    e = time.perf_counter()
    print((e - s), (e - s) / fr)


def consume(iterator, n=None):
    """Advance the iterator n-steps ahead. If n is None, consume entirely."""
    # Use functions that consume iterators at C speed.
    if n is None:
        # feed the entire iterator into a zero-length deque
        deque(iterator, maxlen=0)
    else:
        # advance to the empty slice starting at position n
        next(islice(iterator, n, n), None)


def strict_request_reply(msg, send: Callable, recv: Callable):
    """
    Ensures a strict req-reply loop,
    so that clients dont't receive out-of-order messages,
    if an exception occurs between request-reply.
    """
    try:
        send(msg)
    except Exception:
        raise
    try:
        return recv()
    except Exception:
        with suppress(zmq.error.Again):
            recv()
        raise
