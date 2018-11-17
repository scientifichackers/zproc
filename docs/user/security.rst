.. _security:

Security considerations
=======================

Cryptographic signing
---------------------

Why?
++++

Since un-pickling from an external source is considered dangerous,
it becomes necessary to verify whether the other end is also a ZProc node,
and not some attacker trying to exploit our application.

Hence, ZProc provides cryptographic signing support using `itsdangerous <https://pythonhosted.org/itsdangerous/>`_.

Just provide the `secret_key` parameter to :py:class:`.Context`, and you should be good to go!

>>> import zproc
>>> ctx = zproc.Context(secret_key="muchsecret")
>>> ctx.secret_key
'muchsecret'

Similarly, :py:class:`.State` also takes the ``secret_key`` parameter.

By default, ``secret_key`` is set to ``None``, which implies that no cryptographic signing is performed.

Yes, but why?
+++++++++++++

Here is an example demonstrating the usefulness of the this feature.


.. code-block:: python

    import zproc

    home = zproc.Context(secret_key="muchsecret")
    ADDRESS = home.address

    home.state['gold'] = 5


An attacker somehow got to know our server's address.
But since his secret key didn't match ours, their attempts to connect our server are futile.

.. code-block:: python

    attacker = zproc.Context(ADDRESS) # blocks forever


If however, you tell someone the secret key, then they are allowed to access the state.

.. code-block:: python

    friend = zproc.Context(ADDRESS, secret_key="muchsecret")
    print(friend.state['gold'])  # 5
