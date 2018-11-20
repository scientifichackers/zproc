import atexit
from multiprocessing.connection import Connection

import zmq

from zproc import exceptions, serializer, util
from zproc.__version__ import __version__
from zproc.consts import ServerMeta
from zproc.state.state_server import StateServer
from zproc.task.server import start_task_server, start_task_proxy


def main(server_address: str, send_conn: Connection):
    with util.socket_factory(zmq.ROUTER, zmq.ROUTER) as (
        zmq_ctx,
        state_router,
        watch_router,
    ):
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
                *start_task_proxy(_bind)
            )
            state_server = StateServer(state_router, watch_router, server_meta)

            send_conn.send_bytes(serializer.dumps(server_meta))
        except Exception:
            send_conn.send_bytes(serializer.dumps(exceptions.RemoteException()))
            return
        finally:
            send_conn.close()

        def cleanup():
            util.clean_process_tree()
            util.log_internal_crash("State server")

        atexit.register(cleanup)
        try:
            state_server.main()
        except KeyboardInterrupt:
            cleanup()
