Distributed compute using ZProc
===============================

*zproc makes distributed compute easy for you.*


.. code-block:: python

    import zproc


    ctx = zproc.Context()

    ctx.workers.start()
    result = ctx.workers.map(pow, [1, 2, 3, 4])

    print(result, list(result))


This will spawn workers,
distribute the task,
send the task over,
and then pull the results from them.


:py:meth:`.Swarm.map` runs across machines.


.. code-block:: python
    :caption: 192.168.1.25

    ctx = zproc.Context("tcp://0.0.0.0:50001")

    ctx.workers.start()


.. code-block:: python
    :caption: Computer 2

    ctx = zproc.Context("tcp://192.168.1.25:50001")

    ctx.workers.start()

.. code-block:: python
    :caption: Computer 3

    ctx.workers.map(pow, [1, 2, 3, 4])
