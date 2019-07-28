cpdef enum Msgs:
    cmd = 0
    info = 1
    namespace = 2
    args = 3
    kwargs = 4


cpdef enum Cmds:
    ping = 0
    get_server_meta = 1
    run_fn_atomically = 2
    time = 3
