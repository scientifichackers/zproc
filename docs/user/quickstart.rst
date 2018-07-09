QuickStart
==========

The whole architecture of zproc is built around a :py:class:`.State` object.

A :py:class:`.Context` is a convenient wrapper over :py:class:`.Process` and :py:class:`.State`.

A :py:class:`.Context` is the most obvious way to launch processes with zproc.

Each :py:class:`.Context` has its own isolated state that is accessible
by that context's processes.

Let's get down to it then.

::

    import zproc

    ctx = zproc.Context()


Lets launch a process that does nothing

::

    def my_process(state):
        pass

    ctx.process(my_process)

The :py:meth:`~.Context.process` will launch a process, and provide it with ``state``.

If you like to be cool, then you can use it as a decorator.

::

    @ctx.process
    def my_process(state):
        pass


The ``state`` is a *dict-like* object that you can use to represent your application's state.

You can also access it from the :py:class:`.Context` itself using ``ctx.state``.

*dict-like*, because it's not exactly a dict.
It implements the ``dict`` methods, so that you can conveniently access the state.

::

    state['apples'] = 5

    state.get('apples')

    state.setdefault('apples', 10)

    ...


Reactive programming with zproc
-------------------------------

Now, let us uncover "reactive" part of zproc.

I like to call it :ref:`state-watching`.

state watching allows you to react to some change in the state in an efficient way.

Lets say, you want to wait for the number of "cookies" to be "5".

Normally, you might do it with something like this:

::

    while True:
        if cookies == 5:
            print('done!')
            break

But then you find out that this eats too much CPU, and put put some sleep.

::

    from time import sleep

    while True:
        if cookies == 5:
            print('done!')
            break
        sleep(1)

And from there on, you try to manage the time for which your application sleeps ( to arrive at a sweet spot).

zproc provides an elegant, easy to use solution for this problem.

::

    def my_process(state):
        state.get_when_equal('cookies', 5)
        print('done with zproc!')

This eats very little to no CPU, and is fast enough for almost everyone needs.

You must realise that this doesn't do any of that expensive "busy" waiting.
Under the covers, it's actually a socket connecting waiting for a request.

If you want, you can even provide a function:

::

    def my_process(state):
        state.get_when(lambda state: state.get('cookies') == 5)


The function you provide will get called on each state update,
to check whether the return value is True-like.

You obviously can't do things like this:

::

    from time import time

    t = time()
    state.get_when(lambda state: time() > t + 5)  # wrong!

The function gets called on state updates.

Changing time doesn't signify a state update.

Mutating objects inside state
-----------------------------

You must remember that can't mutate (update) objects inside the state.

::

    state['numbers'] = [1, 2, 3]  # works

    state['numbers'].append(4)  # doesn't work

While this might look like a flaw of zproc (and it somewhat is),
you can see this as a feature. It will avoid you from

1. over-complicating your state. (Keeping the state as flat as possible is generally a good idea).
2. avoiding race conditions. (Think about the atomicity of ``state['numbers'].append(4)``).

The correct way to mutate objects inside the state, is to do them atomically,
which is to say using the :py:func:`~.atomic` decorator.

::

    zproc.atomic()
    def add_a_number(state, to_add)
        state['numbers'].append(to_add)

    def my_process(state):
        add_a_number(state, 4)

It looks tedious at first,
but trust me when I say that you will rip your brains apart when you find out
that appending to lists in a dict is not atomic and try to do it safely with locks.

You can read more about :ref:`atomicity`.

Performance
-----------

There is always a cost to safety.
You can write more performant code without zproc.

However, when you weigh in the safety and ease of use of zproc,
performance really falls short.

And it's not like zproc is slow, see for yourself:
`async vs zproc <https://github.com/pycampers/zproc/blob/master/examples/async_vs_zproc.py>`_

Bottom line, minimizing the number of times your application accesses the state will
result in lean and fast code.
