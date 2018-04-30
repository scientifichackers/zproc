# ZProc - Process on steroids
zproc is short for [Zero](http://zguide.zeromq.org/page:all#The-Zen-of-Zero) - [Process](https://docs.python.org/3.6/library/multiprocessing.html#multiprocessing.Process)

>generally, "zero" refers to the culture of minimalism that permeates the project. We add power by removing complexity rather than by exposing new functionality.

zproc aims to reduce the pain of multi-processing by

- 🌠
    - Sync-ing  application state across all processes (without shared varialbes!).
- 🌠
    - Giving you the freedom to build any combination of synchronous or asynchronous systems.
- 🌠
    - Remembers to kill processes when exiting, for general peace.

# Documentation

[Read the docs](http://zproc.readthedocs.io/en/latest/)


# Learning ZProc

The simplest way to learn zproc is to skim through the examples in following order:

- `simple_sync.py`
- `luck_test.py`

These can be found under the `examples` directory.

# Example
###### `state` is NOT a shared variable!. It's actually a remote object that is wrapped to behave like a dict.


```python
# example.py

from time import sleep

import zproc


def foo_equals_bar(state):
    return state.get('foo') == 'bar'


# define a child process
def child1(state, props):
    state.get_when_change('foo')  # wait for foo to change
    print("child1: foo got updated, so I wake")

    state['foo'] = 'bar'  # update bar
    print('child1: I set foo to bar')
    print('child1: I exit')


# define another child process
def child2(state, props):
    state.get_when(foo_equals_bar)  # wait for foo_equals_bar
    print('child2: foo changed to bar, so I wake')
    print('child2: I exit')


ctx = zproc.Context()  # create a context for us to work with

ctx.process_factory(child1, child2)  # give the context some processes to work with
ctx.start_all()  # start all processes in context

sleep(1)  # sleep for no reason

ctx.state['foo'] = 'foobar'  # set initial state
print('child0: I set foo to foobar')

input()  # wait for user input before exit

print('child0: I exit')
```

###### output
```
child0: I set foo to foobar
child1: foo got updated, so I wake
child1: I set foo to bar
child1: I exit
child2: foo changed to bar, so I wake
child2: I exit

child0: I exit
```

# Inner Workings

- The process(s) communicate over zmq sockets, over `ipc://`.

- Zproc runs a zproc server, which is responsible for storing and managing the state.

    - store the state whenever it is updated, by another process.

    - transmitt the state whenever a process needs to access it.

- If a process wishes to synchronize at a certain condition, it can attach a handler to the zproc server.

    - The zproc server will check the condition on all state-changes.

    - If the condition is met, the zproc server shall open a tunnel to the application and send the state back.

    - zmq sockets block your application until that tunnel is opened.

# Caveats

- The state only gets updated if you do it directly. This means that if you mutate objects in the state, they wont get updated in global state.

- It runs an extra daemonic server for managing the state. Its fairly lightweight though, and shouldn't add too much weight to your application.

- The state is required to be marshal compatible, which means:

> The following types are supported: booleans, integers, floating point numbers, complex numbers, strings, bytes, bytearrays, tuples, lists, sets, frozensets, dictionaries, and code objects, where it should be understood that tuples, lists, sets, frozensets and dictionaries are only supported as long as the values contained therein are themselves supported. The singletons None, Ellipsis and StopIteration can also be marshalled and unmarshalled

(from python [docs](https://docs.python.org/3/library/marshal.html))

# Known issues

- Processes inside processes are known to create wierd behavior like
    - not being able to access state
    - not shutting down properly on exit


# Install
`pip install zproc  `

# Build documentation

assuming you have sphinx installed
```
cd docs
./build.sh
```