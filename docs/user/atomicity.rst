Atomicity
=========

**The elephant in the room, race-conditions.**

In ZProc world, a single dict operation is __guaranteed™__ to be atomic.

But, in real world applications require arbitrary number of operations to be atomic.

**Exhibit A**

.. code-block:: python

    def increment(step):
        state['count'] += step

    increment(5)

``increment()`` might look like a single operation, but don't get fooled! (They're 2)

1. ``__getitem__``  -> get ``'count'``

2. ``__setitem__``  -> set ``'count'` to ``<count> + 1``

``__getitiem__` and ``__setitem__`` are **guarateed™** to be atomtic on their own, but NOT in conjunction.

If these operations are not done atomically,
it exposes the possiblity of other Processes trying to do operations between "1" and "2"


Clearly, a remedy is required.

---------

With ZProc, it's dead simple.

Let's make some changes to our example..

**Exhibit A (Part 2)**

.. code-block:: python

    @state.atomify()
    def increment(state, step):
        state['count'] += step

    increment(5)


If it wasn't clear, :py:meth:`~.ZeroState.atomify()` makes any arbitrary function,
an atomic operation on the state.


:py:meth:`~.ZeroState.atomic()` <- non-decorator version

`🔖 <https://github.com/pycampers/zproc/tree/master/examples>`_ <- full example
