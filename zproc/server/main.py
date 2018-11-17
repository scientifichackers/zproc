import atexit
import time
from multiprocessing.connection import Connection

import zmq

from zproc import exceptions
from zproc import util
from zproc.__version__ import __version__
from zproc.consts import ServerMeta
from zproc.state.server import StateServer
from zproc.task.server import start_task_server, start_task_proxy


# fmt: off
def main(server_address: str, send_conn: Connection):
    with \
            util.create_zmq_ctx() as ctx, \
            ctx.socket(zmq.ROUTER) as state_router, \
            ctx.socket(zmq.PUB) as state_pub:

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

            # required for the State object to function properly
            state_pub.setsockopt(zmq.INVERT_MATCHING, 1)

            _, (task_proxy_in, task_proxy_out) = start_task_proxy(_bind)
            _, (task_router, task_result_pull, task_pub_ready) = start_task_server(_bind)

            server_meta = ServerMeta(
                version=__version__,
                server_address=server_address,
                state_pub=_bind(state_pub),
                task_router=task_router,
                task_result_pull=task_result_pull,
                task_pub_ready=task_pub_ready,
                task_proxy_in=task_proxy_in,
                task_proxy_out=task_proxy_out
            )

            state_server = StateServer(state_router, state_pub, server_meta)
            send_conn.send_bytes(util.dumps(server_meta))
        except Exception:
            send_conn.send_bytes(util.dumps(exceptions.RemoteException()))
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
