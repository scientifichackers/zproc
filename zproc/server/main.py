import atexit
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

import zmq

from zproc import exceptions, serializer, util
from zproc.__version__ import __version__
from zproc.consts import ServerMeta
from zproc.exceptions import RemoteException
from zproc.state.server import StateServer
from zproc.task.server import start_task_server, start_task_proxy


@contextmanager
def write_pid_file(pid_file: Optional[Path]):
    if pid_file is None:
        yield
        return
    try:
        print(f"[ZProc] Storing PID file @ {str(pid_file)!r}")
        with open(pid_file, "w") as f:
            f.write(str(os.getpid()))
        yield
    finally:
        with open(pid_file, "w") as f:
            f.write("")


def main(server_address: str, pid_file: Optional[Path], send_conn):
    with write_pid_file(pid_file), util.socket_factory(zmq.ROUTER, zmq.ROUTER) as (
        zmq_ctx,
        state_router,
        watch_router,
    ):
        atexit.register(util.clean_process_tree)

        try:
            if server_address:
                state_router.bind(server_address)
                if "ipc" in server_address:
                    _bind = util.bind_to_random_ipc
                else:
                    _bind = util.bind_to_random_tcp
            else:
                _bind = util.bind_to_random_address
                server_address = _bind(state_router)

            server_meta = ServerMeta(
                __version__,
                server_address,
                _bind(watch_router),
                *start_task_server(_bind),
                *start_task_proxy(_bind),
            )

            state_server = StateServer(state_router, watch_router, server_meta)
        except Exception:
            with send_conn:
                send_conn.send_bytes(serializer.dumps(exceptions.RemoteException()))
            return
        else:
            with send_conn:
                send_conn.send_bytes(serializer.dumps(server_meta))

        while True:
            try:
                state_server.tick()
            except KeyboardInterrupt:
                util.log_internal_crash("State Server")
                return
            except Exception:
                if state_server.identity is None:
                    util.log_internal_crash("State server")
                else:
                    state_server.reply(RemoteException())
            finally:
                state_server.reset_internal_state()
