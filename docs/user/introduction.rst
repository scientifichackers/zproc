Introduction to ZProc
=====================

The idea of zproc revolves around this funky :py:class:`.State` object.

A :py:class:`.Context` is provided as a factory for creating objects.
It's the easiest, most obvious way to use zproc.

Each :py:class:`.Context` object must be associated with a server process,
whose job is to manage the state of your applciation;
anything that needs synchronization.

Creating one is as simple as:

.. code-block:: python

    import zproc

    ctx = zproc.Context()

It makes the creation of objects explicit and bound to a specific Context,
eliminating the need for various guesing games.

The Context means just that.
It's a collection of various parameters and flags that help the framework
identify *where* the program currently is.

Launching a Process
---------------------------------

.. sidebar:: Decorators

    Function decorators are functions which
    accept other functions as arguments,
    and add some wrapper code around them.

    .. code-block:: python

        @decorator
        def func():
            pass

        # roughly equivalent to:

        func = decorator(func)

The :py:meth:`.Context.spawn` function allows you to launch processes.

.. code-block:: python

    def my_process(state):
        ...

    ctx.spawn(my_process)

It works both as a function, and decorator.

.. code-block:: python

    @ctx.process
    def my_process(state):
        ...


The state
---------

.. code-block:: python

    state = ctx.create_state()



:py:meth:`~.Context.spawn` will launch a process, and provide it with ``state``.

:py:class:`.State` is a *dict-like* object.
*dict-like*, because it's not exactly a ``dict``.

It supports common dictionary operations on the state.

| However, you *cannot* actually operate on the underlying ``dict``.
| It's guarded by a Process, whose sole job is to manage it.
| The :py:class:`.State` object only *instructs* that Process to modify the ``dict``.

You may also access it from the :py:class:`.Context` itself -- ``ctx.state``.

Process arguments
------------------------------

To supply arguments to a the Process's target function,
you can use ``args`` or ``kwargs``:

.. code-block:: python

    def my_process(state, num, exp):
        print(num, exp)  # 2, 4

    ctx.spawn(my_process, args=[2], kwargs={'exp': 4})

``args`` is a sequence of positional arguments for the function;
``kwargs`` is a dict, which maps argument names and values.


Waiting for a Process
-----------------------------------

Once you've launched a Process, you can wait for it to complete,
and obtain the return value.

.. code-block:: python

    from time import sleep


    def sleeper(state):
        sleep(5)
        return 'Hello There!'

    p = ctx.spawn(sleeper)
    result = p.wait()

    print(result)   # Hello There!


.. _process_factory:

Process Factory
--------------------------

:py:meth:`~.Context.spawn` also lets you launch many processes at once.

.. code-block:: python

    p_list = ctx.spawn(sleeper, count=10)
    p_list.wait()


.. _worker_map:

Worker Processes
----------------

This feature let's you distribute a computation to serveral,
fixed amount of workers.

This is meant to be used for CPU bound tasks,
since you can only have a limited number of CPU bound Processes working at any given time.

:py:meth:`~.Context.worker_map` let's you use the in-built `map()` function in a parallel way.

It divides up the sequence you provide into ``count`` number of pieces,
and sends them to ``count`` number of workers.

---

You first, need a :py:class:`.Workers` object,
which is the front-end for using worker Processes.

.. code-block:: python
    :caption: obtaining workers

    ctx = zproc.Context()

    swarm = ctx.create_swarm(4)

---

Now, we can start to use it.

.. code-block:: python
    :caption: Works similar to ``map()``

    def square(num):
        return num * num

    # [1, 4, 9, 16]
    list(workers.map(square, [1, 2, 3, 4]))


.. code-block:: python
    :caption: Common Arguments.

    def power(num, exp):
        return num ** exp

    # [0, 1, 8, 27, 64, ... 941192, 970299]
    list(
         workers.map(
            power,
            range(100),
            args=[3],
            count=10  # distribute among 10 workers.
         )
    )

.. code-block:: python
    :caption: Mapped Positional Arguments.

    def power(num, exp):
        return num ** exp

    # [4, 9, 36, 256]
    list(
        workers.map(
            power,
            map_args=[(2, 2), (3, 2), (6, 2), (2, 8)]
        )
    )

.. code-block:: python
    :caption: Mapped Keyword Arguments.

    def my_thingy(seed, num, exp):
        return seed + num ** exp

    # [1007, 3132, 298023223876953132, 736, 132, 65543, 8]
    list(
        ctx.worker_map(
            my_thingy,
            args=[7],
            map_kwargs=[
                {'num': 10, 'exp': 3},
                {'num': 5, 'exp': 5},
                {'num': 5, 'exp': 2},
                {'num': 9, 'exp': 3},
                {'num': 5, 'exp': 3},
                {'num': 4, 'exp': 8},
                {'num': 1, 'exp': 4},
            ],
            count=5
        )
    )

---

What's interesting about :py:meth:`~.Context.worker_map` is that it returns a generator.

The moment you call it, it will distribute the task to "count" number of workers.

It will then, return with a generator,
which in-turn will do the job of pulling out the results from these workers,
and arranging them in order.

---

The amount of time it takes for ``next(res)`` is non-linear,
because all the blocking computation is being carrried out in the background.

>>> import zproc
>>> import time

>>> ctx = zproc.Context()

>>> def blocking_func(x):
...     time.sleep(5)
...
...     return x * x
...

>>> res = ctx.worker_map(blocking_func, range(10))  # returns immediately
>>> res
<generator object Context._pull_results_for_task at 0x7fef735e6570>

>>> next(res)  # might block
0
>>> next(res)  # might block
1
>>> next(res)  # might block
4
>>> next(res)  # might block
9
>>> next(res)  # might block
16
*and so on..*


.. _process_map:

Map Processes
-------------

This is meant to be used for I/O and network bound tasks,
as you can have more number of Processes working together,
than the number physical CPUs.

This is beacuase these kind of tasks typically involve waiting for a resource,
and are, as a result quite lax on CPU resources.

:py:meth:`~.Context.map_process`
has the exact same semantics for mapping sequences as :py:meth:`~.Context.map_process`,
except that it launches a new Process for each item in the sequence.

Reactive programming
--------------------

.. sidebar:: Reactive Programming

    Reactive programming is a declarative programming
    paradigm concerned with data streams and the propagation of change.


This is the part where you really start to see the benefits of a smart state.
The state knows when it's being updated, and does the job of notifying everyone.

State watching allows you to "react" to some change in the state in an efficient way.

The problem
+++++++++++

.. sidebar:: Busy waiting

    busy-waiting
    is a technique in which a process repeatedly checks to see if a condition is true,
    such as whether keyboard input or a lock is available.

*Busy waiting is expensive and quite tricky to get right.*

Lets say, you want to wait for the number of ``"cookies"`` to be ``5``.
Using busy-waiting, you might do it with something like this:

.. code-block:: python

    while True:
        if cookies == 5:
            print('done!')
            break

But then you find out that this eats too much CPU, and put put some sleep.

.. code-block:: python

    from time import sleep

    while True:
        if cookies == 5:
            print('done!')
            break
        sleep(1)

And from there on, you try to manage the time for which your application sleeps (to arrive at a sweet spot).

The solution
++++++++++++

zproc provides an elegant, easy to use solution to this problem.

.. code-block:: python

    def my_process(state):
        state.get_when_equal('cookies', 5)
        print('done with zproc!')

This eats very little to no CPU, and is fast enough for almost everyone needs.


You can also provide a callable,
which gets called on each state update
to check whether the return value is *truthy*.

.. code-block:: python

    state.get_when(lambda snap: snap.get('cookies') == 5)


.. caution::

    Wrong use of state watchers!

    .. code-block:: python

        from time import time

        t = time()
        state.get_when(lambda _: time() > t + 5)  # wrong!

    State only knows how to respond to *state* changes.
    Changing time doesn't signify a state update.


Read more on the :ref:`state-watching`.

Mutating objects inside state
-----------------------------

.. sidebar:: Mutation

    In computer science,
    mutation refers to the act of modifying an object in-place.

    When we say that an object is mutable,
    it implies that its in-place methods "mutate" the object's contents.


Zproc does not allow one to mutate objects inside the state.

.. code-block:: python
    :caption: incorrect mutation

    state['numbers'] = [1, 2, 3]  # works

    state['numbers'].append(4)  # doesn't work


The *right* way to mutate objects in the state,
is to do it using the :py:func:`~.atomic` decorator.

.. code-block:: python
    :caption: correct mutation

    @zproc.atomic
    def add_a_number(snap, to_add)
        snap['numbers'].append(to_add)


    @ctx.process
    def my_process(state):
        add_a_number(state, 4)

Read more about :ref:`atomicity`.


Here be dragons
---------------

.. sidebar:: Thread safety

    Thread-safe code only manipulates shared data structures in a manner that ensures that all
    threads behave properly and fulfill their design specifications without unintended interaction.


Absolutely none of the the classes in ZProc are Process or Thread safe.
You must never attempt to share an object across multiple Processes.

Create a new object for each Process.
Communicate and synchronize using the :py:class:`.State` at all times.

This is, in-general *very* good practice.

Never attempt to directly share python objects across Processes,
and the framework will reward you :).

The problem
+++++++++++

.. code-block:: python
    :caption: incorrect use of the framework

    ctx = zproc.Context()


    def my_process(state):
        ctx.spawn(some_other_process)  # very wrong!

    ctx.spawn(my_process)

Here, the ``ctx`` object is shared between the parent and child Process.
This is not allowed, and will inevitably lead to improper behavior.

The solution
++++++++++++

You can ask zproc to create new objects for you.

.. code-block:: python
    :caption: correct use of the framework

    ctx = zproc.Context()


    def my_process(inner_ctx):
        inner_ctx.spawn(some_other_process)  # correct.

    ctx.spawn(my_process, pass_context=True)  # Notice "pass_context"

---

Or, create new ones youself.

.. code-block:: python
    :caption: correct use of the framework

    ctx = zproc.Context()


    def my_process(state):
        inner_ctx = zproc.Context() # important!
        inner_ctx.spawn(some_other_process)

    ctx.spawn(my_process)
