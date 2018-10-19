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


class ProcessExit(Exception):
    def __init__(self, status=0):
        """
        The analogue of inbuilt ``SystemExit``, but only for a single Process.

        When raised inside a :py:class:`Process`,
        this will cause the Process to immediately shut down,
        with ``status``, without calling cleanup handlers, flushing stdio buffers, etc.

        Useful for the ``Context.call_when_*`` functions, since they run in a never-ending infinite loop.
        """
        self.status = status


def signal_to_exception(sig: signal.Signals):
    """
    Convert a ``signal.Signals`` to a ``SignalException``.

    This allows for a natural, pythonic signal handing with the use of try-except blocks.
    """
    def handler(sig, frame):
        raise SignalException(sig, frame)

    signal.signal(sig, handler)
