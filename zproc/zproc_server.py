import os
import pickle
from typing import Tuple
from uuid import UUID

import zmq
from tblib import pickling_support

from zproc.util import (
    get_ipc_paths_from_uuid,
    Message,
    de_serialize_func,
    RemoteException,
)

pickling_support.install()


class ZProcServer:
    def __init__(self, uuid: UUID):
        self.uuid = uuid
        self.state = {}

        self.server_ipc_path, self.publish_ipc_path = get_ipc_paths_from_uuid(self.uuid)

        self.zmq_ctx = zmq.Context()
        self.zmq_ctx.setsockopt(zmq.LINGER, 0)

        self.server_sock = self.zmq_ctx.socket(zmq.ROUTER)
        self.server_sock.bind(self.server_ipc_path)

        self.publish_sock = self.zmq_ctx.socket(zmq.PUB)
        self.publish_sock.bind(self.publish_ipc_path)

    def wait_for_request(self) -> Tuple[str, dict]:
        """wait for a client to send a request"""

        identity, msg_dict = self.server_sock.recv_multipart()
        return identity, pickle.loads(msg_dict)

    def reply(self, identity, response):
        """reply with response to a client (with said identity)"""

        return self.server_sock.send_multipart(
            [identity, pickle.dumps(response, protocol=pickle.HIGHEST_PROTOCOL)]
        )

    def reply_state(self, identity, *args):
        """reply with state to a client (with said identity)"""

        self.reply(identity, self.state)

    def publish_state_if_change(self, identity, old_state):
        """Publish the state to everyone"""

        if old_state != self.state:
            return self.publish_sock.send_multipart(
                [
                    identity,
                    pickle.dumps(
                        [old_state, self.state], protocol=pickle.HIGHEST_PROTOCOL
                    ),
                ]
            )

    def ping(self, identity, request):

        return self.reply(
            identity, {"pid": os.getpid(), "ping_data": request[Message.ping_data]}
        )

    def _run_function_atomically_and_safely(self, identity, func, args, kwargs):
        old_state = self.state.copy()

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

        method_name = request[Message.method_name]
        state_method = getattr(self.state, method_name)

        return self._run_function_atomically_and_safely(
            identity, state_method, request[Message.args], request[Message.kwargs]
        )

    def run_atomic_function(self, identity: str, msg_dict: dict):
        """Run a function on the state, safely and atomically"""

        func = de_serialize_func(msg_dict[Message.func])
        args = (self.state, *msg_dict[Message.args])

        return self._run_function_atomically_and_safely(
            identity, func, args, msg_dict[Message.kwargs]
        )

    def close(self):
        self.server_sock.close()
        self.publish_sock.close()
        self.zmq_ctx.destroy()
        self.zmq_ctx.term()

    def resend_error_back_to_process(self, identity):
        return self.reply(identity, RemoteException())

    def mainloop(self):
        while True:
            identity, request = self.wait_for_request()
            # print(request, identity)

            try:
                getattr(self, request[Message.server_action])(identity, request)
            except:
                self.resend_error_back_to_process(identity)
