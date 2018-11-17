.. _atomicity:

Atomicity and race conditions
=============================

When writing parallel/concurrent code, atomicity is a major concern.

zproc provides a powerful consturct, the :py:func:`~.atomic()` decorator
to make it easy for you to write correct multi tasking code.

The problem
-----------

.. sidebar:: Atomic operations

    In concurrent programming,
    an operation (or set of operations) is atomic, linearizable, indivisible or uninterruptible
    if it appears to the rest of the system to occur at once without being interrupted.

If an operation can be divided into pieces, then other Processes might jump
in and out between these pieces and try to meddle with each others' work, confusing everyone.


.. code-block:: python
    :caption: non-atomic incrementer

    state['count'] += 5

The above code might look like a single operation, but don't get fooled! (They're 2)

1. get ``'count'``, i.e. ``dict.__getitem__('count')``
2. set ``'count'`` to ``count + 1``, i.e. ``dict.__setitem__('count', count + 1)``

The solution
------------

zproc **guarantees™** that a single method call on a ``dict`` is atomic.

This takes out a lot of guesswork in determining the atomicity of an operation.
Just think in terms of ``dict`` methods.

So, ``dict.__getitiem__()`` and ``dict.__setitem__()`` are **guarateed™**
to be atomic on their own, but not in conjunction. *If these operations are not done atomically,
it exposes the possibility of other Processes trying to do operations between "1" and "2"*

zproc makes it dead simple to avoid such race conditions.
Let's make some changes to our example...

.. code-block:: python
    :caption: atomic incrementer

    @zproc.atomic
    def increment(snap, step):
        snap['count'] += step

    increment(state, 5)

:py:func:`~.atomic()` transforms any arbitrary function into
an atomic operation on the state.

*Notice, the use of the word* ``snap`` *instead of* ``state`` *inside* ``increment()``.

This is because the :py:func:`~.atomic()` wrapper provides only a *snapshot* of the state, as a ``dict`` object.
It's important to realize that ``snap`` is not a :py:class:`State` object.

This enables you to mutate ``snap`` freely
and the changes will be reflected in the global state
(after ``increment()`` returns).
It also means that you cannot assign to ``snap``, only mutate.

.. code-block:: python
    :caption: assignment not allowed

    @zproc.atomic
    def setcount(snap):
        snap = {'count': 10}  # wrong!

    setcount(state)


Sidenotes
---------

- | While zproc does provide you a mechanism to avoid such race conditions,
  | you still need to identify the critical points where a race condition can occur,
  | and prevent it using :py:func:`~.atomic()`.

- To preserve state consistency, update related State keys in a single atomic operation.

- | If an error occurs while the function is running, the state will remain *unaffected*.

- | The first argument to the atomic function must be a :py:class:`.State` object.



A complete example is available `here <https://github.com/pycampers/zproc/tree/master/examples/atomicity.py>`_.

