Atomicity
=========

**The elephant in the room, race-conditions.**

When doing multiprocessing, one has to inevitably think about atomicity.

ZProc __guarantees™__ that a single dict operation is atomic.

However, your application may require arbitrary number of operations to be atomic.

**Exhibit A**

.. code-block:: python

    def increment(state, step):
        state['count'] += step

    increment(state, 5)

``increment()`` might look like a single operation, but don't get fooled! (They're 2)

1. ``__getitem__``  -> get ``'count'``

2. ``__setitem__``  -> set ``'count'` to ``<count> + 1``

``__getitiem__` and ``__setitem__`` are **guarateed™** to be atomtic on their own, but NOT in conjunction.

If these operations are not done atomically,
it exposes the possibility of other Processes trying to do operations between "1" and "2"


Clearly, a remedy is required.

---------

With ZProc, it's dead simple.

Let's make some changes to our example..

.. code-block:: python

    @zproc.atomic
    def increment(state, step):
        state['count'] += step

    increment(state, 5)

:py:meth:`~.atomic()` makes any arbitrary function,
an atomic operation on the state.

This is very different from traditional locks. Locks are just flags. This is NOT a flag.

It's a hard restriction on state.

Also, If an error shall occur while the function is running, the state will remain UNAFFECTED.

`🔖 <https://github.com/pycampers/zproc/tree/master/examples>`_ <- full example
