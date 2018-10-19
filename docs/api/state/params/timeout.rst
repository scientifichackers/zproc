Sets the timeout in seconds.

If the value is ``None``, it will block until an update is available.

For all other values (``>=0``), it will wait for a state-change,
for that amount of time before returning with a ``TimeoutError``.