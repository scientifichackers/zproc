import enum
import os
import signal
from collections import defaultdict
from copy import deepcopy
from typing import Any, Dict

import itsdangerous
import zmq
from tblib import pickling_support

from zproc import util, exceptions

pickling_support.install()


@enum.unique
class Msg(enum.Enum):
    server_fn = 1
    state_method = 2
    args = 3
    kwargs = 4
    fn = 5
    key = 6
    keys = 7
    value = 8
    payload = 9
    pid = 10
    namespace = 11
    address = 12


@enum.unique
class ServerFn(enum.Enum):
    ping = 1
    head = 2
    state_reply = 3
    exec_atomic_fn = 4
    exec_state_method = 5
    set_state = 6


class Server(util.SecretKeyHolder):
    def __init__(
        self, server_address: str, push_address: str, secret_key: str = None
    ) -> None:
        super().__init__(secret_key)

        self.zmq_ctx = zmq.Context()
        self.zmq_ctx.setsockopt(zmq.LINGER, 0)

        self.router_sock = self.zmq_ctx.socket(zmq.ROUTER)
        self.pub_sock = self.zmq_ctx.socket(zmq.PUB)
        self.pull_sock = self.zmq_ctx.socket(zmq.PULL)

        push_sock = self.zmq_ctx.socket(zmq.PUSH)
        push_sock.connect(push_address)

        try:
            if server_address:
                self.req_rep_address = server_address
                self.router_sock.bind(self.req_rep_address)
                if "ipc" in server_address:
                    self.pub_sub_address = util.bind_to_random_ipc(self.pub_sock)
                    self.push_pull_address = util.bind_to_random_ipc(self.pull_sock)
                else:
                    self.pub_sub_address = util.bind_to_random_tcp(self.pub_sock)
                    self.push_pull_address = util.bind_to_random_tcp(self.pull_sock)
            else:
                self.req_rep_address = util.bind_to_random_address(self.router_sock)
                self.pub_sub_address = util.bind_to_random_address(self.pub_sock)
                self.push_pull_address = util.bind_to_random_address(self.pull_sock)
        except Exception:
            push_sock.send(self._serializer.dumps(exceptions.RemoteException()))
            self.close()
        else:
            push_sock.send(self._serializer.dumps(self.req_rep_address))
        finally:
            push_sock.close()

        # see State._get_subscribe_sock() for more
        self.pub_sock.setsockopt(zmq.INVERT_MATCHING, 1)

        self.state_namespace = defaultdict(dict)  # type:Dict[bytes, Dict[Any, Any]]
        self.dispatch_dict = {i: getattr(self, i.name) for i in ServerFn}

    def wait_for_req(self) -> Dict[Msg, Any]:
        """wait for a client to send a request"""

        identity, msg = self.router_sock.recv_multipart()
        # print("server:", identity, request)

        self.identity_for_req = identity

        request = self._serializer.loads(msg)
        if request[Msg.server_fn] not in (ServerFn.ping, ServerFn.head):
            self.namespace_for_req = request[Msg.namespace]
            self.state_for_req = self.state_namespace[self.namespace_for_req]

        return request

    def pub_state(self, old_state: dict):
        """Publish the state to everyone"""

        self.pub_sock.send(
            self.identity_for_req
            + self.namespace_for_req
            + self._serializer.dumps(
                [old_state, self.state_for_req, old_state == self.state_for_req]
            )
        )

    def reply(self, response):
        """reply with ``response`` to a client (with said ``identity``)"""

        # print("server rep:", self.identity_for_req, response)

        self.router_sock.send_multipart(
            [self.identity_for_req, self._serializer.dumps(response)]
        )

    def fn_executor(self, fn):
        """
        Run a function,
        and return the result back to the client with ``identity``.

        Publishes the state if the function executes successfully.
        """

        old_state = deepcopy(self.state_for_req)
        # print(fn, args, kwargs)

        result = fn()

        self.reply(result)
        self.pub_state(old_state)

    def head(self, _):
        self.reply((self.pub_sub_address, self.push_pull_address))

    def ping(self, request):
        self.reply({Msg.pid: os.getpid(), Msg.payload: request[Msg.payload]})

    def set_state(self, request):
        def _set_state():
            self.state_namespace[self.namespace_for_req] = request[Msg.value]

        self.fn_executor(_set_state)

    def state_reply(self, _=None):
        """reply with state to the current client"""

        self.reply(self.state_for_req)

    def exec_state_method(self, request):
        """Execute a method on the state ``dict`` and reply with the result."""

        state_method_name, args, kwargs = (
            request[Msg.state_method],
            request[Msg.args],
            request[Msg.kwargs],
        )
        # print(method_name, args, kwargs)
        self.fn_executor(
            lambda: getattr(self.state_for_req, state_method_name)(*args, **kwargs)
        )

    def exec_atomic_fn(self, _):
        """Execute a function, atomically and reply with the result."""

        self.reply(self.state_for_req)

        old_state = deepcopy(self.state_for_req)
        new_state = self._serializer.loads(self.pull_sock.recv())

        if new_state is not None:
            self.state_namespace[
                self.namespace_for_req
            ] = self.state_for_req = new_state

        self.pub_state(old_state)

    def close(self):
        self.router_sock.close()
        self.pub_sock.close()
        util.close_zmq_ctx(self.zmq_ctx)
        os._exit(1)

    def dispatch(self, request):
        # print("dispatch:", request)
        self.dispatch_dict[request[Msg.server_fn]](request)

    def main(self):
        def signal_handler(*args):
            self.close()

        signal.signal(signal.SIGTERM, signal_handler)

        while True:
            try:
                self.dispatch(self.wait_for_req())
            except itsdangerous.BadSignature:
                pass
            except KeyboardInterrupt:
                self.close()
                raise
            except Exception:
                # proxy the exception back to parent.
                self.reply(exceptions.RemoteException())
