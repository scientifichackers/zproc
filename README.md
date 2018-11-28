<img src="https://s3.ap-south-1.amazonaws.com/saral-data-bucket/misc/logo%2Btype%2Bnocatch.svg" />

ZProc is a thought experiment, in making multi-tasking easier and accessible to everyone.

It focuses on automating various tasks related to message passing systems, for pythonistas.
The eventual goal is to make Python a first-class language for doing multi-tasking.

So that _you_ don't have to think about arcane details, 
like request-reply loops, reliable pub-sub, that kind of thing...  


**Behold, the power of ZProc:**

```python
import zproc


@zproc.atomic
def eat_cookie(snap):
    snap["cookies"] -= 1
    print("nom nom nom")


@zproc.atomic
def bake_cookie(snap):
    snap["cookies"] += 1
    print("Here's a cookie!")


def cookie_eater(ctx):
    state = ctx.create_state()
    it = state.get_when_change("cookies", count=5)
    state['ready'] = True
    
    for _ in it:
        eat_cookie(state)


# boilerplate
ctx = zproc.Context(wait=True)
state = ctx.create_state({"cookies": 0})

# create a ready handle
ready = state.get_when_available("ready")

# spwan the process
proc = ctx.spawn(cookie_eater)
print(proc)

# wait for ready
next(ready)

# bake some!
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

Message passing is cumbersome, error prone, and tedius --
 because there is a lot of manual wiring involved. 

The idea behind this project is to provide a pythonic API over widely accepted models in the multi-tasking realm. 

It started out with embracing shared state (but not shared memory).

Shared state is frowned upon by almost everyone, due to the fact that memory is inherently dumb.
Memory doesn't really care who's writing to it.
ZProc's state keeps a track of who's doing what.

It then evolved to do handle exceptions across processes, failover, worker swarms, event sourcing and other very useful features realated to multi-tasking. 

Finally, this one quote from Joe Armstrong,

> I want one way to program computers, not two.

Inspired me to keep the underlying architecture 100% message passing based,
and hence scalable across many computers, 
with minimal modifications to the user code.

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


## Wishlist

Here are some of the ideas that I wish were implemented in ZProc, but currently aren't.

- Redundant state-servers -- automatic selection/fallback.
- Green, Erlang-style processes. (requires Cpython internals)
- Process *links*, that automatically propagate errors across processes.
- Make namespaces horizontally scalable. 

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
