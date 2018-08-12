import os
import pickle
from typing import Tuple
import uuid
from copy import deepcopy

import zmq
from tblib import pickling_support

from zproc import util

# installs pickle support for exceptions.
pickling_support.install()


class ZProcServer:
    def __init__(self, server_address: Tuple[str, str], address_queue):
        self.state = {}

        self.zmq_ctx = zmq.Context()
        self.zmq_ctx.setsockopt(zmq.LINGER, 0)

        self.req_rep_sock = self.zmq_ctx.socket(zmq.ROUTER)
        self.pub_sub_sock = self.zmq_ctx.socket(zmq.PUB)

        if server_address is None:
            if os.system == "posix":
                base_address = "ipc://" + str(util.ipc_base_dir)
                self.req_rep_address, self.pub_sub_address = (
                    base_address + str(uuid.uuid1()),
                    base_address + str(uuid.uuid1()),
                )

                self.req_rep_sock.bind(self.req_rep_address)
                self.pub_sub_sock.bind(self.pub_sub_address)
            else:
                req_rep_port = self.req_rep_sock.bind_to_random_port("tcp://*")
                pub_sub_port = self.pub_sub_sock.bind_to_random_port("tcp://*")

                self.req_rep_address, self.pub_sub_address = (
                    "tcp://127.0.0.1:{}".format(req_rep_port),
                    "tcp://127.0.0.1:{}".format(pub_sub_port),
                )
        else:
            self.req_rep_address, self.pub_sub_address = server_address

            self.req_rep_sock.bind(self.req_rep_address)
            self.pub_sub_sock.bind(self.pub_sub_address)

        address_queue.put((self.req_rep_address, self.pub_sub_address))

    def _wait_for_request(self) -> Tuple[str, dict]:
        """wait for a client to send a request"""

        identity, msg_dict = self.req_rep_sock.recv_multipart()
        return identity, pickle.loads(msg_dict)

    def _reply(self, identity, response):
        """reply with ``response`` to a client (with said ``identity``)"""

        return self.req_rep_sock.send_multipart(
            [identity, pickle.dumps(response, protocol=pickle.HIGHEST_PROTOCOL)]
        )

    def _reply_exception(self, identity):
        """Serialize the current exception, serialize it, and send it to the client with ``identity``"""

        return self._reply(identity, util.RemoteException())

    def _publish_state_if_changed(self, identity, old_state):
        """Publish the state to everyone"""

        if old_state != self.state:
            return self.pub_sub_sock.send_multipart(
                [
                    identity,
                    pickle.dumps(
                        [old_state, self.state], protocol=pickle.HIGHEST_PROTOCOL
                    ),
                ]
            )

    def _func_executor(self, identity, func, args, kwargs):
        """
        Run a function atomically (sort-of)
        and returns the result back to the client with ``identity``.

        - Restores the state if an error occurs.
        - Publishes the state if it changes after the function executes.
        """

        old_state = deepcopy(self.state)

        try:
            result = func(*args, **kwargs)
        except:
            self.state = old_state  # restore previous state
            self._reply_exception(identity)
        else:
            self._reply(identity, result)
            self._publish_state_if_changed(identity, old_state)

    def ping(self, identity, request):
        return self._reply(
            identity,
            {
                util.Message.pid: os.getpid(),
                util.Message.payload: request[util.Message.payload],
            },
        )

    def reply_state(self, identity, request=None):
        """reply with state to a client (with said ``identity``)"""

        self._reply(identity, self.state)

    def exec_state_method(self, identity, request):
        """Execute a method on the state ``dict`` and reply with the result."""

        method_name, args, kwargs = (
            request[util.Message.dict_method],
            request[util.Message.args],
            request[util.Message.kwargs],
        )

        return self._func_executor(
            identity, getattr(self.state, method_name), args, kwargs
        )

    def exec_atomic_func(self, identity: str, request: dict):
        """Execute a function, atomically  and reply with the result."""

        func, args, kwargs = (
            request[util.Message.func],
            request[util.Message.args],
            request[util.Message.kwargs],
        )

        return self._func_executor(
            identity, util.deserialize_func(func), (self.state, *args), kwargs
        )

    def close(self):
        self.req_rep_sock.close()
        self.pub_sub_sock.close()
        self.zmq_ctx.destroy()
        self.zmq_ctx.term()

    def mainloop(self):
        while True:
            identity, request = self._wait_for_request()
            # print(request, identity)

            try:
                # retrieve the method matching the one in the request,
                # and then call it with appropriate args.
                getattr(self, request[util.Message.server_method])(identity, request)
            except KeyboardInterrupt:
                return self.close()
            except:
                self._reply_exception(identity)
