# zproc
zproc is short for [Zero](http://zguide.zeromq.org/page:all#The-Zen-of-Zero)Process

zproc aims to reduce the pain of multi-processing by

- 🌠
    - Managing application state for you across all processes
- 🌠
    - Giving you the freedom to build any combination of synchronous or asynchronous systems
- 🌠
    - Remembers to kill processes when exiting, for general peace

# Install
`pip install zproc`


# Enough talk, here's code

#### Set state from the current process, and see the state change in a completely separate process, in real-time
```
from zproc import ZeroProcess
from time import sleep


def other_process(zstate, props):
    print('got props:', props)
    print('other process:', zstate.get_state_when_change())


zproc, zstate = ZeroProcess(other_process).run()

zstate.set_state({'foo': 'bar'}, foobar='abcd')
print('this process:', zstate.get_state())

print('is alive:', zproc.is_alive)
print('pid:', zproc.pid)

sleep(1)

print('is alive:', zproc.is_alive)
```

###### output

```
this process: {'foobar': 'abcd', 'foo': 'bar'}
is alive: True
pid: 4827
got props: None
other process: {'foobar': 'abcd', 'foo': 'bar'}
is alive: False
```



#### same example, but done asynchronously

```
from zproc import ZeroProcess
from time import sleep


def other_process(zstate, props):
    print('got props:', props)
    print('other process: sleeping for 5 sec')
    sleep(5)
    print('other process:', zstate.get_state())


zproc, zstate = ZeroProcess(other_process).run()

zstate.set_state({'foo': 'bar'}, foobar='abcd')
print('this process:', zstate.get_state())
print('this process: sleeping for 10 sec')

sleep(10)

print('this process: exit')
```

##### output

```
got props: None
other process: sleeping for 5 sec
this process: {'foobar': 'abcd', 'foo': 'bar'}
this process: sleeping for 10 sec
other process: {'foobar': 'abcd', 'foo': 'bar'}
this process: exit
```