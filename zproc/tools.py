import functools
import multiprocessing
import os
import pickle
import types
from typing import Tuple, Union, Callable

import zmq

from zproc import processdef, util
from zproc.server import ServerFn, Msg


def start_server(
    server_address: Union[None, Tuple[str, str]] = None,
    *,
    backend: Callable = multiprocessing.Process
):
    """
    Start a new zproc server.

    :param server_address:
        The zproc server's address.
        (See :ref:`zproc-server-address-spec`)

        If set to ``None``, then a random address will be used.

    :param backend:
        The backend to use for launching the server process.

        For example, you may use ``threading.Thread`` as the backend.

        .. warning::

            Not guaranteed to work well with anything other than ``multiprocessing.Process``.

    :return: ``tuple``, containing a ``multiprocessing.Process`` object for server and the server address.
    """

    if server_address is None:
        recvconn, sendconn = multiprocessing.Pipe()

        server_process = backend(
            target=processdef.server_process, args=(server_address, sendconn)
        )
        server_process.start()

        server_address = recvconn.recv()
        recvconn.close()
    else:
        server_process = backend(
            target=processdef.server_process, args=(server_address,)
        )
        server_process.start()

    return server_process, server_address


def ping(
    server_address: Tuple[str, str],
    *,
    timeout: Union[None, float, int] = None,
    payload: Union[None, bytes] = None
) -> Union[int, None]:
    """
    Ping the zproc server

    :param server_address:
        The zproc server's address.
        (See :ref:`zproc-server-address-spec`)

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
        The zproc server's **PID** if the ping was successful, else ``None``
    """

    if payload is None:
        payload = os.urandom(56)

    ctx = zmq.Context()
    ctx.setsockopt(zmq.LINGER, 0)

    sock = ctx.socket(zmq.DEALER)
    sock.connect(server_address[0])

    if timeout is not None:
        sock.setsockopt(zmq.RCVTIMEO, int(timeout * 1000))

    ping_msg = {Msg.server_fn: ServerFn.ping, Msg.payload: payload}

    sock.send_pyobj(ping_msg, protocol=pickle.HIGHEST_PROTOCOL)

    try:
        response = sock.recv_pyobj()
    except zmq.error.Again:
        raise TimeoutError("Timed-out waiting while for the ZProc server to respond.")
    else:
        if response[Msg.payload] == payload:
            return response["pid"]
        else:
            return None
    finally:
        sock.close()


def atomic(fn: types.FunctionType):
    """
    Wraps a function, to create an atomic operation out of it.

    No Process shall access the state while ``fn`` is running.

    .. note::
        - The first argument to the wrapped function must be a :py:class:`State` object.

        - You might not be able to use global variables inside the atomic function.

          This happens because the atomic wrapped function is serialized.
          To work around this problem, you MUST pass any global variables through the `*args` and `**kwargs`.


    Read :ref:`atomicity`.

    :param fn:
        The ``function`` to be wrapped, as an atomic function.

    :returns:
        A wrapper ``function``.

        The "wrapper" ``function`` returns the value returned by the "wrapped" ``function``.


    .. code-block:: python
        :caption: Example

        import zproc

        @zproc.atomic
        def increment(state):
            return state['count'] += 1

        ctx = zproc.Context()
        ctx.state['count'] = 0

        print(increment(ctx.state))  # 1

    """

    serialized_fn = util.serialize_fn(fn)

    @functools.wraps(fn)
    def wrapper(state, *args, **kwargs):
        return state._req_rep(
            {
                Msg.server_fn: ServerFn.exec_atomic_fn,
                Msg.fn: serialized_fn,
                Msg.args: args,
                Msg.kwargs: kwargs,
            }
        )

    return wrapper
