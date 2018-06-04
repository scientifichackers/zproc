API
===


Context
-------

The first thing you should do is create a Context.

.. autoclass:: zproc.Context
    :inherited-members:


ZeroProcess
-----------

Once you have yourself a Context, you create processes.

All processes are an instance of ZeroProcess.

.. autoclass:: zproc.ZeroProcess
    :inherited-members:

ZeroState
---------

Once you have a ZeroProcess, you can use ZeroState to access the state,
along with some other useful operations.


.. autoclass:: zproc.ZeroState
    :inherited-members:
    :exclude-members: clear, copy, fromkeys, get, items, keys, pop, popitem, setdefault, update, values

Functions
---------

These helper functions are useful for miscellaneous tasks that don't require setting up a Context.

.. autofunction:: zproc.ping