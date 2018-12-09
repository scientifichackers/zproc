import pickle
from typing import Callable, Any, Dict

from cloudpickle import cloudpickle

from zproc import exceptions


def dumps(obj: Any) -> bytes:
    return pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)


def loads(bytes_obj: bytes) -> Any:
    rep = pickle.loads(bytes_obj)
    if isinstance(rep, exceptions.RemoteException):
        rep.reraise()
    return rep


def _get_fn_hash(fn: Callable):
    try:
        return hash(fn.__code__)
    except AttributeError:
        return hash(fn)


_fn_dump_cache: Dict[int, bytes] = {}


def dumps_fn(fn: Callable) -> bytes:
    fn_hash = _get_fn_hash(fn)
    try:
        fn_bytes = _fn_dump_cache[fn_hash]
    except KeyError:
        fn_bytes = cloudpickle.dumps(fn)
        _fn_dump_cache[fn_hash] = fn_bytes
    return fn_bytes


_fn_load_cache: Dict[int, Callable] = {}


def loads_fn(fn_bytes: bytes) -> Callable:
    fn_bytes_hash = hash(fn_bytes)
    try:
        fn = _fn_load_cache[fn_bytes_hash]
    except KeyError:
        fn = cloudpickle.loads(fn_bytes)
        _fn_load_cache[fn_bytes_hash] = fn
    return fn
