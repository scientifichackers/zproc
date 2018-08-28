import multiprocessing
import os
import pickle
from copy import deepcopy
from typing import Tuple

import zmq
from tblib import pickling_support

from zproc import util

# installs pickle-ing support for exceptions.
pickling_support.install()


class Server:
    def __init__(
        self,
        server_address: Tuple[str, str] = None,
        sendconn: multiprocessing.Pipe = None,
    ):
        self.state = {}

        self._zmq_ctx = zmq.Context()
        self._zmq_ctx.setsockopt(zmq.LINGER, 0)

        self._router_sock = self._zmq_ctx.socket(zmq.ROUTER)
        self._pub_sock = self._zmq_ctx.socket(zmq.PUB)

        if server_address is None:
            req_rep_address = util.bind_to_random_address(self._router_sock)
            pub_sub_address = util.bind_to_random_address(self._pub_sock)

            sendconn.send((req_rep_address, pub_sub_address))
            sendconn.close()
        else:
            self._router_sock.bind(server_address[0])
            self._pub_sock.bind(server_address[1])

        # see State._get_subscribe_sock() for more
        self._pub_sock.setsockopt(zmq.INVERT_MATCHING, 1)

    def _wait_for_request(self) -> Tuple[str, dict]:
        """wait for a client to send a request"""

        identity, msg_dict = self._router_sock.recv_multipart()
        return identity, pickle.loads(msg_dict)

    def _reply(self, identity, response):
        """reply with ``response`` to a client (with said ``identity``)"""

        return self._router_sock.send_multipart(
            [identity, pickle.dumps(response, protocol=pickle.HIGHEST_PROTOCOL)]
        )

    def _exception_reply(self, identity):
        """
        Retrieve the current exception,
        serialize it, and send it to the client with said ``identity``
        """

        return self._reply(identity, util.RemoteException())

    def _pub_state_if_changed(self, identity: bytes, old_state: dict):
        """Publish the state to everyone"""

        if old_state != self.state:
            return self._pub_sock.send(
                identity
                + pickle.dumps(
                    [old_state, self.state], protocol=pickle.HIGHEST_PROTOCOL
                )
            )

    def _fn_executor(self, identity, fn, args, kwargs):
        """
        Run a function atomically (sort-of)
        and returns the result back to the client with ``identity``.

        - Restores the state if an error occurs.
        - Publishes the state if it changes after the function executes.
        """

        old_state = deepcopy(self.state)
        # print(fn, args, kwargs)
        try:
            result = fn(*args, **kwargs)
        except:
            self.state = old_state  # restore previous state
            self._exception_reply(identity)
        else:
            self._reply(identity, result)
            self._pub_state_if_changed(identity, old_state)

    def ping(self, identity, request):
        return self._reply(
            identity, {Msg.pid: os.getpid(), Msg.payload: request[Msg.payload]}
        )

    def state_reply(self, identity, request=None):
        """reply with state to a client (with said ``identity``)"""

        self._reply(identity, self.state)

    def exec_state_method(self, identity, request):
        """Execute a method on the state ``dict`` and reply with the result."""

        state_method_name, args, kwargs = (
            request[Msg.state_method],
            request[Msg.args],
            request[Msg.kwargs],
        )
        # print(method_name, args, kwargs)
        return self._fn_executor(
            identity, getattr(self.state, state_method_name), args, kwargs
        )

    def exec_atomic_fn(self, identity: str, request: dict):
        """Execute a function, atomically  and reply with the result."""

        fn, args, kwargs = (request[Msg.fn], request[Msg.args], request[Msg.kwargs])

        return self._fn_executor(
            identity, util.deserialize_fn(fn), (self.state, *args), kwargs
        )

    def close(self):
        self._router_sock.close()
        self._pub_sock.close()
        util.close_zmq_ctx(self._zmq_ctx)

    def mainloop(self):
        while True:
            identity, request = self._wait_for_request()
            # print(request, identity)

            try:
                # retrieve the method matching the one in the request,
                # and then call it with appropriate args.
                getattr(self, request[Msg.server_fn])(identity, request)
            except KeyboardInterrupt:
                return self.close()
            except:
                # proxy the exception back to parent.
                self._exception_reply(identity)


# Here are some static declarations.
# They are here to prevent typos, while constructing messages.
#
# Could've been a dict, but my IDE doesn't seem to detect and refactor changes in dict keys.


class Msg:
    server_fn = 0
    state_method = 1
    args = 2
    kwargs = 3
    fn = 4
    key = 5
    keys = 6
    value = 7
    payload = 8
    pid = 9


class ServerFn:
    ping = Server.ping.__name__
    state_reply = Server.state_reply.__name__
    exec_atomic_fn = Server.exec_atomic_fn.__name__
    exec_state_method = Server.exec_state_method.__name__
