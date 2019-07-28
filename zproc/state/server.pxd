from typing import Dict
from typing import List, Tuple

from zmq.backend.cython.socket cimport Socket


cdef class DoubleList:
    cdef size_t nexti
    cdef double[:] arr
    cdef double[:] get(self)
    cdef append(self, double item)


cdef class ServerData:
    cdef dict state
    cdef DoubleList timeline
    cdef list history #type:List[Tuple[bytes, bytes]]
    cdef dict pending #type:Dict[bytes, Tuple[bytes, bytes, float]]

    cdef bytes namespace
    cdef data #type:Dict[bytes, list]

    cdef set_state(self, dict state)
    cdef set_namespace(self, bytes value)


cdef class StateServer:
    cdef Socket state_router, watch_router
    cdef server_meta
    cdef bytes identity
    cdef ServerData data
    cdef dict dispatch_dict

    cdef recv_request(self)
    cdef reply(self, object response)
    cdef run_fn_atomically(self, dict request)
    cdef recv_watcher(self)
    cdef solve_watcher(
        self,
        bytes watcher_id,
        bytes state_id,
        bytes namespace,
        double only_after,
    )
    cdef solve_pending_watchers(self)
    cdef tick(self)