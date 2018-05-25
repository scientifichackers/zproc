import pickle
import sys
from collections import defaultdict

import zmq
from tblib import pickling_support
from time import sleep

from zproc.utils import *

pickling_support.install()


class ZProcServerException:
    def __init__(self):
        self.exc = sys.exc_info()

    def reraise(self):
        raise self.exc[0].with_traceback(self.exc[1], self.exc[2])

    def __str__(self):
        return str(self.exc)


class ZProcServer:
    def __init__(self, bind_ipc_path):
        self.state = {}

        self.state_lock_ident = None

        self.condition_handlers = Queue()
        self.equals_handlers = Queue()
        self.val_change_handlers = defaultdict(Queue)
        self.change_handlers = defaultdict(Queue)

        # init zmq socket
        self.ctx = zmq.Context()
        self.sock = self.ctx.socket(zmq.ROUTER)
        self.sock.bind(bind_ipc_path)

    def wait_req(self):
        """wait for client to send a request"""
        ident, msg = self.sock.recv_multipart()
        return ident, pickle.loads(msg)

    def reply(self, ident, msg):
        """reply to a client (with said identity) and msg"""
        return self.sock.send_multipart([ident, pickle.dumps(msg, protocol=pickle.HIGHEST_PROTOCOL)])

    def push(self, ipc_path, msg):
        """push to an ipc_path, the given msg"""
        sock = self.ctx.socket(zmq.PUSH)
        sock.bind(ipc_path)
        sock.send_pyobj(msg, protocol=pickle.HIGHEST_PROTOCOL)
        sock.close()

    def get_values_for_keys(self, state_keys):
        """Get a list of values, given some keys in the state"""

        return tuple(self.state.get(state_key) for state_key in state_keys)

    def send_state(self, ident, msg=None):
        """Sends the state back to a process"""
        self.reply(ident, self.state)

    def state_rpc(self, ident, msg):
        func_name = msg[Message.func_name]

        can_mutate = func_name in DICT_MUTABLE_ACTIONS
        if can_mutate:
            old = self.state.copy()
        else:
            old = None

        state_func = getattr(self.state, func_name)
        result = state_func(*msg[Message.args], **msg[Message.kwargs])
        self.reply(ident, result)

        if can_mutate and old != self.state:
            self.resolve_all_handlers()

    def rpc(self, ident, msg):
        self.reply(ident, de_serialize_func(msg[Message.func])(self.state, *msg[Message.args], **msg[Message.kwargs]))

    def process_msg(self, ident, msg):
        """Process a message, and then reply to client with the result"""

        return getattr(self, msg[Message.method_name])(ident, msg)

    # on change handlers

    def register_get_when_change(self, ident, msg):
        ipc_path = get_random_ipc()
        self.reply(ident, ipc_path)

        keys = msg[Message.keys]

        if len(keys):
            self.change_handlers[keys].enqueue(
                (ipc_path, self.get_values_for_keys(keys))
            )
        else:
            self.change_handlers['_any_'].enqueue(
                (ipc_path, self.state.copy())
            )

        self.resolve_get_when_change()

    def resolve_get_when_change(self):
        for keys, change_handler_queue in self.change_handlers.items():
            only_one = False
            if keys == '_any_':
                new = self.state
            else:
                new = self.get_values_for_keys(keys)
                only_one = len(new) == 1

            for ipc_path, old in change_handler_queue.drain():
                if old != new:
                    self.push(ipc_path, new[0] if only_one else new)
                else:
                    change_handler_queue.enqueue((ipc_path, old))

    # on equal handlers

    def register_get_when_equal(self, ident, msg):
        ipc_path = get_random_ipc()
        self.reply(ident, ipc_path)

        self.equals_handlers.enqueue(
            (msg[Message.key], msg[Message.value], ipc_path, True)
        )

        self.resolve_get_when_equal_or_not()

    def register_get_when_not_equal(self, ident, msg):
        ipc_path = get_random_ipc()
        self.reply(ident, ipc_path)

        self.equals_handlers.enqueue(
            (msg[Message.key], msg[Message.value], ipc_path, False)
        )

        self.resolve_get_when_equal_or_not()

    def resolve_get_when_equal_or_not(self):
        for key, value, ipc_path, should_be_equal in self.equals_handlers.drain():
            if should_be_equal:
                if self.state.get(key) == value:
                    self.push(ipc_path, True)
                else:
                    self.equals_handlers.enqueue((key, value, ipc_path, True))
            else:
                if self.state.get(key) != value:
                    self.push(ipc_path, value)
                else:
                    self.equals_handlers.enqueue((key, value, ipc_path, False))

    # condition handlers

    def register_get_when(self, ident, msg):
        ipc_path = get_random_ipc()
        self.reply(ident, ipc_path)

        self.condition_handlers.enqueue((
            ipc_path,
            de_serialize_func(msg[Message.func]),
            msg[Message.args],
            msg[Message.kwargs]
        ))

        self.resolve_get_when()

    def resolve_get_when(self):
        for ipc_path, test_fn, args, kwargs in self.condition_handlers.drain():
            if test_fn(self.state, *args, **kwargs):
                self.push(ipc_path, self.state)
            else:
                self.condition_handlers.enqueue((ipc_path, test_fn, args, kwargs))

    def resolve_all_handlers(self):
        self.resolve_get_when_change()
        self.resolve_get_when()
        self.resolve_get_when_equal_or_not()


def state_server(bind_ipc_path: str):
    server = ZProcServer(bind_ipc_path)

    # server mainloop
    while True:
        ident, msg = server.wait_req()
        # print(msg, ident)
        try:
            server.process_msg(ident, msg)
        except Exception:
            server.reply(ident, ZProcServerException())


def keep_alive_daemon(ctx, sleep_time: float):
    while True:
        ctx.start_all()
        sleep(sleep_time)
