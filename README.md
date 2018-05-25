# ZProc - Process on steroids
##### Multi-Processing how it should've been.

If you're wondering, ZProc is short for _Zero_ Process


### Philosophy
#### History
Traditional Multi Processing was mostly, built on the principle of _shared memory_.  
This might sound odd, but shared memory ___violates_ the laws of Physics itself__.  
Don't believe me? [watch this](https://www.youtube.com/watch?v=bo5WL5IQAd0) (from Joe Armstrong, the creator of Erlang)  

The solution presented by Erlang, (and ZMQ) is the notion of __message passing__ for achieving parallelism, or at least concurrency.  
[Yes, they are different things](https://joearms.github.io/published/2013-04-05-concurrent-and-parallel-programming.html).

#### Now

Message passing can be tedious, and often un-pythonic.  
This is where ZProc comes in.  

__It provides a middle ground between message passing and shared memory.__

It does message passing, without you ever knowing that it's doing it.  
It provides you a global `dict` which we like to call `state`.  
The `state` is not shared memory, and works _purely_ on message passing.

If you're a CS majaor, you might recognize this as the [Actor Model](https://en.wikipedia.org/wiki/Actor_model).  
ZProc doesn't blindly follow it, but it you can think of it as such.

#### The zen of zero

> generally, "zero" refers to the culture of minimalism that permeates the project. We add power by removing complexity rather than by exposing new functionality.

## Install
`pip install zproc`

License: MIT License (MIT)  
Requires: Python >=3.5      

## Documentation
[Read the docs](http://zproc.readthedocs.io/en/latest/)

## [Examples](examples)

A great way to see zproc in action is through the examples  
They should be pretty self-explanatory.  

[🔖](examples)  


## Features

- 🌠 &nbsp; Global State
    - Globally synchronized state (`dict`), without using shared memory.
    - [🔖](#inner-workings)

- 🌠 &nbsp; Asynchronous paradigms without `async def`
    - Build any combination of synchronous and asynchronous systems.
    - _watch_ for changes in state, without [Busy Waiting](https://en.wikipedia.org/wiki/Busy_waiting).
    - [🔖](http://zproc.readthedocs.io/en/latest/source/zproc.html#zproc.zproc.ZeroState)

- 🌠 &nbsp; Process management
    - [Process Factory](http://zproc.readthedocs.io/en/latest/source/zproc.html#zproc.zproc.Context.process_factory)
    - Remembers to kill processes when exiting, for general peace. (even when they're nested)
    - Keeps a record of processes created using ZProc.
    - [🔖](http://zproc.readthedocs.io/en/latest/source/zproc.html#zproc.zproc.Context)

- 🌠 &nbsp; Atomic Operations
    - Perform an arbitrary number of operations on state as a single, atomic operation.
    - [🔖](#atomicity)

## Atomicity
###### The elephant in the room, race-conditions.

In ZProc world, a single dict operation is __guaranteed™__ to be atomic.

But, in real world applications require arbitrary number of operations to be atomic.   

__Exhibit A__

```python
def increment(step):
    state.count += step

increment(5)
```

`increment()` might look like a single operation, but don't get fooled! (They're 2)

1. `__getitem__`  -> get `'count'` 

2. `__setitem__`  -> set `'count'` to `<count> + 1`

`__getitiem__` and `__setitem__` are __guarateed™__ to be atomtic on their own, but NOT in conjunction. 

If these operations are not done atomically,
it exposes the possiblity of other Processes trying to do operations between "1" and "2"


Clearly, a remedy is required.

---
With ZProc, it's dead simple. 

Let's make some changes to our example..
```python
@state.atomify()
def increment(state, step):
    state.count += step

increment(5)
```


If it wasn't clear, `@state.atomify()` makes any arbitrary function, an atomic operation on the state.  

[🔖](#atomicity)

## Caveats

- The state only gets updated if you do it directly. This means that if you mutate objects inside the state, they wont get updated in global state.
- It runs an extra daemonic server for managing the state. Its fairly lightweight though, and shouldn't add too much weight to your application.
- The state should be pickle-able
- Missing state updates when using `state.get_when_*`, if updates are too fast.
    - Current API is not intended for this type of use-case.
    - Work is being done to expose new API that will allow you to watch for every singe update, no matter when they occur

## FAQ
- fast?
    - plenty, since its written with ZMQ.
    - See `luck_test.py` example for a taste.
- stable?
    - The project itself is stable, but the API is NOT.
- real?
    - YES. It works. 
    - [🔖](https://github.com/pycampers/muro)
- Windows / Mac compatible?
    - I honestly don't know. Please tell me.

## Inner Workings

- The process(s) communicate over zmq sockets, over `ipc://`.

- Zproc runs a zproc server, which is responsible for storing and managing the state.
    - update the state whenever another process updates it.
    - transmit the state whenever a process needs to access it.

- Overall, the zproc server helps create an illusion of a global shared state when actually, it isn't shared at all!

- If a process wishes to synchronize at a certain condition, it can attach a handler to the zproc server.
    - The zproc server will check the condition on all state-changes.
    - If the condition is met, the zproc server shall open a tunnel to the application and send the state back.
    - zmq sockets block your application until that tunnel is opened.

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
- Thanks to [pieter hintjens](http://hintjens.com/), for his work on the [ZeroMQ](http://zeromq.org/) library and for his [amazing book](http://zguide.zeromq.org/).
- Thanks to [tblib](https://github.com/ionelmc/python-tblib), ZProc can raise First-class Exceptions from the zproc server!
- Thanks to [psutil](https://github.com/giampaolo/psutil), ZProc can handle nested procesess!

---

<a href="https://www.buymeacoffee.com/u75YezVri" target="_blank"><img src="https://www.buymeacoffee.com/assets/img/custom_images/black_img.png" alt="Buy Me A Coffee" style="height: auto !important;width: auto !important;" ></a>


🐍🏕️

