import os
import signal
from collections import defaultdict
from copy import deepcopy
from typing import Any, Dict

import itsdangerous
import zmq
from tblib import pickling_support

from zproc import util, exceptions
from zproc.constants import Msgs, Commands

pickling_support.install()


class Server(util.SecretKeyHolder):
    _active_identity = b""
    _active_namespace = b""
    _active_state = {}  # type:dict

    def __init__(
        self, server_address: str, push_address: str, secret_key: str = None
    ) -> None:
        super().__init__(secret_key)

        self.zmq_ctx = util.create_zmq_ctx()

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

        self.state_store = defaultdict(dict)  # type:Dict[bytes, Dict[Any, Any]]

        self.dispatch_dict = {
            Commands.exec_atomic_fn: self.exec_atomic_fn,
            Commands.exec_dict_method: self.exec_dict_method,
            Commands.get_state: self.send_state,
            Commands.set_state: self.set_state,
            Commands.head: self.head,
            Commands.ping: self.ping,
        }

    def recv(self) -> Dict[Msgs, Any]:
        self._active_identity, msg = self.router_sock.recv_multipart()

        request = self._serializer.loads(msg)
        try:
            self._active_namespace = request[Msgs.namespace]
        except KeyError:
            pass
        self._active_state = self.state_store[self._active_namespace]

        # print(
        #     self._active_identity,
        #     msg,
        #     request,
        #     self._active_namespace,
        #     self._active_state,
        # )
        return request

    def send(self, response):
        """reply with ``response`` to a client (with said ``identity``)"""
        # print("server rep:", self.identity_for_req, response)

        self.router_sock.send_multipart(
            [self._active_identity, self._serializer.dumps(response)]
        )

    def dispatch(self, request):
        # print("dispatch:", request)
        self.dispatch_dict[request[Msgs.cmd]](request)

    def pub_state(self, old_state: dict):
        """Publish the state to everyone"""

        self.pub_sock.send(
            self._active_identity
            + self._active_namespace
            + self._serializer.dumps(
                [old_state, self._active_state, old_state == self._active_state]
            )
        )

    def fn_executor(self, fn):
        """
        Run a function,
        and return the result back to the client with ``identity``.

        Publishes the state if the function executes successfully.
        """
        old_state = deepcopy(self._active_state)
        self.send(fn())
        self.pub_state(old_state)

    def head(self, _):
        self.send((self.pub_sub_address, self.push_pull_address))

    def ping(self, request):
        self.send({Msgs.info: [request[Msgs.info], os.getpid()]})

    def set_state(self, request):
        def _set_state():
            self.state_store[self._active_namespace] = request[Msgs.info]

        self.fn_executor(_set_state)

    def send_state(self, _=None):
        """reply with state to the current client"""
        self.send(self._active_state)

    def exec_dict_method(self, request):
        """Execute a method on the state ``dict`` and reply with the result."""
        state_method_name, args, kwargs = (
            request[Msgs.info],
            request[Msgs.args],
            request[Msgs.kwargs],
        )
        # print(method_name, args, kwargs)
        self.fn_executor(
            lambda: getattr(self._active_state, state_method_name)(*args, **kwargs)
        )

    def exec_atomic_fn(self, _):
        """Execute a function, atomically and reply with the result."""
        self.send(self._active_state)

        old_state = deepcopy(self._active_state)
        new_state = self._serializer.loads(self.pull_sock.recv())

        if new_state is not None:
            self.state_store[self._active_namespace] = self._active_state = new_state

        self.pub_state(old_state)

    def close(self):
        self.router_sock.close()
        self.pub_sock.close()
        util.close_zmq_ctx(self.zmq_ctx)
        os._exit(1)

    def main(self):
        def signal_handler(signum, _):
            self.close()
            print("Stopped server:", os.getpid())
            os._exit(signum)

        signal.signal(signal.SIGTERM, signal_handler)

        while True:
            try:
                self.dispatch(self.recv())
            except itsdangerous.BadSignature:
                pass
            except KeyboardInterrupt:
                self.close()
                raise
            except Exception:
                # proxy the exception back to parent.
                self.send(exceptions.RemoteException())
