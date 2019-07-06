from functools import wraps
from typing import Callable, Tuple, Any

import glom

from . import serializer
from .consts import Msgs, Cmds


def atomic(fn: Callable=None, *, path:str=None) -> Callable:
    """
    Wraps a function, to create an atomic operation out of it.

    This contract guarantees, that while an atomic ``fn`` is running -

    - No one, except the "callee" may access the state.
    - If an ``Exception`` occurs while the ``fn`` is running, the state remains unaffected.
    - | If a signal is sent to the "callee", the ``fn`` remains unaffected.
      | (The state is not left in an incoherent state.)

    .. note::
        - The first argument to the wrapped function *must* be a :py:class:`State` object.
        - The wrapped ``fn`` receives a frozen version (snapshot) of state,
          which is a ``dict`` object, not a :py:class:`State` object.
        - It is not possible to call one atomic function from other.

    Please read :ref:`atomicity` for a detailed explanation.

    :param fn:
        The function to be wrapped, of the following signature:

        (state: dict, *args, **kwargs) -> Any

    :returns:
        The wrapped function, of the following signature:

        (client: Client, *args, **kwargs) -> Any

    >>> import zproc
    >>>
    >>> @zproc.atomic
    >>> def increment(state):
    ...     state["count"] += 1
    ...     return state["count"]
    ...
    >>> client = zproc.Client()
    >>> increment(client)
    1
    """
    if fn is not None:
        msg = {
            Msgs.cmd: Cmds.run_fn_atomically,
            Msgs.info: (serializer.dumps_fn(fn), path),
            Msgs.args: (),
            Msgs.kwargs: {},
        }

        @wraps(fn)
        def wrapper(client, *args, **kwargs):
            msg[Msgs.args] = args
            msg[Msgs.kwargs] = kwargs
            return client._state._s_request_reply(msg)

        return wrapper

    def decorator(fn: Callable) -> Callable:
        return atomic(fn, path=path)

    return decorator


@atomic
def keys(state: dict) -> tuple:
    return tuple(state.keys())


@atomic
def values(state: dict) -> tuple:
    return tuple(state.values())


@atomic
def items(state: dict) -> Tuple[tuple, ...]:
    return tuple(state.items())


@atomic
def copy(state: dict) -> dict:
    return state


@atomic
def call(state: dict, path: str, method: str, *args, **kwargs) -> Any:
    value = glom.glom(state, path)
    return getattr(value, method)(*args, **kwargs)


@atomic
def apply(state: dict, path: str, method: str, *args, **kwargs) -> Any:
    value = getattr(glom.glom(state, path), method)(*args, **kwargs)
    glom.assign(state, path, value)
    return value


@atomic
def get(state: dict, path: str) -> Any:
    return glom.glom(state, path)


@atomic
def set(state: dict, path: str, value: dict, *, missing: Callable = dict) -> None:
    glom.assign(state, path, value, missing=missing)


@atomic
def merge(state: dict, *others: dict) -> None:
    glom.merge((state,) + others)
