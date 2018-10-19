Spawns a new :py:class:`Process`,
and then calls the wrapped function inside of that new process.

*The wrapped function is run with the following signature:*

``target(snapshot, state, *args, **kwargs)``

*Where:*

- ``target`` is the wrapped function.

- ``snapshot`` is a ``dict`` containing a copy of the state.

  Its serves as a *snapshot* of the state,
  corresponding to the state-change for which the wrapped function is being called.

- ``state`` is a :py:class:`State` instance.

- ``*args`` and ``**kwargs`` are passed on from ``**process_kwargs``.
