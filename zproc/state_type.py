from zproc.constants import Msgs, Commands

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


def _create_remote_dict_method(dict_method_name: str):
    """
    Generates a method for the State class,
    that will call the "method_name" on the state (a ``dict``) stored on the server,
    and return the result.

    Glorified RPC.
    """
    def remote_method(self, *args, **kwargs):
        return self._req_rep(
            {
                Msgs.cmd: Commands.exec_dict_method,
                Msgs.info: dict_method_name,
                Msgs.args: args,
                Msgs.kwargs: kwargs,
            }
        )

    remote_method.__name__ = dict_method_name
    return remote_method


class StateType(type):
    def __new__(mcs, *args, **kwargs):
        cls = super().__new__(mcs, *args, **kwargs)

        for name in STATE_DICT_METHODS:
            setattr(cls, name, _create_remote_dict_method(name))

        return cls


# See "state_type.pyi" for more
class StateDictMethodStub:
    pass
