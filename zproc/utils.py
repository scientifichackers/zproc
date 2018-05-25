from collections import deque
from multiprocessing import current_process
from pathlib import Path
from types import FunctionType
from typing import Iterable
from uuid import uuid1, UUID

import dill
import psutil

ipc_base_dir = Path.home().joinpath('.tmp')

if not ipc_base_dir.exists():
    ipc_base_dir.mkdir()


def de_serialize_func(fn_bytes: bytes) -> FunctionType:
    return dill.loads(fn_bytes)


def serialize_func(fn: FunctionType) -> bytes:
    return dill.dumps(fn)


def get_random_ipc() -> str:
    return get_ipc_path(uuid1())


def get_ipc_path(uuid: UUID) -> str:
    return 'ipc://' + str(ipc_base_dir.joinpath(str(uuid)))


def method_injector(t: type, names: Iterable[str], get_method):
    for name in names:
        setattr(t, name, get_method(name))


def reap_ptree(*args):
    """
    Tries hard to terminate and ultimately kill all the children of current process.
    (stolen from - https://psutil.readthedocs.io/en/latest/#terminate-my-children)
    """

    self = psutil.Process()  # much apt naming :)
    procs = self.children()

    # keep the party going, till everyone dies.
    while procs:
        # send SIGTERM
        for p in procs:
            p.terminate()

        gone, alive = psutil.wait_procs(procs, timeout=0.1)

        if alive is not None:
            # send SIGKILL
            for p in alive:
                p.kill()

        procs = self.children()

    if current_process().name != 'MainProcess':
        self.kill()


class Queue(deque):
    """A Queue that can be drained"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def enqueue(self, something):
        self.appendleft(something)

    def dequeue(self):
        self.pop()

    def drain(self):
        # create a copy of the deque, to prevent shit-storms while iterating :)
        iter_deque = self.copy()
        self.clear()

        while True:
            try:
                yield iter_deque.pop()
            except IndexError:
                break


# static declarations

STATE_DICT_LIKE_METHODS = {
    '__contains__',
    '__delitem__',
    '__eq__',
    '__getitem__',
    '__iter__',
    '__len__',
    '__ne__',
    '__setitem__',
    'clear',
    'copy',
    'fromkeys',
    'get',
    'items',
    'keys',
    'pop',
    'popitem',
    'setdefault',
    'update',
    'values'
}

DICT_MUTABLE_ACTIONS = {
    '__setitem__',
    '__delitem__',
    'setdefault',
    'pop',
    'popitem',
    'clear',
    'update',
}

STATE_DICT_DYNAMIC_METHODS = set(STATE_DICT_LIKE_METHODS) - {'__copy__', 'items', 'keys', 'values'}


class Message:
    method_name = 'method'

    args = 'args'
    kwargs = 'kwargs'

    func = 'fn'

    key = 'key'
    keys = 'keys'
    value = 'value'

    func_name = 'fn_name'

# SPECIAL_METHOD_NAMES = {
#     '__repr__',
#     '__bytes__',
#     '__lt__',
#     '__le__',
#     '__eq__',
#     '__ne__',
#     '__gt__',
#     '__ge__',
#     '__hash__',
#     '__bool__',
#     '__len__',
#     '__length_hint__',
#     '__getitem__',
#     '__missing__',
#     '__setitem__',
#     '__delitem__',
#     '__iter__',
#     '__reversed__',
#     '__contains__',
#     '__add__',
#     '__sub__',
#     '__mul__',
#     '__matmul__',
#     '__truediv__',
#     '__floordiv__',
#     '__mod__',
#     '__divmod__',
#     '__pow__',
#     '__lshift__',
#     '__rshift__',
#     '__and__',
#     '__xor__',
#     '__or__',
#     '__radd__',
#     '__rsub__',
#     '__rmul__',
#     '__rmatmul__',
#     '__rtruediv__',
#     '__rfloordiv__',
#     '__rmod__',
#     '__rdivmod__',
#     '__rpow__',
#     '__rlshift__',
#     '__rrshift__',
#     '__rand__',
#     '__rxor__',
#     '__ror__',
#     '__iadd__',
#     '__isub__',
#     '__imul__',
#     '__imatmul__',
#     '__itruediv__',
#     '__ifloordiv__',
#     '__imod__',
#     '__ipow__',
#     '__irshift__',
#     '__ilshift__',
#     '__iand__',
#     '__ixor__',
#     '__ior__',
#     '__neg__',
#     '__pos__',
#     '__abs__',
#     '__invert__',
#     '__complex__',
#     '__int__',
#     '__float__',
#     '__index__',
#     '__round__',
#     '__trunc__',
#     '__floor__',
#     '__ceil__'
# }
