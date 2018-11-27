import multiprocessing
import os
from collections import Callable
from typing import Union, Tuple

import zmq

from zproc import util, serializer
from zproc.consts import Msgs, Cmds
from zproc.consts import ServerMeta
from zproc.server.main import main


def start_server(
        server_address: str = None, *, backend: Callable = multiprocessing.Process
) -> Tuple[multiprocessing.Process, str]:
    """
    Start a new zproc server.

    :param server_address:
        .. include:: /api/snippets/server_address.rst
    :param backend:
        .. include:: /api/snippets/backend.rst

    :return: `
        A `tuple``,
        containing a :py:class:`multiprocessing.Process` object for server and the server address.
    """
    recv_conn, send_conn = multiprocessing.Pipe()

    server_process = backend(target=main, args=[server_address, send_conn])
    server_process.start()

    try:
        with recv_conn:
            server_meta: ServerMeta = serializer.loads(recv_conn.recv_bytes())
    except zmq.ZMQError as e:
        if e.errno == 98:
            raise ConnectionError(
                "Encountered - %s. Perhaps the server is already running?" % repr(e)
            )
        if e.errno == 22:
            raise ValueError(
                "Encountered - %s. `server_address` must be a string containing a valid endpoint."
                % repr(e)
            )
        raise

    return server_process, server_meta.state_router


def ping(
        server_address: str, *, timeout: float = None, payload: Union[bytes] = None
) -> int:
    """
    Ping the zproc server.

    This can be used to easily detect if a server is alive and running, with the aid of a suitable ``timeout``.

    :param server_address:
        .. include:: /api/snippets/server_address.rst
    :param timeout:
        The timeout in seconds.

        If this is set to ``None``, then it will block forever, until the zproc server replies.

        For all other values, it will wait for a reply,
        for that amount of time before returning with a :py:class:`TimeoutError`.

        By default it is set to ``None``.
    :param payload:
        payload that will be sent to the server.

        If it is set to None, then ``os.urandom(56)`` (56 random bytes) will be used.

        (No real reason for the ``56`` magic number.)

    :return:
        The zproc server's **pid**.
    """
    if payload is None:
        payload = os.urandom(56)

    with util.create_zmq_ctx() as zmq_ctx:
        with zmq_ctx.socket(zmq.DEALER) as dealer_sock:
            dealer_sock.connect(server_address)
            if timeout is not None:
                dealer_sock.setsockopt(zmq.RCVTIMEO, int(timeout * 1000))

            dealer_sock.send(
                serializer.dumps(
                    {Msgs.cmd: Cmds.ping, Msgs.info: payload}
                )
            )

            try:
                recv_payload, pid = serializer.loads(dealer_sock.recv())
            except zmq.error.Again:
                raise TimeoutError(
                    "Timed-out waiting while for the ZProc server to respond."
                )

            assert (
                    recv_payload == payload
            ), "Payload doesn't match! The server connection may be compromised, or unstable."

            return pid
