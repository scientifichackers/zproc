# zproc
zproc is short for [Zero](http://zguide.zeromq.org/page:all#The-Zen-of-Zero)Process

zproc aims to reduce the pain of multi-processing by

- 🌠
    - Managing application state for you across all processes
- 🌠
    - Giving you the freedom to build any combination of synchronous or asynchronous systems

# Enough talk, here's code

### Exhibit A
#### Set state from the current process, and see the state change in a completely separate process, in real-time
```
from zproc import ZeroProcess

def other_process(zstate, props):
    print('Other side got props:', props)
    print('From the other side:', zstate.get_state_when_change())


zproc, zstate = ZeroProcess(other_process).run()

zstate.set_state({'foo': 'bar'}, foobar='abcd')
print('From this side:', zstate.get_state())

input()
zproc.kill()

```
### Exhibit B
#### same example, but the other way round!
```
from zproc import ZeroProcess

def other_process(zstate, props):
    print('Other side got props:', props)

    zstate.set_state({'foo': 'bar'}, foobar='abcd')
    print('From this side:', zstate.get_state())


zproc, zstate = ZeroProcess(other_process, props='hello there!').run()

print('From the other side:', zstate.get_state_when_change())

input()
zproc.kill()
```
