QuickStart
==========

A :py:class:`.Context` is the most obvious way to launch processes with zproc.

It provides a convenient wrapper around ``multiprocessing.Process``
and also does the hard work of managing your state.

Here is how we get a :py:class:`.Context`

::

    import zproc

    ctx = zproc.Context()


Lets launch a process that does nothing

::

    def my_process(state):
        pass

    ctx.process(my_process)

The :py:meth:`~.Context.process` will launch a process, and provide it with ``state``.

If you like to be cool like me, then you can use it as a decorator.

::

    @ctx.process()
    def my_process(state):
        pass


The ``state`` is a *dict-like* object that you can use to represent your application's state.

You can also access it from the context (``ctx.state``).

I say *dict-like*, because it's not exactly a dict.
It just implements the ``dict`` methods, so that you can conveniently access the state.

So while you can do

::

    state['apples'] = 5

    state.get('apples')

    state.setdefault('apples', 10)

    ...

You can't mutate (update) objects inside the state.

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

.. note::
    There is always a cost to safety.
    You can write more performant code without zproc.

    However, when you weigh in the safety and ease of use of zproc,
    performance really falls short.

    And it's not like zproc is slow, see for yourself:
    `async vs zproc <https://github.com/pycampers/zproc/blob/master/examples/async_vs_zproc.py>`_


    (plus, this next bit is surely faster with zproc)

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

And from there on, you try to manage the time for which your application sleeps
until you finally give up getting to the sweet spot, and switch to zproc.

::

    def my_process(state):
        state.get_when_equal('cookies', 5)
        print('done with zproc!')

This eats very little to no CPU, and is fast enough for my (and probably your) needs.

Best part is that it doesn't do any of that expensive "busy" waiting.
Like underneath, it's actually a socket connecting waiting for a request.