How zproc talks
===============

While you don't need to do any communication on your own,
zproc is actively doing it behind the covers, using zmq sockets.

Thanks to this,
you take the same code and run it in a different environment,
with very little modifications.

Furthermore, you can even take your existing code and scale it across
multiple computers on your network.

This is the benefit of NOT using shared memory.
Your whole stack is built on communication, and hence,
becomes extremely scalable and flexible when you need it to be.

.. _zproc-server-address-spec:

The zproc server address spec
------------------------------

By default, zproc produces random connection endpoints for communication,
and as a result, you never need to provide it any addresses.

However, zproc does expose the necessary API,
shall you want to manually provide the connection endpoints through which zproc should communicate.

You will find ``server_address`` in the function arguments / class constructors,
which allows you provide a custom address.

It is simply, a 2-length tuple containing 2 connection endpoints.

(first for ``REQ-REP`` socket and second for ``PUB-SUB`` socket)

A endpoint is a string consisting of two parts as follows: ``<transport>://<address>``.
The transport part specifies the underlying transport protocol to use.
The meaning of the address part is specific to the underlying transport protocol selected.

The following transports can be used:

- ipc
    local inter-process communication transport, see `zmq_ipc <http://api.zeromq.org/2-1:zmq_ipc>`_

- tcp
    unicast transport using TCP, see `zmq_tcp <http://api.zeromq.org/2-1:zmq_tcp>`_


.. code-block:: py
    :caption: Example

    server_address=('tcp://127.0.0.1:5000', 'tcp://127.0.0.1:5001')

    server_address=('ipc:///home/username/test1', 'ipc:///home/username/test2')

IPC or TCP?
-----------

If you have a POSIX, and don't need to communicate across multiple computers,
you are better off reaping the performance benefits of IPC.

For other use-cases, TCP.

By default, zproc will use IPC if it sees a POSIX, else TCP.

.. _start-server:

Starting the server manually
----------------------------

By default, zproc will start the server when you create a :py:class:`.Context` object.

Each :py:class:`.Context` (and its processes) have a separate, isolated state.

If you want multiple :py:class:`.Context` objects to access the same state,
you can start the server manually,
and provide the :py:class:`.Context` with the address of the server.

If you manually provide the address to :py:class:`.Context`, then zproc won't start the
server itself, and you have to do it manually, using :py:func:`.start_server`.

This is useful when you want 2 separate scripts to access the same state.

You can also do the same with :py:class:`.State`.

::

    import zproc


    ADDRESS = ('tcp://127.0.0.1:5000', 'tcp://127.0.0.1:5001')

    zproc.start_server(ADDRESS)

    zproc.Context(ADDRESS)

    zproc.State(ADDRESS)


The above example uses tcp, but ipc works just as well.

.. caution::

    - Start the server exactly once, per address.
    - Start the server before you access the :py:class:`.State`, since :py:class:`.State` solely depends on the server.

You can start the server from anywhere you wish, and then access it though the address.

