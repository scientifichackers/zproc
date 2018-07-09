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

----

zproc makes it dead simple to avoid such race conditions.

Let's make some changes to our example..

::

    @zproc.atomic
    def increment(state, step):
        state['count'] += step

    increment(state, 5)

:py:func:`~.atomic()` transforms any arbitrary function into
an atomic operation on the state.

This is very different from traditional locks. Locks are just flags. This is NOT a flag.

It's a hard restriction on state.

Also, If an error shall occur while the function is running, the state will remain UNAFFECTED.

.. note ::

    The first argument to a function that is wrapped with :py:func:`~.atomic()` must be a :py:class:`.State` object.

.. note ::

    The ``state`` you get inside an atomic wrapped function
    is not a :py:class:`.State` object,
    but instead the full underlying ``dict`` object.

    This means you can't perform the operations like state watching,
    BUT, you can mutate objects inside the state freely,
    since you're directly mutating the underlying ``dict`` object.

    (This means, things like appending to a list will work)



`🔖 <https://github.com/pycampers/zproc/tree/master/examples/atomicity.py>`_ <- full example
