import secrets
from multiprocessing import Process, Event
from threading import Thread
from time import sleep
from pathlib import Path
import zmq


class ACTION:
    GET_STATE = 1
    SET_STATE = 2
    TERMINATE = 3
    STATE_RESPONSE = 4


class MSG:
    ACTION = secrets.token_urlsafe(5)
    UPDATE = secrets.token_urlsafe(5)
    STATE = secrets.token_urlsafe(6)


class ZeroState:
    def __init__(self, zmq_socket, state_event, is_child=False):
        self.sock = zmq_socket
        self.is_child = is_child
        self.state_event = state_event

        if not is_child:
            self._msg_thread = Thread(target=self._parent_mainloop, daemon=True)
            self._msg_thread.start()
            self._state = {}

    def _send_msg(self, msg):
        return self.sock.send_json(msg)

    def _recv_msg(self):
        return self.sock.recv_json()

    def _parent_mainloop(self):
        while True:
            msg = self._recv_msg()
            action = msg.get(MSG.ACTION)

            if action == ACTION.GET_STATE:
                self._send_msg({MSG.ACTION: ACTION.STATE_RESPONSE, MSG.STATE: self._state})

            elif action == ACTION.SET_STATE:
                self._state.update(msg.get(MSG.UPDATE))
                self.state_event.set()

            elif action == ACTION.TERMINATE:
                self.sock.close()
                break

    def set_state(self, update_dict=None, **kwargs):
        if update_dict:
            kwargs.update(update_dict)

        if self.is_child:
            self._send_msg({MSG.ACTION: ACTION.SET_STATE, MSG.UPDATE: kwargs})
        else:
            self._state.update(kwargs)
            self.state_event.set()

    def get_state(self, key=None):
        if self.is_child:
            self._send_msg({MSG.ACTION: ACTION.GET_STATE})
            data = self._recv_msg().get(MSG.STATE)
        else:
            data = self._state

        if key is not None:
            return data.get(key)
        else:
            return data

    def get_state_when_change(self):
        self.state_event.wait()
        self.state_event.clear()
        return self.get_state()

    def kill(self):
        self._send_msg({MSG.ACTION: ACTION.TERMINATE})


class ZeroProcess:
    def __init__(self, child_mainloop, props=None):
        assert callable(child_mainloop), "Mainloop must be a callable!"
        self.props = props
        self.child_mainloop = child_mainloop
        self._zstate = None
        self._proc = None
        self._state_event = Event()

        ipc_base_dir = Path().joinpath('/', 'tmp', 'zeroprocess')

        if not ipc_base_dir.exists():
            ipc_base_dir.mkdir()

        self._ipc_path = "ipc://" + str(ipc_base_dir) + secrets.token_urlsafe(5)
        self._zmq_ctx = zmq.Context()
        self._main_sock = self._zmq_ctx.socket(zmq.PAIR)

    @property
    def is_alive(self):
        return self._proc and self._proc.is_alive()

    def run(self):
        if self._proc is not None and self._proc.is_alive():
            print("ZeroProcess is already running!")
        else:
            self._proc = Process(target=self._mainloop, args=(self._ipc_path, self.props), daemon=True)
            sleep(0.5)
            self._proc.start()
            self._main_sock.connect(self._ipc_path)
            self._zstate = ZeroState(self._main_sock, self._state_event)

        return self, self._zstate

    def _mainloop(self, ipc_path, props):
        ctx = zmq.Context()
        child_sock = ctx.socket(zmq.PAIR)
        child_sock.bind(ipc_path)
        zstate = ZeroState(child_sock, self._state_event, is_child=True)

        self.child_mainloop(zstate, props)

    def kill(self):
        if self._proc is not None:
            self._proc.terminate()

        if self._zstate is not None:
            self._zstate.kill()

        self._main_sock.close()


def other_process(zstate, props):
    print('Other side got props:', props)
    print('From the other side:', zstate.get_state_when_change())


zproc, zstate = ZeroProcess(other_process).run()

zstate.set_state({'foo': 'bar'}, foobar='abcd')
print('From this side:', zstate.get_state())

input()
zproc.kill()
