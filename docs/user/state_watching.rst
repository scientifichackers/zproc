.. _state-watching:

The magic of state watching
===========================
**Watch the state for events, as-if you were watching a youtube video!**


zproc allows you to "watch" the state using these methods, using the :py:class:`.State` API.

- :py:meth:`~.State.get_when_change`
- :py:meth:`~.State.get_when`
- :py:meth:`~.State.get_when_equal`
- :py:meth:`~.State.get_when_not_equal`

Essentially, they allow you to wait for updates in the state.

For example, the following code will watch the state,
and print out a message when the price of gold is below 40$.

.. code-block:: python

    price = state.get_when(lamba state: state['gold_price'] < 40)

    print('"gold_price" is below 40$ !:', price)

There also these utility methods in :py:class:`.Context` that are just a wrapper
over their counterparts in :py:class:`.State`.

- :py:meth:`~.Context.call_when_change`
- :py:meth:`~.Context.call_when`
- :py:meth:`~.Context.call_when_equal`
- :py:meth:`~.Context.call_when_not_equal`


These help you avoid writing the extra 5 lines of code.

For example, the function ``want_pizza()`` will be called every-time the ``"num_pizza"`` key in the state changes.

.. code-block:: python

    @ctx.call_when_change("num_pizza")
    def want_pizza(num_pizza, state):
        print("pizza be tasty!", num_pizza)


.. _live-events:


Live-ness of events
-------------------

zproc provides 2 different "modes" for watching the state.

By default, all state watchers will provide **live updates**.

Let us see what that exactly means, in detail.


Peanut generator
++++++++++++++++


First, let us create a :py:class:`~Process` that will generate some peanuts, periodically.

.. code-block:: python

    from time import sleep
    import zproc


    ctx = zproc.Context()
    state = ctx.state

    state["peanuts"] = 0


    @zproc.atomic
    def inc_peanuts(state):
        state['peanuts'] += 1

    @ctx.process
    def peanut_gen(state):
        while True:
            inc_peanuts(state)
            sleep(1)



Live consumer
+++++++++++++

.. code-block:: python

    while True:
        num = state.get_when_change("peanuts", live=True)
        print("live consumer got:", num)

        sleep(2)

The above code will miss any updates that happen while it is sleeping (``sleep(5)``).

When consuming live updates, your code **can miss events**, if it's not paying attention.

*like a live youtube video, you only see what's currently happening.*

Buffered consumer
+++++++++++++++++

To modify this behaviour, you need to pass ``live=False``.

.. code-block:: python

    while True:
        num = state.get_when_change("peanuts", live=False)
        print("non-live consumer got:", num)

        sleep(2)

This way, the events are stored in a *buffer*,
so that your code **doesn't miss any events**.

*like a normal youtube video, where you won't miss anything, since it's buffering.*

Hybrid consumer
+++++++++++++++

*But a live youtube video can be buffered as well!*

Hence the need for a :py:meth:`~.State.go_live` method.

It *clears* the buffer, ignoring any previous events.

*That's somewhat like the "LIVE" button on a live stream, that skips ahead to the live broadcast.*


.. code-block:: python

    while True:
        num = state.get_when_change("peanuts", live=False)
        print("hybrid consumer got:", num)

        state.go_live()

        sleep(2)


.. note::
    :py:meth:`~.State.go_live` only affects the behavior when ``live`` is set to ``False``.

    Has no effect when ``live`` is set to ``True``.

    A **live** state watcher is strictly **LIVE**.


Using these methods,
alongside the ``live`` parameter and :py:meth:`~.State.go_live` method,
one can create extremely simple looking, yet powerful applications.

*A Full Example is available* `here. <https://github.com/pycampers/zproc/blob/master/examples/peanut_processor.py>`_


Decision making
+++++++++++++++

Its easy to decide whether you need live updates or not.

- If you don't care about missing an update or two, and want the most up-to date state, use live mode.

- If you care about each state update, at the cost of speed, and the recency of the updates, don't use live mode.

Live mode is obviously faster (potentially), since it can miss an update or two,
which eventually trickles down to less computation.


Timeouts
--------

You can also provide timeouts while watching the state, using ``timeout`` parameter.

If an update doesn't occur within the timeout, a ``TimeoutError`` is raised.

.. code-block:: python

    try:
        print(state.get_when_change(timeout=5))  # wait 5 seconds for an update
    except TimeoutError:
        print('Waited too long!)




Button Press
------------

Let's take an example, to put what we learned into real world usage.

Here, we want to watch a button press, and determine whether it was a long or a short press.

Some assumptions:

- If the value of ``'button'`` is ``True``, the the button is pressed
- If the value of ``'button'`` is ``False``, the button is not pressed.
- The ``Reader`` is any arbitrary source of a value, e.g. a GPIO pin or a socket connection, receiving the value from an IOT button.

.. code-block:: python

    @ctx.process
    def reader(state):
        # reads the button value from a reader and stores it in the state

        reader = Reader()
        old_value = None

        while True:
            new_value = reader.read()

            # only update state when the value changes
            if old_value != new_value:
                state['button'] = new_value
                old_value = new_value



    # calls handle_press() whenever button is pressed
    @ctx.call_when_equal('button', True, live=True)
    def handle_press(_, state):  # The first arg will be the value of "button". We don't need that.

        print("button pressed")

        try:
            # wait 0.5 sec for a button to be released
            state.get_when_equal('button', False, timeout=0.5)

            print('its a SHORT press')

        # give up waiting
        except TimeoutError as e:

            print('its a LONG press')

            # wait infinitely for button to be released
            state.get_when_equal('button', False)

        print("button is released")


Here, passing ``live=True`` makes sense, since we don't care about a missed button press.

It makes the software respond to the button in real-time.

If ``live=False`` was passed, then it would not be real-time,
and sometimes the application would lag behind the real world button state.

This behavior is undesirable when making Human computer interfaces,
where keeping stuff responsive is a priority.


(The above code is simplified version of the code used in `this <https://github.com/pycampers/muro>`_ project).
