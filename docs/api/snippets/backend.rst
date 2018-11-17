The backend to use for launching the Processes.

For example, you may use :py:class:`threading.Thread` as the backend.

The ``backend`` must -

- Be a Callable.
- Accept ``target``, ``daemon``, ``args``, and ``kwargs`` as keyword arguments.

.. warning::

    Not guaranteed to work with anything other than :py:class:`multiprocessing.Process`.
