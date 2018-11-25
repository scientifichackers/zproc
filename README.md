<img src="https://s3.ap-south-1.amazonaws.com/saral-data-bucket/misc/logo%2Btype%2Bnocatch.svg" />

**ZProc lets you do shared-state multitasking without the perils of having shared-memory.**

**Behold, the power of ZProc:**

```python
import zproc


@zproc.atomic
def eat_cookie(snap):
    """Eat a cookie."""
    snap["cookies"] -= 1
    print("nom nom nom")


@zproc.atomic
def bake_cookie(snap):
    """Bake a cookie."""
    snap["cookies"] += 1
    print("Here's a cookie!")


ctx = zproc.Context(wait=True)
state = ctx.create_state()
state["cookies"] = 0


@ctx.spawn
def cookie_eater(ctx):
    """Eat cookies as they're baked."""
    state = ctx.create_state()
    state["ready"] = True

    for _ in state.get_when_change("cookies"):
        eat_cookie(state)


next(state.get_when_available("ready"))
print(cookie_eater)

for _ in range(5):
    bake_cookie(state)
```

**Result:**

```
Process - pid: 10815 target: '__main__.cookie_eater' ppid: 10802 is_alive: True exitcode: None
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

ZProc aims to make building multi-taking applications easier
 and faster for everyone, in a pythonic way.

It started out from the core idea of having a *smart* state -- 
eventually wanting to turn into a full-fledged framework for all things 
multitasking.

## Install

[![PyPI](https://img.shields.io/pypi/pyversions/zproc.svg?style=for-the-badge)](https://pypi.org/project/zproc/)

```
$ pip install zproc
```

MIT License<br>
Python 3.5+  


## Documentation

[![Documentation Status](https://readthedocs.org/projects/zproc/badge/?version=latest)](https://zproc.readthedocs.io/)

[**Read the docs**](http://zproc.readthedocs.io/en/latest/)

[**Examples**](examples)


## Features

- 🌠 &nbsp; Process management   
    - Remembers to cleanup processes when exiting, for general peace. (even when they're nested)
    - Keeps a record of processes created using ZProc.
    - [🔖](https://zproc.readthedocs.io/en/latest/api.html#context)
       
    ```
    [ZProc] Cleaning up 'python' (13652)...
    ```
       
- 🌠 &nbsp; Worker/Process Maps   
    - Automatically manages worker processes, and delegates tasks to them.
    - [🔖](https://zproc.readthedocs.io/en/latest/api.html#context)    

- 🌠 &nbsp; [Communicating sequential processes](https://en.wikipedia.org/wiki/Communicating_sequential_processes), at the core.
    - No need for manual message passing.     
    - _Watch_ for changes in state, without [busy waiting](https://en.wikipedia.org/wiki/Busy_waiting).
    - [🔖](https://zproc.readthedocs.io/en/latest/api.html#state).

- Deterministic state updates. 
    - Ships with a event messaging system that doesn't rely on flaky PUB/SUB.
    - Go back in time, with a `TimeMachine`!. 
    
- Distributed, by default.
    - Scalable to multiple computers, with minimal refactoring.    
    
- 🌠 &nbsp; Atomic Operations
    - Perform an arbitrary number of operations on state as a single, atomic operation.
    - [🔖](https://zproc.readthedocs.io/en/latest/user/atomicity.html)

- 🌠 Detailed, humane error logging for Proceeses.
      
    ```
    [ZProc] Crash report:
      target: '__main__.p1'
      pid: 8959
      ppid: 8944
    
      Traceback (most recent call last):
        File "/home/dev/Projects/zproc/zproc/child.py", line 88, in main
          **self.target_kwargs
        File "/home/dev/Projects/zproc/zproc/child.py", line 65, in target_wrapper
          return self.target(*args, **kwargs)
        File "test.py", line 12, in p1
          raise ValueError
      ValueError 
    ```


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
    
-   Stable?

    -   Mostly. However, since it's still in its development stage, you should expect some API changes. 

-   Production ready?

    -   Please don't use it in production right now.

-   Windows compatible?

    -   Probably?
    
## Local development

```
# get the code
git clone https://github.com/pycampers/zproc.git

# install dependencies
cd zproc
pipenv install
pipenv install -d

# activate virtualenv
pipenv shell

# install zproc, and run tests
pip install -e .
pytest 
```

## Build documentation

```
cd docs
./build.sh 

# open docs
google-chrome _build/index.html 

# start a build loop
./build.sh loop  
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
