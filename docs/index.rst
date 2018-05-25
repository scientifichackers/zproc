ZProc: Process on steroids
=================================



.. image:: https://img.shields.io/badge/pip-0.3.1-blue.svg?longCache=true&style=for-the-badge
    :alt: PyPI
    :target: https://pypi.org/project/zproc/

.. image:: https://img.shields.io/badge/python-3.5%2C%203.6-blue.svg?style=for-the-badge
    :alt: PyPI - Python Version
    :target: https://pypi.org/project/zproc/

.. image:: https://img.shields.io/github/license/mashape/apistatus.svg?style=for-the-badge
    :alt: license
    :target: https://github.com/pycampers/zproc/blob/master/LICENSE



---------------


.. toctree::
    :maxdepth: 2

    source/modules.rst


Small Introduction
##################

.. code-block:: python
   :emphasize-lines: 5,9,12,13,20

    from time import sleep

    import zproc

    ctx = zproc.Context()
    ctx.state['cookies'] = 0


    @ctx.processify()
    def cookie_eater(state):
        while True:
            cookies = state.get_when_change('cookies')
            state['cookies'] = cookies - 1
            print('eater: I ate a cookie!')


    sleep(.5)

    for i in range(5):
        ctx.state['cookies'] += 1
        print('main: I made a cookie!')
        sleep(.5)

    sleep(.5)


``Output`` ::

    main: I made a cookie!
    eater: I ate a cookie!
    main: I made a cookie!
    eater: I ate a cookie!
    main: I made a cookie!
    eater: I ate a cookie!
    main: I made a cookie!
    eater: I ate a cookie!
    main: I made a cookie!
    eater: I ate a cookie!


-------------------------------------------------------------------

`More Examples <https://github.com/pycampers/zproc/tree/master/examples>`_  like this one.


Indicies
========
* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`


