from time import sleep

import zproc

ctx = zproc.Client()


@ctx.spawn(pass_state=False)
def my_process():
    sleep(1)

    try:
        raise ValueError("hello!")
    except Exception as e:
        print("encountered:", repr(e))

        # This serializes the current exception and sends it back to parent.
        return zproc.RemoteException()


sleep(5)

try:
    my_process.wait()  # waits for a return value from the process.
except Exception as e:
    print("caught it!", repr(e))
