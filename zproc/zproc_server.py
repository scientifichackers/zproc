import os
import pickle
import typing
import uuid
from copy import deepcopy

import zmq
from tblib import pickling_support

from zproc import util

pickling_support.install()


class ZProcServer:
    def __init__(self, server_address, address_queue):
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

    def wait_for_request(self) -> typing.Tuple[str, dict]:
        """wait for a client to send a request"""

        identity, msg_dict = self.req_rep_sock.recv_multipart()
        return identity, pickle.loads(msg_dict)

    def reply(self, identity, response):
        """reply with response to a client (with said identity)"""

        return self.req_rep_sock.send_multipart(
            [identity, pickle.dumps(response, protocol=pickle.HIGHEST_PROTOCOL)]
        )

    def reply_state(self, identity, *args):
        """reply with state to a client (with said identity)"""

        self.reply(identity, self.state)

    def publish_state_if_change(self, identity, old_state):
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

    def ping(self, identity, request):
        return self.reply(
            identity,
            {
                util.Message.pid: os.getpid(),
                util.Message.payload: request[util.Message.payload],
            },
        )

    def _run_function_atomically_and_safely(self, identity, func, args, kwargs):
        old_state = deepcopy(self.state)

        try:
            result = func(*args, **kwargs)
        except:
            self.state = old_state  # restore previous state
            self.resend_error_back_to_process(identity)
        else:
            self.reply(identity, result)
            self.publish_state_if_change(identity, old_state)

    def call_method_on_state(self, identity, request):
        """Call a method on the state dict and return the result."""

        method_name = request[util.Message.dict_method]
        state_method = getattr(self.state, method_name)

        return self._run_function_atomically_and_safely(
            identity,
            state_method,
            request[util.Message.args],
            request[util.Message.kwargs],
        )

    def run_atomic_function(self, identity: str, msg_dict: dict):
        """Run a function on the state, safely and atomically"""

        func = util.deserialize_func(msg_dict[util.Message.func])
        args = (self.state, *msg_dict[util.Message.args])

        return self._run_function_atomically_and_safely(
            identity, func, args, msg_dict[util.Message.kwargs]
        )

    def close(self):
        self.req_rep_sock.close()
        self.pub_sub_sock.close()
        self.zmq_ctx.destroy()
        self.zmq_ctx.term()

    def resend_error_back_to_process(self, identity):
        return self.reply(identity, util.RemoteException())

    def mainloop(self):
        while True:
            identity, request = self.wait_for_request()
            # print(request, identity)

            try:
                getattr(self, request[util.Message.server_method])(identity, request)
            except KeyboardInterrupt:
                return self.close()
            except:
                self.resend_error_back_to_process(identity)
