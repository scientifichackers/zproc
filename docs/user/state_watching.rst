.. _state-watching:

The magic of state watching
===========================
**Watch the state for events, as-if you were watching a youtube video!**


zproc allows you to "watch" the state using these methods.

- :py:meth:`~.ZeroState.get_when_change`
- :py:meth:`~.ZeroState.get_when`
- :py:meth:`~.ZeroState.get_when_equal`
- :py:meth:`~.ZeroState.get_when_not_equal`

Essentially, they allow you to wait for updates in the state.

For example, the following code will watch the state,
and print out a message when the number of "cookies" is "5".

::

    state.get_when_equal('cookies', 5)
    print('5 cookies!')


.. _live-events:

Live events
-----------

By default, watchers provide **live events**.

So, a Process **will miss events**, if it's not paying attention.

*like a live youtube video, you only see what's currently happening.*

To modify this behaviour, pass ``live=False``, like so -

``state.get_when_change(live=False)``

This way, the events are stored in a *buffer*,
so that a Process **doesn't miss any events**.

*like a normal youtube video, where you won't miss anything, since it's buffering.*

*Wait a second, a live youtube video can be buffered as well!*

Hence the need for a :py:meth:`~.ZeroState.go_live` method.

It *clears* the buffer, deleting any previous events.

*That's somewhat like the **LIVE** button on a live stream, that makes it **skip ahead to the live broadcast**.*

.. note::
    :py:meth:`~.ZeroState.go_live` only affects the behavior of a ``live=False`` state watcher.

    Has no effect on a ``live=True`` state watcher.

    A **live** state watcher is strictly **LIVE**.


Using these methods,
alongside the ``live`` parameter and :py:meth:`~.ZeroState.go_live` method,
one can create extremely simple looking, yet powerful applications.


