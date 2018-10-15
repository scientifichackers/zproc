How ZProc talks
===============

While you don't need to do any communication on your own,
ZProc is actively doing it behind the covers, using zmq sockets.

Thanks to this,
you take the same code and run it in a different environment,
with very little to no modifications.

Furthermore, you can even take your existing code and scale it across
multiple computers on your network.

This is the benefit of message passing parallelism.
Your whole stack is built on communication, and hence,
becomes extremely scalable and flexible when you need it to be.

.. _server-address-spec:

The server address spec
-----------------------

An endpoint is a string consisting of two parts as follows: ``<transport>://<address>``.
The transport part specifies the underlying transport protocol to use.
The meaning of the address part is specific to the underlying transport protocol selected.

The following transports may be used:

- ipc
    local inter-process communication transport, see `zmq_ipc <http://api.zeromq.org/2-1:zmq_ipc>`_

    (``tcp://<address>:<port>``)

- tcp
    unicast transport using TCP, see `zmq_tcp <http://api.zeromq.org/2-1:zmq_tcp>`_

    (``ipc://<file path>``)

.. code-block:: python
    :caption: Example

    server_address='tcp://0.0.0.0:50001'

    server_address='ipc:///home/username/my_endpoint'


IPC or TCP?
-----------

If you have a POSIX, and don't need to communicate across multiple computers,
you are better off reaping the performance benefits of IPC.

For other use-cases, TCP.

By default, zproc will use IPC if it is available, else TCP.

.. _start-server:

Starting the server manually
----------------------------

When you create a :py:class:`.Context` object, ZProc will produce random a ``server_address``,
and start a server.

For advanced use-cases,
you might want to use a well-known static address that all the services in your application are aware of.

**This is quite useful when you want to access the same state across multiple nodes on a network,
or in a different context on the same machine; anywhere communicating a "random" address would become an issue.**

However, if you use a static address, :py:class:`.Context` won't start that
server itself, and you have to do it manually, using :py:func:`.start_server`
(This behavior enables us to spawn multiple :py:class:`.Context` objects with the same address).

*All the classes in ZProc take* ``server_address`` *as their first argument.*


    >>> import zproc
    >>> ADDRESS = 'tcp://127.0.0.1:5000'
    >>> zproc.start_server(ADDRESS)  # Important!
    (<Process(Process-1, started)>, 'tcp://127.0.0.1:5000')
    >>> zproc.Context(ADDRESS)
    <Context for State: {} to 'tcp://127.0.0.1:5000' at ...>
    >>> zproc.State(ADDRESS)
    <State: {} to 'tcp://127.0.0.1:5000' at ...>


The above example uses tcp, but ipc works just as well. (except across multiple machines)

.. caution::

    Start the server *before* you access the :py:class:`.State` in *any* way; it solely depends on the server.

TLDR; You can start the server from anywhere you wish, and then access it though the address.