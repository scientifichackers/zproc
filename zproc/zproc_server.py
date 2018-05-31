import pickle
from typing import Tuple
from uuid import UUID

import zmq
from tblib import pickling_support

from zproc.utils import get_ipc_paths, Message, DICT_MUTABLE_ACTIONS, de_serialize_func, RemoteException

pickling_support.install()


class ZProcServer:
    def __init__(self, uuid: UUID):
        self.uuid = uuid
        self.state = {}

        self.server_ipc_path, self.bcast_ipc_path = get_ipc_paths(self.uuid)

        self.zmq_ctx = zmq.Context()

        self.server_sock = self.zmq_ctx.socket(zmq.ROUTER)
        self.server_sock.bind(self.server_ipc_path)

        self.pub_sock = self.zmq_ctx.socket(zmq.PUB)
        self.pub_sock.bind(self.bcast_ipc_path)

    def wait_req(self) -> Tuple[str, dict]:
        """wait for a client to send a request"""

        ident, msg_dict = self.server_sock.recv_multipart()
        return ident, pickle.loads(msg_dict)

    def reply(self, ident, response):
        """reply with response to a client (with said identity)"""

        return self.server_sock.send_multipart([ident, pickle.dumps(response, protocol=pickle.HIGHEST_PROTOCOL)])

    def reply_state(self, ident, *args):
        """reply with state to a client (with said identity)"""

        self.reply(ident, self.state)

    def publish_state(self, ident, old):
        """Publish the state to everyone"""

        return self.pub_sock.send_multipart([
            ident,
            pickle.dumps([old, self.state], protocol=pickle.HIGHEST_PROTOCOL)
        ])

    def state_method(self, ident, request):
        """Call a method on the state dict and return the result."""

        method_name = request[Message.method_name]

        can_mutate = method_name in DICT_MUTABLE_ACTIONS
        if can_mutate:
            old = self.state.copy()

        state_method = getattr(self.state, method_name)
        result = state_method(*request[Message.args], **request[Message.kwargs])

        self.reply(ident, result)

        if can_mutate and old != self.state:
            self.publish_state(ident, old)

    def state_func(self, ident: str, msg_dict: dict):
        """Run a function on the state"""

        old = self.state.copy()

        func = de_serialize_func(msg_dict[Message.func])
        result = func(self.state, *msg_dict[Message.args], **msg_dict[Message.kwargs])

        self.reply(ident, result)

        if old != self.state:
            self.publish_state(ident, old)


def zproc_server_proc(uuid: UUID):
    server = ZProcServer(uuid)

    # server mainloop
    while True:
        ident, request = server.wait_req()
        # print(request, ident)
        try:
            getattr(server, request[Message.server_action])(ident, request)
        except Exception:
            server.reply(ident, RemoteException())
