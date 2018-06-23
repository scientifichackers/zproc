# ZProc - Process on steroids

##### Multi-Tasking how it should've been.

![ZProc logo](https://i.imgur.com/N0X6zl8.png)

> To make utterly perfect MT programs (and I mean that literally),
> we don't need mutexes, locks, or any other form of inter-thread
> communication except messages sent across ZeroMQ sockets.

P.S. ZProc is short for _Zero_ Process

**Behold, the power of ZProc:**

```python
import zproc

ctx = zproc.Context(background=True)
ctx.state["cookies"] = 0


@zproc.atomic
def eat_cookie(state):
    state["cookies"] -= 1
    print("nom nom nom")


@zproc.atomic
def bake_cookie(state):
    state["cookies"] += 1
    print("Here's a cookie!")


@ctx.call_when_change("cookies")
def cookie_eater(state):
    eat_cookie(state)


@ctx.processify()
def cookie_baker(state):
    for i in range(5):
        bake_cookie(state)
```

**output**

```
Here's a cookie!
Here's a cookie!
nom nom nom
Here's a cookie!
nom nom nom
Here's a cookie!
nom nom nom
Here's a cookie!
nom nom nom
nom nom nom
```

Notice how the outputs are asynchronous,
because the baker and eater run in different processes.

```
print(cookie_eater)
print(cookie_baker)
```

**output**

```
<ZeroProcess pid: 2555 target: <function cookie_eater at 0x7f5b4542c9d8> uuid: e74521ae-76ca-11e8-bd1f-7c7a912e12b5>
<ZeroProcess pid: 2556 target: <function cookie_baker at 0x7f5b4542c950> uuid: e74521ae-76ca-11e8-bd1f-7c7a912e12b5>
```

If two ZeroProcess instances have the same uuid, that means they share the same state.

## Install

`pip install zproc`

License: MIT License (MIT)<br>
Requires: Python >=3.5

## Documentation ( [![Documentation Status](https://readthedocs.org/projects/zproc/badge/?version=latest)](https://zproc.readthedocs.io/en/latest/?badge=latest) )

#### [Read the docs](http://zproc.readthedocs.io/en/latest/)

#### [Examples](examples)

## Backstory

Traditional Multi Processing involved _shared memory_ (global variables).<br>
However, it was proven that shared memory tends to _violate_ the laws of Physics.

[🔖](https://www.youtube.com/watch?v=bo5WL5IQAd0)
<- Joe Armstrong, the creator of Erlang.

The solution presented by Erlang, (and ZMQ) is the notion of
**message passing** for achieving parallelism.<br>
However, Message passing can be tedious, and often un-pythonic.

This is where ZProc comes in.

**It provides you a middle ground between message passing and shared memory.**

It does message passing, without you ever knowing that it's doing it.

It also borrows the concept of `state` and `props` from reactJS.

Hence, provides you a global `dict` called `state`.<br>
Each Process can also be supplied with some `props` that make processes re-usable.<br>
The `state` is **not** a shared object.<br>
It works _purely_ on message passing.

Unlike reactJS, you are free to mutate the state and ZProc won't sweat.

Behind the covers, it simulates the [Actor Model](https://en.wikipedia.org/wiki/Actor_model).<br>
ZProc doesn't blindly follow it, but you can think of it as such.

It also borrows the `autoretry` feature of Celery, but unlike
Celery it doesn't need a broker.

#### The zen of zero

> The Ø in ØMQ is all about trade-offs. On the one hand, this strange
> name lowers ØMQ’s visibility on Google and Twitter. On the other hand,
> it annoys the heck out of some Danish folk who write us things like
> “ØMG røtfl”, and “Ø is not a funny-looking zero!” and “Rødgrød med
> Fløde!” (which is apparently an insult that means “May your neighbours
> be the direct descendants of Grendel!”). Seems like a fair trade.

> Originally, the zero in ØMQ was meant to signify “zero broker” and
> (as close to) “zero latency” (as possible). Since then, it has come
> to encompass different goals: zero administration, zero cost, zero
> waste. More generally, “zero” refers to the culture of minimalism
> that permeates the project. We add power by removing complexity
> rather than by exposing new functionality.

## Features

-   🌠 &nbsp; Global State w/o shared memory

    -   Globally synchronized state (`dict`), without using shared memory.
    -   [🔖](#inner-workings)

-   🌠 &nbsp; Asynchronous paradigms without `async def`

    -   Build any combination of synchronous and asynchronous systems.
    -   _watch_ for changes in state, without
        [Busy Waiting](https://en.wikipedia.org/wiki/Busy_waiting).
    -   [🔖](http://zproc.readthedocs.io/en/latest/source/zproc.html#zproc.zproc.ZeroState)

-   🌠 &nbsp; Process management

    -   [Process Factory](http://zproc.readthedocs.io/en/latest/source/zproc.html#zproc.zproc.Context.process_factory)
    -   Remembers to kill processes when exiting, for general peace.
        (even when they're nested)
    -   Keeps a record of processes created using ZProc.
    -   [🔖](http://zproc.readthedocs.io/en/latest/source/zproc.html#zproc.zproc.Context)

-   🌠 &nbsp; Atomic Operations
    -   Perform an arbitrary number of operations on state as a single,
        atomic operation.
    -   [🔖](#atomicity)

## Caveats

-   The state only gets updated if you do it directly.<br>
    This means that if you mutate objects inside the state,
    they wont get reflected in the global state.
-   The state should be pickle-able
-   It runs an extra Process for managing the state.<br>
    Its fairly lightweight though, and shouldn't add too
    much weight to your application.

## FAQ

-   Fast?

    -   Above all, ZProc is written for safety and ease of use.
    -   However, since its written using ZMQ, it's plenty fast for most stuff.
    -   Run -> [🔖](eamples/async_vs_zproc.py) for a taste.

-   Stable?

    -   The code itself is stable, but the API is quite unstable.

-   Production ready?

    -   Please don't use it in production right now.

-   Real?

    -   YES. It works.
    -   [🔖](https://github.com/pycampers/muro)

-   Windows compatible?
    -   Probably?

## Inner Workings

-   Zproc uses a Server, which is responsible for storing and communicating the state.

    -   This isolates our resource (state), eliminating the need for locks.

-   The process(s) communicate through ZMQ sockets, over `ipc://`.

    -   The clients (Proceses) use a `ZMQ_DEALER` socket.
    -   The Server uses a `ZMQ_ROUTER` socket.

-   If a Process wishes to _watch_ the state, it subscribes to a global publish message.
    -   The zproc server publishes the state at every state update.
        (using `ZMQ_PUB` socket)
    -   A Process may subscribe to this message and
        filter out the event it needs (using `ZMQ_SUB` socket).
    -   zmq sockets block your application efficiently
        till an update occurs, eliminating the need for Busy Waiting.

(Busy waiting refers to the `while True: <check condition>` approach).

## Local development

```
git clone https://github.com/pycampers/zproc.git
cd zproc
pipenv install
```

## Build documentation

Assuming you have sphinx installed (Linux)

```
cd docs
pipenv run ./build.sh
```

## Thanks

-   Thanks to [pieter hintjens](http://hintjens.com/),
    for his work on the [ZeroMQ](http://zeromq.org/) library
    and for his [amazing book](http://zguide.zeromq.org/).
-   Thanks to [tblib](https://github.com/ionelmc/python-tblib),
    ZProc can raise First-class Exceptions from the zproc server!
-   Thanks to [psutil](https://github.com/giampaolo/psutil),
    ZProc can handle nested procesess!
-   Thanks to Kennith Rietz.
    His setup.py was used to host this project on pypi.
    Plus lot of documentation is blatantly copied
    from his documentation on requests

---

<a href="https://www.buymeacoffee.com/u75YezVri" target="_blank"><img src="https://www.buymeacoffee.com/assets/img/custom_images/black_img.png" alt="Buy Me A Coffee" style="height: auto !important;width: auto !important;" ></a>

[🐍🏕️](http://www.pycampers.com/)
