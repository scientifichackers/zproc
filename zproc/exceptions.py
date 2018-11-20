import os
import signal
import sys
from typing import Union

from tblib.pickling_support import unpickle_traceback, pickle_traceback

from zproc import util


class ProcessWaitError(Exception):
    def __init__(self, message, exitcode, process=None) -> None:
        self.exitcode = exitcode
        self.process = process
        self.message = message

    def __str__(self):
        return self.message


class RemoteException(Exception):
    def __init__(self, exc_info=None):
        self.exc_info = exc_info
        if self.exc_info is None:
            self.exc_info = sys.exc_info()

    @classmethod
    def _from_pickled_state(cls, exc_type, value, pickled_tb):
        return cls([exc_type, value, unpickle_traceback(*pickled_tb)])

    def __reduce__(self):
        return (
            RemoteException._from_pickled_state,
            (self.exc_info[0], self.exc_info[1], pickle_traceback(self.exc_info[2])[1]),
        )

    def reraise(self):
        raise self.exc_info[0].with_traceback(self.exc_info[1], self.exc_info[2])

    def __str__(self):
        return self.__class__.__qualname__ + ": " + str(self.exc_info)

    def __repr__(self):
        return util.enclose_in_brackets(self.__str__())


class SignalException(Exception):
    def __init__(self, signum: int, frame=None):
        self.signum = signum
        self.frame = frame

    def __str__(self):
        return "SignalException: Received signal - %r." % self.signum

    def __repr__(self):
        return util.enclose_in_brackets(self.__str__())


def _sig_exc_handler(sig, frame):
    raise SignalException(sig, frame)


def signal_to_exception(sig: signal.Signals) -> SignalException:
    """
    Convert a ``signal.Signals`` to a ``SignalException``.

    This allows for natural, pythonic signal handing with the use of try-except blocks.

    .. code-block:: python

        import signal
        import zproc

        zproc.signal_to_exception(signals.SIGTERM)
        try:
            ...
        except zproc.SignalException as e:
            print("encountered:", e)
        finally:
            zproc.exception_to_signal(signals.SIGTERM)
    """
    signal.signal(sig, _sig_exc_handler)
    return SignalException(sig)


def exception_to_signal(sig: Union[SignalException, signal.Signals]):
    """
    Rollback any changes done by :py:func:`signal_to_exception`.
    """
    if isinstance(sig, SignalException):
        signum = sig.signum
    else:
        signum = sig.value
    signal.signal(signum, signal.SIG_DFL)


def send_signal(sig: Union[SignalException, signal.Signals], pid: int = None):
    if pid is None:
        pid = os.getpid()
    if isinstance(sig, SignalException):
        signum = sig.signum
    else:
        signum = sig.value
    return os.kill(pid, signum)


class ProcessExit(Exception):
    def __init__(self, exitcode=0):
        """
        Indicates that a Process should exit.

        When raised inside a :py:class:`Process`,
        it will cause the Process to shut down and exit with ``exitcode``.

        This is preferable to ``os._exit()``,
        as it signals ZProc to properly cleanup resources.

        Also useful for the ``Context.call_when_*`` decorators,
        since they run in a never-ending infinite loop.
        (making this the _right_ way to stop them from within the Process).
        """
        self.exitcode = exitcode
