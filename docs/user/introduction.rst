Introduction to ZProc
=====================

The idea of zproc revolves around this :py:class:`.State` object.

A :py:class:`.Context` is provided as an encapsulation of :py:class:`.Process` and :py:class:`.State`.
It's the most obvious way to launch processes with zproc.

Each :py:class:`.Context` object is associated with a state;
accessible by its Processes.

Here's how you create a :py:class:`.Context`.

.. code-block:: python

    import zproc

    ctx = zproc.Context()



Launching a Process
-------------------

Lets launch a process that does nothing.

.. code-block:: python

    def my_process(state):
        pass

    ctx.process(my_process)

The :py:meth:`~.Context.process` will launch a process, and provide it with ``state``.

---

:py:meth:`~.Context.process` works both as a function, and decorator.

.. code-block:: python

    @ctx.process
    def my_process(state):
        state['apples'] = 5
        state.get('apples')
        state.setdefault('apples', 10)
        ...

---

The ``state`` is a *dict-like* object.

*dict-like*, because it's not exactly a dict.

You *cannot* mutate the underlying ``dict`` directly.
It's guarded by a Process whose sole job is to manage it.

---

P.S. You may also access it from the :py:class:`.Context` itself using ``ctx.state``.


Providing arguments to a Process
--------------------------------

To provide some initial values to a Process, you can use use standard \*args and \*\*kwargs.

.. code-block:: python

    def my_process(state, num, exp):
        print(num, exp)  # 2, 4

    ctx.process(my_process, args=[2], kwargs={'exp': 4})

\*args is a sequence of arguments for the function; \*\*kwargs is a dict, which maps argument names to values.


Waiting for a Process
---------------------

Once you've launched a Process, you can wait for it to complete,
and obtain the return value.

.. code-block:: python

    from time import sleep


    def sleeper(state):
        sleep(5)
        return 'Hello There!'

    my_process = ctx.process(sleeper)
    print(my_process.wait())   # Hello There!


.. _process_factory:

Process Factory
---------------

:py:meth:`~.Context.process_factory` let's you launch multiple processes at once.

.. code-block:: python

    def worker(state):
        sleep(5)
        return 'Task Complete!'

    ctx.process_factory(worker, count=10)


.. _process_map:

Process Map
---------------

:py:meth:`~.Context.process_map` let's you use the in-built `map()` function in a parallel way.


Here is a quick run-down of what this can do :-

.. code-block:: python
    :caption: Works similar to ``map()``

    def square(num):
        return num * num

    # [1, 4, 9, 16]
    list(ctx.process_map(square, [1, 2, 3, 4]))


.. code-block:: python
    :caption: Common Arguments.

    def power(num, exp):
        return num ** exp

    # [0, 1, 8, 27, 64, ... 941192, 970299]
    list(
         ctx.process_map(
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
        ctx.process_map(
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
        ctx.process_map(
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


What's interesting about :py:meth:`~.Context.process_map` is that it returns a generator.

The moment you call it, it will distribute the task to "count" number of workers.

It will then, return with a generator,
which in-turn will do the job of pulling out the results from these workers,
and arranging them in order.


>>> import zproc
>>> import time

>>> ctx = zproc.Context()

>>> def my_blocking_thingy(x):
...     time.sleep(5)
...
...     return x * x
...

>>> res = ctx.process_map(my_blocking_thingy, range(10))  # returns immediately
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
...

It is noteworthy, that computation continues in the background while the main process is running.

Subsequently, the amount of time it takes for ``next(res)`` is variable (non-sequential).

Reactive programming with zproc
-------------------------------

This is the part where you really start to see the benefits of a smart state.
The state knows when it's being mutated, and does the job of notifying everyone.

I like to call it :ref:`state-watching`.

---

State watching allows you to "react" to some change in the state in an efficient way.

Lets say, you want to wait for the number of "cookies" to be "5".

Normally, you might do it with something like this:

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

And from there on, you try to manage the time for which your application sleeps ( to arrive at a sweet spot).

zproc provides an elegant, easy to use solution to this problem.

.. code-block:: python

    def my_process(state):
        state.get_when_equal('cookies', 5)
        print('done with zproc!')

This eats very little to no CPU, and is fast enough for almost everyone needs.

---

This doesn't do any expensive "busy" waiting.
Under the covers, it's just a socket waiting for a request.

If you want, you can also provide a function:

.. code-block:: python

    def my_process(state):
        state.get_when(lambda state: state.get('cookies') == 5)


The function you provide will get called on each state update,
to check whether the return value is *truthy*.

.. caution::

    You can't do things like this:

    .. code-block:: python

        from time import time

        t = time()
        state.get_when(lambda state: time() > t + 5)  # wrong!

    The State responds to *state* changes. Changing time doesn't signify a state update.


Mutating objects inside state
-----------------------------

You must remember that you can't mutate (update) objects beyond one level inside the state.

.. code-block:: python

    state['numbers'] = [1, 2, 3]  # works

    state['numbers'].append(4)  # doesn't work


While this might look like a flaw of zproc (and it somewhat is),
you can see this as a feature. It will avoid you from

1. over-complicating your state.
2. avoiding race conditions.

The correct way to mutate objects inside the state, is to do them atomically,
which is to say using the :py:func:`~.atomic` decorator.

.. code-block:: python

    @zproc.atomic
    def add_a_number(state, to_add)
        state['numbers'].append(to_add)


    def my_process(state):
        add_a_number(state, 4)


Read more about :ref:`atomicity`.


Something to keep in mind
-------------------------

Absolutely none of the the classes in ZProc are Process or Thread safe.
You must never attempt to share a objects between multiple processes.

Create a new one for each Process.
Communicate and synchronize using the State at all times.

This is, in-general *very* good practice.

Never attempt to directly share python objects between Processes, and the multitasking gods will reward you :).

---

You can ask ZProc to create new objects for you.

.. code-block:: python

    ctx = zproc.Context()

    def my_process(inner_ctx):
        print(inner_ctx)  # This context is different.

    ctx.process(my_process, pass_context=True)  # Notice "pass_context"


Just never attempt to share things directly.

.. code-block:: python

    ctx = zproc.Context()

    def my_process():
        print(ctx)  # This is not allowed!

    ctx.process(my_process)
