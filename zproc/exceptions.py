import signal
import sys


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

    def reraise(self):
        raise self.exc_info[0].with_traceback(self.exc_info[1], self.exc_info[2])

    def __str__(self):
        return str(self.exc_info)


class SignalException(Exception):
    def __init__(self, sig, frame):
        self.sig = sig
        self.frame = frame


def signal_to_exception(sig: signal.Signals):
    """
    Convert a ``signal.Signals`` to a ``SignalException``.

    This allows for natural, pythonic signal handing with the use of try-except blocks.
    """

    def handler(sig, frame):
        raise SignalException(sig, frame)

    signal.signal(sig, handler)


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
