API
====

Functions
---------

.. autofunction:: zproc.ping
.. autofunction:: zproc.atomic
.. autofunction:: zproc.start_server
.. autofunction:: zproc.signal_to_exception


Exceptions
----------

.. autoexception:: zproc.ProcessWaitError
.. autoexception:: zproc.RemoteException
.. autoexception:: zproc.SignalException



Context
---------

.. autoclass:: zproc.Context
    :inherited-members:

Process
---------

.. autoclass:: zproc.Process
    :inherited-members:

State
---------

.. autoclass:: zproc.State
    :inherited-members:
    :exclude-members: clear, get, items, keys, pop, popitem, setdefault, update, values

