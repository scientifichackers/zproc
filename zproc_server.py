import marshal
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


ipc_base_dir = Path.home().joinpath('.tmp')

if not ipc_base_dir.exists():
    ipc_base_dir.mkdir()


def get_random_ipc():
    return get_ipc_path(uuid1())


def get_ipc_path(uuid):
    return 'ipc://' + str(ipc_base_dir.joinpath(str(uuid)))


def state_server(ipc_path):
    def pysend(msg):
        return sock.send_multipart([ident, marshal.dumps(msg)])

    def pyrecv():
        ident, msg = sock.recv_multipart()
        return ident, marshal.loads(msg)

    def get_state_keys_cmp(state_keys):
        return [state.get(state_key) for state_key in state_keys]

    # on change handler

    def add_change_handler():
        ipc_path = get_random_ipc()
        pysend(ipc_path)

        state_keys = msg.get(MSGS.state_keys)

        if len(state_keys):
            change_handlers[state_keys].append(
                (ipc_path, get_state_keys_cmp(state_keys))
            )
        else:
            change_handlers['_any_'].append(
                (ipc_path, state)
            )

        return ipc_path

    def resolve_change_handlers():
        complete = []
        for state_keys, handler_list in change_handlers.items():
            if state_keys == '_any_':
                new = state
            else:
                new = get_state_keys_cmp(state_keys)

            for index, (ipc_path, old) in enumerate(handler_list):
                if old != new:
                    sock = ctx.socket(zmq.PUSH)
                    sock.bind(ipc_path)
                    sock.send(marshal.dumps(state))
                    sock.close()

                    complete.append((state_keys, index))

        for state_keys, index in complete:
            del change_handlers[state_keys][index]

    # on val change handler

    def add_val_change_handler():
        ipc_path = get_random_ipc()
        pysend(ipc_path)

        state_key = msg.get(MSGS.state_key)

        val_change_handlers[state_key].append(
            (ipc_path, state.get(state_key))
        )

        resolve_val_change_handlers()

    def resolve_val_change_handlers():
        complete = []
        for state_key, handler_list in val_change_handlers.items():
            new = state.get(state_key)

            for index, (ipc_path, old) in enumerate(handler_list):
                if old != new:
                    sock = ctx.socket(zmq.PUSH)
                    sock.bind(ipc_path)
                    sock.send(marshal.dumps(state.get(state_key)))
                    sock.close()

                    complete.append((state_key, index))

        for state_key, index in complete:
            del val_change_handlers[state_key][index]

    # condition handler

    def add_condition_handler():
        ipc_path = get_random_ipc()
        pysend(ipc_path)

        condition_handlers.append((ipc_path, FunctionType(msg[MSGS.testfn], globals())))

        resolve_condition_handlers()

    def resolve_condition_handlers():
        complete = []
        for index, (ipc_path, test_fn) in enumerate(condition_handlers):
            if test_fn(state):
                sock = ctx.socket(zmq.PUSH)
                sock.bind(ipc_path)
                sock.send(marshal.dumps(state))
                sock.close()

                complete.append(index)

        for index in complete:
            del condition_handlers[index]

    # init zmq socket

    ctx = zmq.Context()
    sock = ctx.socket(zmq.ROUTER)
    sock.bind(ipc_path)
    # sleep(1)
    state = {}
    condition_handlers = []
    val_change_handlers = defaultdict(list)
    change_handlers = defaultdict(list)

    # enter server mainloop
    while True:
        ident, msg = pyrecv()
        # print('server', msg, 'from', ident)
        action = msg.get(MSGS.ACTION)

        if action is not None:
            if action == ACTIONS.get_state:
                pysend(state)
            elif action == ACTIONS.add_val_chng_hand:
                add_val_change_handler()
            elif action == ACTIONS.add_cond_hand:
                add_condition_handler()
            elif action == ACTIONS.add_chng_hand:
                add_change_handler()
            else:
                args, kwargs = msg.get(MSGS.args), msg.get(MSGS.kwargs)
                fn = getattr(state, action)

                if args is None:
                    if kwargs is None:
                        pysend(fn())
                    else:
                        pysend(fn(**kwargs))
                else:
                    if kwargs is None:
                        pysend(fn(*args))
                    else:
                        pysend(fn(*args, **kwargs))

            if action in ACTIONS_THAT_MUTATE:
                # print(state_handlers)
                resolve_change_handlers()
                resolve_condition_handlers()
                resolve_val_change_handlers()
                # print(state_handlers)
