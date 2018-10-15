from zproc.server import ServerFn, Msg

STATE_DICT_METHODS = {
    "__contains__",
    "__delitem__",
    "__eq__",
    "__getitem__",
    "__iter__",
    "__len__",
    "__ne__",
    "__setitem__",
    "clear",
    "get",
    "pop",
    "popitem",
    "setdefault",
    "update",
}


def _create_remote_dict_method(state_method_name: str):
    """
    Generates a method for the State class,
    that will call the "method_name" on the state (a ``dict``) stored on the server,
    and return the result.

    Glorified RPC.
    """

    def remote_method(self, *args, **kwargs):
        return self._req_rep(
            {
                Msg.server_fn: ServerFn.exec_state_method,
                Msg.state_method: state_method_name,
                Msg.args: args,
                Msg.kwargs: kwargs,
            }
        )

    remote_method.__name__ = state_method_name
    return remote_method


class StateType(type):
    def __new__(mcs, *args, **kwargs):
        cls = super().__new__(mcs, *args, **kwargs)

        for name in STATE_DICT_METHODS:
            setattr(cls, name, _create_remote_dict_method(name))

        return cls
