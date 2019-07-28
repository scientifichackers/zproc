from functools import wraps
from typing import Callable, Tuple, Any

import glom
from glom import PathAccessError

from zproc import serializer
from zproc.consts import Msgs, Cmds


def atomic(fn: Callable = None, *, path: str = None) -> Callable:
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
    ... def increment(state):
    ...     state["count"] += 1
    ...     return state["count"]
    ...
    >>> client = zproc.Client(value={"count": 0})
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
            return client._state.state_request_reply(msg)

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
def call(state: dict, spec: str, method: str, *args, **kwargs) -> Any:
    """
    Call a ``method`` (atomically) on the object found in the state,
    using the glom ``spec``, with ``*args`` and ``**kwargs``.

    >>> import zproc
    >>> client = zproc.Client(value={'foot': {'shoes': []}})
    >>> client.call("foot.shoes", "append", "nike")
    >>> client.get()
    {'foot': {'shoes': ['nike']}}
    """
    value = glom.glom(state, spec)
    return getattr(value, method)(*args, **kwargs)


@atomic
def apply(state: dict, spec: str, method: str, *args, **kwargs) -> Any:
    """
    Similar to :py:meth:`call`,
    but replaces the result of the ``method`` call with the object found using the glom ``spec``.

    >>> import zproc
    >>> client = zproc.Client(value={'box': {'cookies': 0}})
    >>> client.apply("box.cookies", "__add__", 5)
    5
    >>> client.get('box.cookies')
    5
    """
    value = getattr(glom.glom(state, spec), method)(*args, **kwargs)
    glom.assign(state, spec, value)
    return value


@atomic
def get(state: dict, spec=None) -> Any:
    """
    Retrieve a value from the state dict using a glom ``spec``,

    >>> import zproc
    >>> client = zproc.Client(value={'a': {'b': 'c'}})
    >>> client.get('a.b')
    'c'

    If ``spec`` is ``None``, then this just returns the full copy of the state.
    """
    if spec is None:
        return state
    return glom.glom(state, spec)


@atomic
def set(state: dict, path: str, value: dict, *, missing: Callable = dict) -> None:
    """
    Provides convenient "deep set"
    functionality, modifying nested data structures in-place::

    >>> import zproc
    >>> client = zproc.Client(value={'a': [{'b': 'c'}, {'d': None}]})
    >>> client.set('a.1.d', 'e')
    >>> client.get()
    {'a': [{'b': 'c'}, {'d': 'e'}]}

    Missing structures can also be automatically created with the ``missing`` parameter.
    """
    glom.assign(state, path, value, missing=missing)


@atomic
def update(state: dict, *others: dict) -> None:
    """
    Merge the state :py:class:`dict` with ``others``, using :py:meth:`dict.update`.

    >>> import zproc
    >>> client = zproc.Client()
    >>> client.merge({'a': 'alpha'}, {'b': 'B'}, {'a': 'A'})
    >>> client.get()
    {'a': 'A', 'b': 'B'}
    """
    for it in others:
        state.update(it)

@atomic
def __contains__(state: dict, spec) -> bool:
    try:
        glom.glom(state, spec)
    except PathAccessError:
        return False
    return True

@atomic
def clear(state: dict) -> None:
    state.clear()