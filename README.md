<img src="https://i.imgur.com/sJARxXD.png" />

*ZProc lets you do shared-state multitasking without the perils of having shared-memory.*

**Behold, the power of ZProc:**

```python

# Some initialization
import zproc


ctx = zproc.Context(wait=True)  # wait for processes in this context
ctx.state["cookies"] = 0


# Define "atomic" operations

@zproc.atomic
def eat_cookie(state):
    """Eat a cookie."""
    
    state["cookies"] -= 1
    print("nom nom nom")


@zproc.atomic
def bake_cookie(state):
    """Bake a cookie."""
    state["cookies"] += 1
    print("Here's a cookie!")


# Fire up processes

@ctx.call_when_change('cookies')
def cookie_eater(_, state):
    """Eat cookies as they're baked."""
    
    eat_cookie(state)


for i in range(5):
    bake_cookie(ctx.state)
```

**Result:**

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

(baker and eater run in different processes)

## The core idea

ZProc tries to breathe new life into the archaic idea of shared-state multitasking by 
protecting application state with logic and reason. 

Shared state is frowned upon by almost everyone, 
(mostly) due to the fact that memory is inherently dumb.

Like memory doesn't really care who's writing to it.

ZProc's state tries to keep a track of who's doing what.

## The Goal

ZProc aims to make building multi-taking applications easier and faster for everyone, in a pythonic way.

It started out from the core idea of having a *smart* state -- 
eventually wanting to turn into a full-fledged framework for all things multitasking.

## Install

```
$ pip install zproc
``` 

**Or, from the development branch**

```
$ pip install git+https://github.com/pycampers/zproc.git@next#egg=zproc
```

License: MIT License (MIT)<br>
Requires: Python >=3.5

## Documentation ( [![Documentation Status](https://readthedocs.org/projects/zproc/badge/?version=latest)](https://zproc.readthedocs.io/) )

#### [Read the docs](http://zproc.readthedocs.io/en/latest/)

#### [Examples](examples)


## Features

- 🌠 &nbsp; Process management

    -   [Process Factory](https://zproc.readthedocs.io/en/latest/api.html#zproc.Context.process_factory)
    -   Remembers to kill processes when exiting, for general peace.
        (even when they're nested)
    -   Keeps a record of processes created using ZProc.
    -   [🔖](https://zproc.readthedocs.io/en/latest/api.html#context)

- 🌠 &nbsp; Process Maps
    
    - Automatically manages worker processes, and delegates tasks to them.
    -   [🔖](https://zproc.readthedocs.io/en/latest/api.html#context)    

- 🌠 &nbsp; Asynchronous paradigms without `async def`

    -   Build a combination of synchronous and asynchronous systems, with ease.
    -   By _watching_ for changes in state, without
        [Busy Waiting](https://en.wikipedia.org/wiki/Busy_waiting).
    -   [🔖](https://zproc.readthedocs.io/en/latest/api.html#state)
    
- 🌠 &nbsp; Atomic Operations
    -   Perform an arbitrary number of operations on state as a single,
        atomic operation.
    -   [🔖](https://zproc.readthedocs.io/en/latest/user/atomicity.html)

## Caveats

-   The state only gets updated if you do it directly.<br>
    This means that if you mutate objects inside the state,
    they wont get reflected in the global state.

-   The state should be pickle-able.

-   It runs an extra Process for managing the state.<br>
    Its fairly lightweight though, and shouldn't add too
    much weight to your application.

## FAQ

-   Fast?

    -   Above all, ZProc is written for safety and the ease of use.
    -   However, since its written using ZMQ, it's plenty fast for most stuff.
    -   Run -> [🔖](eamples/async_vs_zproc.py) for a taste.

-   Stable?

    -   Mostly. However, since it's still in the `0.x.x` stage, you can expect some API changes. 

-   Production ready?

    -   Please don't use it in production right now.

-   Windows compatible?

    -   Probably?
    
## Local development

```
git clone https://github.com/pycampers/zproc.git

cd zproc
pipenv install
pipenv install -d
 
pipenv shell

pip install -e .
pytest 
```

## Build documentation

Assuming you have sphinx installed (Linux)

```
cd docs
./build.sh 

./build.sh loop  # starts a build loop.
```

## ZProc in the wild

- [Oscilloscope](https://github.com/pycampers/oscilloscope)

- [Muro](https://github.com/pycampers/muro)

## Thanks

-   Thanks to [open logos](https://github.com/arasatasaygin/openlogos) for providing the wonderful ZProc logo.
-   Thanks to [pieter hintjens](http://hintjens.com/),
    for his work on the [ZeroMQ](http://zeromq.org/) library
    and for his [amazing book](http://zguide.zeromq.org/).
-   Thanks to [tblib](https://github.com/ionelmc/python-tblib),
    ZProc can raise First-class Exceptions from the zproc server!
-   Thanks to [psutil](https://github.com/giampaolo/psutil),
    ZProc can handle nested procesess!
-   Thanks to Kennith Rietz.
    His setup.py was used to host this project on pypi.
    Plus a lot of documentation structure is blatantly copied
    from his documentation on requests

---

ZProc is short for [Zero](http://zguide.zeromq.org/page:all#The-Zen-of-Zero) Process.

---

[🐍🏕️](http://www.pycampers.com/)
