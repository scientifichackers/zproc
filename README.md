# ZProc - Process on steroids
zproc is short for [Zero](http://zguide.zeromq.org/page:all#The-Zen-of-Zero) - [Process](https://docs.python.org/3.6/library/multiprocessing.html#multiprocessing.Process)

zproc aims to reduce the pain of multi-processing by

- 🌠
    - Managing application state for you across all processes (without sharing memory!)
- 🌠
    - Giving you the freedom to build any combination of synchronous or asynchronous systems wihtout changing your code too much.
- 🌠
    - Remembers to kill processes when exiting, for general peace.


### Inner Workings

- The process(s) communicate over zmq sockets, over `ipc://`.

- The parent process has its own Process attached; responsible for the following

    - storing the state whenever it is updated, by another process.

    - transmitting the state whenever a process needs to access it.

- If a process wishes to synchronize at a certain condition, it can attach a handler to the zproc daemon.

    - The zproc daemon will check the condition on all state-changes.

    - If the condition is met, the zproc daemon shall open a tunnel to the application and send the state back.

    - zmq already has the mechanisms to block your application untill that tunnel is opened.

### Caveats

- It runs an extra daemonic process for managing the state. Its fairly lightweight though, and shouldn't add too much weight to your application.

- The state is required to be marshal compatible, which means:

> The following types are supported: booleans, integers, floating point numbers, complex numbers, strings, bytes, bytearrays, tuples, lists, sets, frozensets, dictionaries, and code objects, where it should be understood that tuples, lists, sets, frozensets and dictionaries are only supported as long as the values contained therein are themselves supported. The singletons None, Ellipsis and StopIteration can also be marshalled and unmarshalled

(from python [docs](https://docs.python.org/3/library/marshal.html))

### Known issues

- Processes inside processes are known to create wierd behavior like
    - not being able to access state
    - not shutting down properly on exit


# Install
`pip install zproc`


<!-- # Short Introduction -->

<!-- Context -->

<!-- zproc provides you with a state object (ZeroState), which gives you a dict-like interface to the state. -->

<!-- from -->


<!-- #### Set state from the current process, and see the state change in a completely separate process, in real-time -->
<!-- ``` -->
<!-- from zproc import ZeroProcess -->
<!-- from time import sleep -->


<!-- def other_process(zstate, props): -->
<!-- print('got props:', props) -->
<!-- print('other process:', zstate.get_state_when_change()) -->


<!-- zproc, zstate = ZeroProcess(other_process).start() -->

<!-- zstate.set_state({'foo': 'bar'}, foobar='abcd') -->
<!-- print('this process:', zstate.get_state()) -->

<!-- print('is alive:', zproc.is_alive) -->
<!-- print('pid:', zproc.pid) -->

<!-- sleep(1) -->

<!-- print('is alive:', zproc.is_alive) -->
<!-- ``` -->

<!-- ###### output -->

<!-- ``` -->
<!-- this process: {'foobar': 'abcd', 'foo': 'bar'} -->
<!-- is alive: True -->
<!-- pid: 4827 -->
<!-- got props: None -->
<!-- other process: {'foobar': 'abcd', 'foo': 'bar'} -->
<!-- is alive: False -->
<!-- ``` -->



<!-- #### same example, but done asynchronously -->

<!-- ``` -->
<!-- from zproc import ZeroProcess -->
<!-- from time import sleep -->


<!-- def other_process(zstate, props): -->
<!-- print('got props:', props) -->
<!-- print('other process: sleeping for 5 sec') -->
<!-- sleep(5) -->
<!-- print('other process:', zstate.get_state()) -->


<!-- zproc, zstate = ZeroProcess(other_process).start() -->

<!-- zstate.set_state({'foo': 'bar'}, foobar='abcd') -->
<!-- print('this process:', zstate.get_state()) -->
<!-- print('this process: sleeping for 10 sec') -->

<!-- sleep(10) -->

<!-- print('this process: exit') -->
<!-- ``` -->

<!-- ###### output -->

<!-- ``` -->
<!-- got props: None -->
<!-- other process: sleeping for 5 sec -->
<!-- this process: {'foobar': 'abcd', 'foo': 'bar'} -->
<!-- this process: sleeping for 10 sec -->
<!-- other process: {'foobar': 'abcd', 'foo': 'bar'} -->
<!-- this process: exit -->
<!-- ``` -->