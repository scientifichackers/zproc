# ZProc - Process on steroids
##### Multi-Processing how it should've been.

ZProc is short for [Zero](http://zguide.zeromq.org/page:all#The-Zen-of-Zero) - [Process](https://docs.python.org/3.6/library/multiprocessing.html#multiprocessing.Process)

>generally, "zero" refers to the culture of minimalism that permeates the project. We add power by removing complexity rather than by exposing new functionality.

ZProc aims to reduce the pain of multi-processing with the aid of following -

- ☄️ Global State management
    - Literally allows you to use a global, shared, mutable, state object (`dict`) without having to worry about the atomicity of your operations and race conditions.
    - Made possible using the zproc server. Read [Inner Workings](https://github.com/pycampers/zproc#inner-workings) .

- ☄️ State synchronization
    - Sync-ing global state across all processes (without shared varialbes!)

- ☄️ Async/Synchronous paradims without `async def`
    - Give you the freedom to build any combination of synchronous and asynchronous systems.
    - Read [here](http://zproc.readthedocs.io/en/latest/source/zproc.html#zproc.zproc.ZeroState) for more. Basically,
    > Allows you to watch for changes in your state, without having to worry about irrelevant details

- ☄️ Process management
    - [Process Factory](http://zproc.readthedocs.io/en/latest/source/zproc.html#zproc.zproc.Context.process_factory)
    - Remembers to kill processes when exiting, for general peace.
    - Keeps a record of processes created using ZProc. Read [here](http://zproc.readthedocs.io/en/latest/source/zproc.html#zproc.zproc.Context) for more

- ☄️ Batch Operations
    - Allows you to perform a bunch of operations on state as a singe, atomic operation.
    - Read more [here](http://zproc.readthedocs.io/en/latest/source/zproc.html#zproc.zproc.ZeroState.lock_state) .


# Documentation

[Read the docs](http://zproc.readthedocs.io/en/latest/)


# Examples

The simplest way to see zproc in action is to skim through the examples:

They should be pretty self-explanatory. I am happy to make these examples better, since I use them as test-cases for testing ZProc.

These can be found under the `examples` directory.


# Is this
- production-ready?
    - No. But it will soon be!
    - I work on it regulary since its the backbone of a number of my own projects.
- fast?
    - plenty, since its written with ZMQ.
    - See `luck_test.py` example for a taste.
    - NOT enough for very large applications, but enough for small to medium sized applications.
- stable?
    - Mostly.
    - I tend to make some fast changes that end up breaking my code.
    - I am actively writing tests to help with this though.
- Real?
    - YES. It works. See it [here](https://github.com/pycampers/muro) in action.
- Windows / Mac compatible?
    - I honestly don't know. Please tell me.

# Inner Workings

- The process(s) communicate over zmq sockets, over `ipc://`.

- Zproc runs a zproc server, which is responsible for storing and managing the state.
    - update the state whenever another process updates it.
    - transmitt the state whenever a process needs to access it.

- Overall, the zproc server helps create an illusion of a global shared state when actually, it isn't shared at all!

- If a process wishes to synchronize at a certain condition, it can attach a handler to the zproc server.

    - The zproc server will check the condition on all state-changes.

    - If the condition is met, the zproc server shall open a tunnel to the application and send the state back.

    - zmq sockets block your application until that tunnel is opened.

# Caveats

- The state only gets updated if you do it directly. This means that if you mutate objects inside the state, they wont get updated in global state.

- It runs an extra daemonic server for managing the state. Its fairly lightweight though, and shouldn't add too much weight to your application.

- The state should be pickle-able

# Known issues

- Processes inside processes are known to create wierd behavior like
    - not being able to access state
    - not shutting down properly on exit


# Install
`pip install zproc  `

# Build documentation

assuming you have sphinx installed (Linux)
```
cd docs
./build.sh
```

# Thanks

- Thanks to [tblib](https://github.com/ionelmc/python-tblib) ZProc can raise First-class Exceptions from the zproc server!
