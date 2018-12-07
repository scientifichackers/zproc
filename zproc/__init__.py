from .__version__ import __version__
from .context import Context
from .exceptions import (
    ProcessWaitError,
    RemoteException,
    SignalException,
    ProcessExit,
    signal_to_exception,
    exception_to_signal,
    send_signal,
)
from .process import Process
from .server.tools import start_server, ping
from .state.state import State, atomic
from .task.result import SequenceTaskResult, SimpleTaskResult
from .task.swarm import Swarm
from .util import clean_process_tree, consume, create_ipc_address


@atomic
def increase(state, key, step=1):
    state[key] += step


@atomic
def decrease(state, key, step=1):
    state[key] -= step


@atomic
def append(state, key, item):
    state[key].append(item)
