import struct
from typing import NamedTuple

TASK_NONCE_LENGTH = ZMQ_IDENTITY_LENGTH = 5

TASK_INFO_FMT = ">III"
TASK_ID_LENGTH = TASK_NONCE_LENGTH + struct.calcsize(TASK_INFO_FMT)

CHUNK_INFO_FMT = ">i"
CHUNK_ID_LENGTH = TASK_ID_LENGTH + struct.calcsize(CHUNK_INFO_FMT)

DEFAULT_ZMQ_RECVTIMEO = -1
DEFAULT_NAMESPACE = "default"


EMPTY_MULTIPART = [b""]


class Msgs:
    cmd = 0
    info = 1
    namespace = 2
    args = 3
    kwargs = 4


class Cmds:
    ping = 0
    get_server_meta = 1

    get_state = 2
    set_state = 3

    run_fn_atomically = 4
    run_dict_method = 5

    time = 6


class ServerMeta(NamedTuple):
    version: str

    state_router: str
    watcher_router: str

    task_router: str
    task_result_pull: str

    task_proxy_in: str
    task_proxy_out: str


class StateUpdate(NamedTuple):
    before: dict
    after: dict
    timestamp: float
    is_identical: bool
