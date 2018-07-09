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
and print out a message when the number of "cookies" is "5".

::

    state.get_when_equal('cookies', 5)
    print('5 cookies!')

There also these utility methods in py:class:`.Context`
that are just a wrapper over their counterparts in :py:class:`.State`.

- :py:meth:`~.Context.call_when_change`
- :py:meth:`~.Context.call_when`
- :py:meth:`~.Context.call_when_equal`
- :py:meth:`~.Context.call_when_not_equal`

These help you avoid writing the extra 5 lines of code.


.. _live-events:


Live-ness of events
-------------------

zproc provides 2 different "modes" for watching the state.

By default, the ``State.get_when*`` methods provide **live updates**,
while the ``Context.call_when*`` provide buffered updates.

------

When consuming live updates, Process **will miss events**, if it's not paying attention.

*like a live youtube video, you only see what's currently happening.*

For example -

::

    while True:
        print(state.get_when_change(live=True))

        sleep(5)


The above code will miss any updates that happen while it is sleeping (``sleep(5)``).

------

To modify this behaviour, you need to pass ``live=False``

::

    while True:
        print(state.get_when_change(live=False))

        sleep(5)


This way, the events are stored in a *buffer*,
so that your code **doesn't miss any events**.

*like a normal youtube video, where you won't miss anything, since it's buffering.*

------

Its easy to decide whether you need live updates or not.

- If you don't care about missing an update or two, and want the most up-to date state, use live mode.

- If you care about each state update, at the cost of speed, and the recency of the updates, don't use live mode.

Live mode is obviously faster (potentially), since it can miss an update or two,
which eventually trickles down to less computation.


------

*But a live youtube video can be buffered as well!*

Hence the need for a :py:meth:`~.State.go_live` method.

It *clears* the buffer, ignoring any previous events.

*That's somewhat like the "LIVE" button on a live stream, that skips ahead to the live broadcast.*


.. note::
    :py:meth:`~.State.go_live` only affects the behavior when ``live`` is set to ``False``.

    Has no effect when ``live`` is set to ``True``.

    A **live** state watcher is strictly **LIVE**.


Using these methods,
alongside the ``live`` parameter and :py:meth:`~.State.go_live` method,
one can create extremely simple looking, yet powerful applications.


Timeouts
--------

You can also provide timeouts while watching the state, using ``timeout`` parameter.

If an update occurs doesn't happen within the timeout, a ``TimeoutError`` is raised.

::

    try:
        print(state.get_when_change(timeout=5))  # wait 5 seconds for an update
    except TimeoutError:
        print('Waited too long!)




Button Press
------------

Let's take an example, to put what we learned into real world usage.

Here, we want to watch a button press, and determine whether it was a long or a short press.

It is assumed that the state is constantly updated with the value of button,
from another process, whose details are irrelevant.

We assume that the value of ``'button'`` is ``True``,
when the button is pressed, and ``False`` when it is not.

The ``Reader`` is any arbitrary source of a value, say a GPIO pin,
or socket sending the value of an IOT button.

::

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
    def handle_press(state):

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
and sometimes the application would lag behind the real world button state,

This behavior is undesirable when making Human computer interfaces.
Keeping stuff responsive is a priority.


(The above code is simplified version of the code `this <https://github.com/pycampers/muro>`_ project).
