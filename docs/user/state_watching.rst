.. _state_watching:

The magic of state watching
===========================
Watch the state for events, as-if you were watching a youtube video!

Basic stuff
-----------

State watching is primary method of synchronization in ZProc.

It boils down to these methods, in the :class:`.ZeroState` API.

- :func:`~zproc.zproc.ZeroState.get_when_change`
- :func:`~zproc.zproc.ZeroState.get_when`
- :func:`~zproc.zproc.ZeroState.get_when_equal`
- :func:`~zproc.zproc.ZeroState.get_when_not_equal`

All these methods have a common parameter, "live".

Friendly conversation with a Human
----------------------------------

By default, watchers provide **live events**,
such that, a Process **will miss events**, if it's busy doing work, while an update happens.

**Human:** So it's like a live youtube video, you only see what's currently happening.

To modify this behaviour, just pass ``live=False``, like so -

``state.get_when_change(live=False)``

| This way, the events are stored in a *buffer*,
| such that a Process **doesn't miss any events**, if it's busy doing work, while an update happens.

**Human:** So it's like a normal youtube video, where you won't miss anything, since it's buffering.

**Human:** Wait a second, a live youtube video can be buffered as well!

| Hence the need for a :func:`~zproc.zproc.ZeroState.go_live` method.
| It *clears* the buffer, deleting any previous events.

**Human:** Great, that's exactly like the **LIVE** button on my live stream, that makes it *skip ahead to the live broadcast*.

| P.S.
| It only affects a ``live=False`` state watcher.
| Has no effect on a ``live=True`` state watcher.
| A **live** state watcher is strictly **LIVE**.


Using these methods, alongside the ``live`` parameter and :func:`~zproc.zproc.ZeroState.go_live` method, one can create extremely simple looking, yet powerful applications.


