import os
import textwrap
import time
import traceback
from functools import wraps

import zmq

from zproc import exceptions, util, serializer


class ChildProcess:
    exitcode = 0
    retries = 0

    def __init__(self, **kwargs):
        self.kwargs = kwargs

        self.pass_context = self.kwargs["pass_context"]
        self.max_retries = self.kwargs["max_retries"]
        self.retry_delay = self.kwargs["retry_delay"]
        self.retry_args = self.kwargs["retry_args"]
        self.retry_kwargs = self.kwargs["retry_kwargs"]
        self.to_catch = tuple(util.to_catchable_exc(self.kwargs["retry_for"]))
        self.target = self.kwargs["target"]

        self.target_args = self.kwargs["target_args"]
        self.target_kwargs = self.kwargs["target_kwargs"]

        self.basic_info = "target: %s\npid: %r\nppid: %r" % (
            util.callable_repr(self.target),
            os.getpid(),
            os.getppid(),
        )

        self.main()

    def _handle_exc(self, e: Exception, *, handle_retry: bool = False):
        retry_info = ""
        if handle_retry:
            if self.max_retries is not None and self.retries > self.max_retries:
                raise e

            retry_info = "Tried - %r time(s)\n" % self.retries
            if self.max_retries is not None and self.retries >= self.max_retries:
                retry_info += "*Max retries reached*\n"
                if isinstance(e, exceptions.SignalException):
                    exceptions.exception_to_signal(e)
            else:
                retry_info += "Next retry in - %r sec\n" % self.retry_delay

        report = "\n".join((self.basic_info, retry_info, traceback.format_exc()))
        report = textwrap.indent(report, " " * 2)
        print("\n[ZProc] Crash report:\n" + report)

        if handle_retry:
            time.sleep(self.retry_delay)

    def main(self):
        @wraps(self.target)
        def target_wrapper(*args, **kwargs):
            while True:
                self.retries += 1
                try:
                    return self.target(*args, **kwargs)
                except exceptions.ProcessExit as e:
                    self.exitcode = e.exitcode
                    return None
                except self.to_catch as e:
                    self._handle_exc(e, handle_retry=True)

                    if self.retry_args is not None:
                        self.target_args = self.retry_args
                    if self.retry_kwargs is not None:
                        self.target_kwargs = self.retry_kwargs

        try:
            if self.pass_context:
                from .context import Context  # this helps avoid a circular import

                return_value = target_wrapper(
                    Context(
                        self.kwargs["server_address"],
                        namespace=self.kwargs["namespace"],
                        start_server=False,
                    ),
                    *self.target_args,
                    **self.target_kwargs
                )
            else:
                return_value = target_wrapper(*self.target_args, **self.target_kwargs)
            # print(return_value)
            with util.create_zmq_ctx(linger=True) as zmq_ctx:
                with zmq_ctx.socket(zmq.PAIR) as result_sock:
                    result_sock.connect(self.kwargs["result_address"])
                    result_sock.send(serializer.dumps(return_value))
        except Exception as e:
            self._handle_exc(e)
        finally:
            util.clean_process_tree(self.exitcode)
