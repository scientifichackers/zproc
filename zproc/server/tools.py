import multiprocessing
import os
from collections import Callable
from typing import Union, Optional, Tuple

import zmq

from zproc import util
from zproc.consts import Msgs, Commands
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
        server_meta: ServerMeta = util.loads(recv_conn.recv_bytes())
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
    finally:
        recv_conn.close()

    return server_process, server_meta.server_address


def ping(
    server_address: str,
    *,
    timeout: float = None,
    send_payload: Union[bytes] = None
) -> Optional[int]:
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
    :param send_payload:
        payload that will be sent to the server.

        If it is set to None, then ``os.urandom(56)`` (56 random bytes) will be used.

        (No real reason for the ``56`` magic number.)

    :return:
        The zproc server's **pid** if the ping was successful, else ``None``

        If this returns ``None``,
        then it probably means there is some fault in communication with the server.
    """
    if send_payload is None:
        send_payload = os.urandom(56)

    with util.create_zmq_ctx() as zmq_ctx:
        with zmq_ctx.socket(zmq.DEALER) as dealer_sock:
            dealer_sock.connect(server_address)
            if timeout is not None:
                dealer_sock.setsockopt(zmq.RCVTIMEO, int(timeout * 1000))

            dealer_sock.send(
                util.dumps(
                    {
                        Msgs.cmd: Commands.ping,
                        Msgs.info: send_payload,
                        Msgs.namespace: b"",
                    }
                )
            )

            try:
                response = util.loads(dealer_sock.recv())
            except zmq.error.Again:
                raise TimeoutError(
                    "Timed-out waiting while for the ZProc server to respond."
                )

            recv_payload, pid = response[Msgs.info]
            if recv_payload == send_payload:
                return pid
            else:
                return None
