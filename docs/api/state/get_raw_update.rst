It is preffereable to use :py:meth:`get_when` over this,
since it avoids common pitfalls associated with state-watching.

*This is an advanced API, and should be used with caution.*

Meant to be used a Context Manager.

.. code-block:: python

    with state.get_raw_update(identical_okay=True) as get:
         while True:
             before, after, identical = get()
             print("new update:", before, after, identical)

:param live:
    .. include:: /api/state/params/live.rst

:param timeout:
    .. include:: /api/state/params/timeout.rst

:param identical_okay:
    .. include:: /api/state/params/identical_okay.rst
