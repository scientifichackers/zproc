.. _atomicity:

Atomicity and race conditions
=============================

When writing parallel code, one has to think about atomicity.

If an operation is atomic, then it means that the operation is indivisible, just like an atom.

If an operation can be divided into pieces, then processes might jump
in and out between the pieces and try to meddle with your work, confusing everyone.

While zproc does provide mechanisms to avoid these kind of race conditions,
it is ultimately up-to you to figure out if an operation is atomic or not.

zproc **guarantees™** that a single method call on a ``dict`` is atomic.

This takes out a lot of guesswork in determining the atomicity of an operation.

Just think in terms of ``dict`` methods.


Example
-------

::

    def increment(state, step):
        state['count'] += step

    increment(state, 5)

``increment()`` might look like a single operation, but don't get fooled! (They're 2)

1. get ``'count'``. (``dict.__getitem__()``)

2. set ``'count'`` to ``<count> + 1``. (``dict.__setitem__()``)

``dict.__getitiem__()`` and ``dict.__setitem__()`` are **guarateed™**
to be atomic on their own, but NOT in conjunction.

If these operations are not done atomically,
it exposes the possibility of other Processes trying to do operations between "1" and "2"


Clearly, a remedy is required.

---------

With ZProc, it's dead simple.

Let's make some changes to our example..

::

    @zproc.atomic
    def increment(state, step):
        state['count'] += step

    increment(state, 5)

:py:meth:`~.atomic()` transforms any arbitrary function into
an atomic operation on the state.

This is very different from traditional locks. Locks are just flags. This is NOT a flag.

It's a hard restriction on state.

Also, If an error shall occur while the function is running, the state will remain UNAFFECTED.

`🔖 <https://github.com/pycampers/zproc/tree/master/examples/atomicity.py>`_ <- full example
