import multiprocessing
import os
from typing import Union, Callable, Optional

import zmq

from zproc import util
from zproc.server import ServerFn, Msg, Server


def start_server(
    server_address: str = None,
    *,
    backend: Callable = multiprocessing.Process,
    secret_key: str = None
):
    """
    Start a new zproc server.

    :param server_address:
        The zproc server's address.

        If it is set to ``None``, then a random address will be generated.

        Please read :ref:`server-address-spec` for a detailed explanation.


    :param backend:
        The backend to use for launching the server process.

        For example, you may use ``threading.Thread`` as the backend.

        .. warning::

            Not guaranteed to work well with anything other than ``multiprocessing.Process``.

    :return: ``tuple``, containing a ``multiprocessing.Process`` object for server and the server address.
    """

    ctx = zmq.Context()
    ctx.setsockopt(zmq.LINGER, 0)
    sock = ctx.socket(zmq.PULL)
    pull_address = util.bind_to_random_address(sock)

    serializer = util.get_serializer(secret_key)

    server_process = backend(
        target=lambda *args, **kwargs: Server(*args, **kwargs).main(),
        args=[server_address, pull_address, secret_key],
        daemon=True,
    )
    server_process.start()

    try:
        server_address = util.recv(sock, serializer)
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
        sock.close()
        util.close_zmq_ctx(ctx)

    return server_process, server_address


def ping(
    server_address: str,
    *,
    timeout: Optional[Union[float, int]] = None,
    payload: Optional[Union[bytes]] = None,
    secret_key: str = None
) -> Optional[int]:
    """
    Ping the zproc server

    :param server_address:
        The zproc server's address.

        Please read :ref:`server-address-spec` for a detailed explanation.

    :param timeout:
        The timeout in seconds.

        If this is set to ``None``, then it will block forever, until the zproc server replies.

        For all other values, it will wait for a reply,
        for that amount of time before returning with a ``TimeoutError``.

        By default it is set to ``None``.

    :param payload:
        payload that will be sent to the server.

        If it is set to None, then ``os.urandom(56)`` (56 random bytes) will be used.

        (No real reason for the ``56`` magic number.)

    :return:
        The zproc server's **pid** if the ping was successful, else ``None``

        If this returns ``None``,
        then it probably means there is some fault in communication with the server.
    """

    if payload is None:
        payload = os.urandom(56)

    serializer = util.get_serializer(secret_key)

    ctx = zmq.Context()
    ctx.setsockopt(zmq.LINGER, 0)

    sock = ctx.socket(zmq.DEALER)
    sock.connect(server_address)

    if timeout is not None:
        sock.setsockopt(zmq.RCVTIMEO, int(timeout * 1000))

    sock.send(serializer.dumps({Msg.server_fn: ServerFn.ping, Msg.payload: payload}))

    try:
        response = util.handle_remote_exc(serializer.loads(sock.recv()))
    except zmq.error.Again:
        raise TimeoutError("Timed-out waiting while for the ZProc server to respond.")
    else:
        if response[Msg.payload] == payload:
            return response[Msg.pid]
        else:
            return None
    finally:
        sock.close()
