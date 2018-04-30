import marshal
import queue
from collections import defaultdict
from pathlib import Path
# from time import sleep
from types import FunctionType
from uuid import uuid1

import zmq


class ACTIONS:
    pop = 'pop'
    popitem = 'popitem'
    clear = 'clear'
    update = 'update'
    setdefault = 'setdefault'
    setitem = '__setitem__'
    delitem = '__delitem__'

    get = 'get'
    getitem = '__getitem__'
    contains = '__contains__'
    eq = '__eq__'
    ne = '__ne__'

    get_state = 'get_state'
    stop = 'STOP'

    add_chng_hand = 'ACH'
    add_val_chng_hand = 'AVCH'
    add_cond_hand = 'ACOH'


ACTIONS_THAT_MUTATE = (
    ACTIONS.setitem,
    ACTIONS.delitem,
    ACTIONS.setdefault,
    ACTIONS.pop,
    ACTIONS.popitem,
    ACTIONS.clear,
    ACTIONS.update,
    # ACTIONS.add_val_chng_hand,
    # ACTIONS.add_chng_hand,
    # ACTIONS.add_cond_hand
)


class MSGS:
    ACTION = 'action'
    args = 'args'
    kwargs = 'kwargs'

    testfn = 'callable'

    state_keys = 'state_keys'
    state_key = 'state_key'

    globals = 'globals'


ipc_base_dir = Path.home().joinpath('.tmp')

if not ipc_base_dir.exists():
    ipc_base_dir.mkdir()


def get_random_ipc():
    return get_ipc_path(uuid1())


def get_ipc_path(uuid):
    return 'ipc://' + str(ipc_base_dir.joinpath(str(uuid)))


class Drainer:
    def __init__(self, q):
        self.q = q

    def __iter__(self):
        while True:
            try:
                yield self.q.get_nowait()
            except queue.Empty:  # on python 2 use Queue.Empty
                break


class ZProcServer:
    def __init__(self, ipc_path):
        # Data structures
        self.state = {}

        self.condition_handlers = queue.Queue()
        self.val_change_handlers = defaultdict(queue.Queue)
        self.change_handlers = defaultdict(queue.Queue)

        # init zmq socket
        self.ctx = zmq.Context()
        self.sock = self.ctx.socket(zmq.ROUTER)
        self.sock.bind(ipc_path)

    def pysend(self, ident, msg):
        return self.sock.send_multipart([ident, marshal.dumps(msg)])

    def pyrecv(self):
        ident, msg = self.sock.recv_multipart()
        return ident, marshal.loads(msg)

    def get_state_keys_cmp(self, state_keys):
        return [self.state.get(state_key) for state_key in state_keys]

    # on change handler

    def add_change_handler(self, ident, msg):
        ipc_path = get_random_ipc()
        self.pysend(ident, ipc_path)

        state_keys = msg.get(MSGS.state_keys)

        if len(state_keys):
            self.change_handlers[state_keys].put(
                (ipc_path, self.get_state_keys_cmp(state_keys))
            )
        else:
            self.change_handlers['_any_'].put(
                (ipc_path, self.state)
            )

        self.resolve_change_handlers()

    def resolve_change_handlers(self):
        for state_keys, change_handler_queue in self.change_handlers.items():
            if state_keys == '_any_':
                new = self.state
            else:
                new = self.get_state_keys_cmp(state_keys)

            to_put_back = []

            for ipc_path, old in Drainer(change_handler_queue):
                if old != new:
                    sock = self.ctx.socket(zmq.PUSH)
                    sock.bind(ipc_path)
                    sock.send(marshal.dumps(self.state))
                    sock.close()
                else:
                    to_put_back.append((ipc_path, old))

            for i in to_put_back:
                self.change_handlers[state_keys].put(i)

    # on val change handler

    def add_val_change_handler(self, ident, msg):
        ipc_path = get_random_ipc()
        self.pysend(ident, ipc_path)

        state_key = msg.get(MSGS.state_key)

        self.val_change_handlers[state_key].put(
            (ipc_path, self.state.get(state_key))
        )

        self.resolve_val_change_handlers()

    def resolve_val_change_handlers(self):
        for state_key, handler_list in self.val_change_handlers.items():
            new = self.state.get(state_key)

            to_put_back = []

            for ipc_path, old in Drainer(handler_list):
                if old != new:
                    sock = self.ctx.socket(zmq.PUSH)
                    sock.bind(ipc_path)
                    sock.send(marshal.dumps(self.state.get(state_key)))
                    sock.close()
                else:
                    to_put_back.append((ipc_path, old))

            for i in to_put_back:
                self.change_handlers[state_key].put(i)

    # condition handler

    def add_condition_handler(self, ident, msg):
        ipc_path = get_random_ipc()
        self.pysend(ident, ipc_path)

        self.condition_handlers.put((
            ipc_path,
            FunctionType(msg[MSGS.testfn], globals()),
            msg[MSGS.args],
            msg[MSGS.kwargs]
        ))

        self.resolve_condition_handlers()

    def resolve_condition_handlers(self):
        to_put_back = []
        for ipc_path, test_fn, args, kwargs in Drainer(self.condition_handlers):
            if test_fn(self.state, *args, **kwargs):
                sock = self.ctx.socket(zmq.PUSH)
                sock.bind(ipc_path)
                sock.send(marshal.dumps(self.state))
                sock.close()
            else:
                to_put_back.append((ipc_path, test_fn, args, kwargs))

        for i in to_put_back:
            self.condition_handlers.put(i)

    def resolve_handlers(self):
        self.resolve_change_handlers()
        self.resolve_condition_handlers()
        self.resolve_val_change_handlers()


def state_server(ipc_path):
    # sleep(1)
    server = ZProcServer(ipc_path)
    old_state = server.state.copy()

    # server mainloop
    while True:
        ident, msg = server.pyrecv()
        # print('server', msg, 'from', ident)
        action = msg.get(MSGS.ACTION)

        if action is not None:
            if action == ACTIONS.get_state:
                server.pysend(ident, server.state)
            elif action == ACTIONS.add_val_chng_hand:
                server.add_val_change_handler(ident, msg)
            elif action == ACTIONS.add_cond_hand:
                server.add_condition_handler(ident, msg)
            elif action == ACTIONS.add_chng_hand:
                server.add_change_handler(ident, msg)
            else:
                args, kwargs = msg.get(MSGS.args), msg.get(MSGS.kwargs)
                fn = getattr(server.state, action)

                is_mutable_action = action in ACTIONS_THAT_MUTATE

                if is_mutable_action:
                    old_state = server.state.copy()

                if args is None:
                    if kwargs is None:
                        server.pysend(ident, fn())
                    else:
                        server.pysend(ident, fn(**kwargs))
                else:
                    if kwargs is None:
                        server.pysend(ident, fn(*args))
                    else:
                        server.pysend(ident, fn(*args, **kwargs))

                if is_mutable_action and old_state != server.state:
                    server.resolve_handlers()
