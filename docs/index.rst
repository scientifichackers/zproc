ZProc: Multi Processing on steroids
===================================

.. image:: https://img.shields.io/pypi/v/zproc.svg?style=for-the-badge
    :alt: PyPI
    :target: https://pypi.org/project/zproc/

.. image:: https://img.shields.io/pypi/pyversions/zproc.svg?style=for-the-badge
    :alt: PyPI - Python Version
    :target: https://pypi.org/project/zproc/

.. image:: https://img.shields.io/github/license/mashape/apistatus.svg?style=for-the-badge
    :alt: license
    :target: https://github.com/pycampers/zproc/blob/master/LICENSE

.. image:: https://img.shields.io/github/stars/pycampers/zproc.svg?style=for-the-badge&label=Stars
    :alt: GitHub stars
    :target: https://github.com/pycampers/zproc

Welcome to ZProc's docs! Glad that you made it here.

- If you're unsure whether you really want to use zproc, read the :ref:`motivation`!
- Head over to the :ref:`user-guide` if you're new.
- Or, if you want information about something specific, use the :ref:`api-doc`!


.. _motivation:

Motivation
-----------------

Typically, when a Process is launched using Python's ``multiprocessing`` module,
Python will spwan a new interpreter,
that inherits resources (like variables, file descriptors etc.) from the parent.

*However, it is not possible for you to update these resources from both Processes.*

Let me explain with an example, where we try to update a ``dict`` from a child Process, but it doesn't really work.

.. code-block:: python
    :caption: multiprocessing module

    import multiprocessing


    state = {"msg": "hello!"}

    def my_process():
        print(state["msg"])

        # this won't show up on global state
        state['msg'] = "bye!"

    p = multiprocessing.Process(target=my_process)
    p.start()
    p.join()

    print(state)  # {"msg": "hello!"}


**This is the problem zproc solves.**

.. code-block:: python
    :caption: zproc

    import zproc

    ctx = zproc.Context()
    ctx.state = {"msg": "hello!"}

    def my_process(state):
        print(state["msg"])

        # this will show up on global state
        state['msg'] = "bye!"

    p = ctx.spawn(my_process)
    p.wait()

    print(ctx.state)  # {"msg": "bye!"}

ZProc achieves this by having `zeromq <http://zeromq.org/>`_ sockets communicate between Processes.

*It cleverly hides away all these details, empowering you to build complex multi-tasking apps fast.*

Also,
it turns out that this model of passing messages fits quite well
for doing a pleothera of multitasking "feats",
like reactive programming, atomic operations, distributed task queues, you name it.


Indicies
------------

.. toctree::
    :maxdepth: 1

    user.rst
    api.rst

- :ref:`genindex`
- :ref:`modindex`
- :ref:`search`

