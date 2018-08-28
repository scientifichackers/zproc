Introduction to ZProc
=====================

The whole architecture of zproc is built around a :py:class:`.State` object.

:py:class:`.Context` is provided as a convenient wrapper over :py:class:`.Process` and :py:class:`.State`.

It's is the most obvious way to launch processes with zproc.

Each :py:class:`.Context` object is associated with its own isolated state
that is accessible by that its processes.


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

If you like to be cool, then you can use it as a decorator.
(:py:meth:`~.Context.process` works both as a function, and decorator)

.. code-block:: python

    @ctx.process
    def my_process(state):
        pass


The ``state`` is a *dict-like* object that you can use to represent your application's state.

You can also access it from the :py:class:`.Context` itself using ``ctx.state``.

*dict-like*, because it's not exactly a dict.
It implements the ``dict`` methods, to provide that sweet syntactical sugar.

.. code-block:: python

    state['apples'] = 5

    state.get('apples')

    state.setdefault('apples', 10)

    ...

Behind the scenes, it's literally just passing messages using ZMQ sockets.

Providing arguments to a Process
--------------------------------

To provide some initial values to a Process, you can use use \*args and \*\*kwargs.

.. code-block:: python

    def my_process(state, num, exp):
        print(num ** exp)

    ctx.process(my_process, args=(2,), kwargs={'exp': 4})

.. note::
    ``args`` MUST be an ``Iterable``.

    Since ``(2)`` evaluates to just ``2`` in Python,
    it becomes necessary to have a ``,`` in there,
    so that Python evaluates ``(2,)`` as a ``tuple`` of length ``1``,
    containing ``2`` as the first element.

Waiting for a Process
---------------------

Once you've launched a Process, you can wait for it to complete,
and get it's return value like this:

.. code-block:: python

    from time import sleep


    @ctx.process
    def my_process(state):
        sleep(5)
        return 'Hello There!'


    print(my_process.wait())   # Hello There!


.. _process_factory:

Process Factory
---------------

.. _process_map:

Process Map
---------------

Python's inbuilt ``multiprocessing.Pool`` let's you use the in-built `map()` function in a parallel way.

However, it gets quite finicky to use for anything serious.

That's why ZProc provides a more powerful construct, :py:meth:`~.Context.process_map` for mapping iterables to processes.


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
            args=(3,),
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
            args=(7,),
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


What's really cool about the process map is that it returns a generator.

The moment you call it, it will distribute the task to "count" number of workers.

It will return with a generator,
which in-turn will do the job of pulling in the results from these workers,
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

As a result, the amount of time it takes for ``next(res)`` to return changes over time.

Reactive programming with zproc
-------------------------------

Now, let us uncover "reactive" part of zproc.

I like to call it :ref:`state-watching`.

state watching allows you to react to some change in the state in an efficient way.

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

zproc provides an elegant, easy to use solution for this problem.

.. code-block:: python

    def my_process(state):
        state.get_when_equal('cookies', 5)
        print('done with zproc!')

This eats very little to no CPU, and is fast enough for almost everyone needs.

You must realise that this doesn't do any of that expensive "busy" waiting.
Under the covers, it's actually a socket connecting waiting for a request.

If you want, you can even provide a function:

.. code-block:: python

    def my_process(state):
        state.get_when(lambda state: state.get('cookies') == 5)


The function you provide will get called on each state update,
to check whether the return value is ``True``-like.

You obviously can't do things like this:

.. code-block:: python

    from time import time

    t = time()
    state.get_when(lambda state: time() > t + 5)  # wrong!

The function gets called on state updates.

Changing time doesn't signify a state update.

Mutating objects inside state
-----------------------------

You must remember that can't mutate (update) objects inside the state.

.. code-block:: python

    state['numbers'] = [1, 2, 3]  # works

    state['numbers'].append(4)  # doesn't work

While this might look like a flaw of zproc (and it somewhat is),
you can see this as a feature. It will avoid you from

1. over-complicating your state. (Keeping the state as flat as possible is generally a good idea).
2. avoiding race conditions. (Think about the atomicity of ``state['numbers'].append(4)``).

The correct way to mutate objects inside the state, is to do them atomically,
which is to say using the :py:func:`~.atomic` decorator.

.. code-block:: python

    @zproc.atomic
    def add_a_number(state, to_add)
        state['numbers'].append(to_add)

    def my_process(state):
        add_a_number(state, 4)

It looks tedious at first,
but trust me when I say that you will rip your brains apart when you find out
that appending to lists in a dict is not atomic and try to do it safely with locks.

You can read more about :ref:`atomicity`.


A note on performance
---------------------

There is always a cost to safety.
You can write more performant code without zproc.

However, when you weigh in the safety and ease of use of zproc,
performance really falls short.

And it's not like zproc is slow, see for yourself - `async vs zproc <https://github.com/pycampers/zproc/blob/master/examples/async_vs_zproc.py>`_

Bottom line, minimizing the number of times your application accesses the state will
result in lean and fast code.
