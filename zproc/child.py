import os
import textwrap
import time
import traceback
from functools import wraps
from typing import Callable, Union, Sequence, Mapping, Type, Optional, Tuple

import psutil
import zmq

from zproc import exceptions, util, serializer


class ChildProcess:
    exitcode = 0
    retries = 0

    target: Callable
    client_args: Sequence
    client_kwargs: Mapping
    target_args: Sequence
    target_kwargs: Mapping
    to_catch: Tuple[Type[BaseException]]
    retry_delay: Union[int, float]
    max_retries: Optional[int]
    retry_args: tuple
    retry_kwargs: dict
    result_address: str

    def __init__(self, *args):
        (
            self.target,
            self.client_args,
            self.client_kwargs,
            self.target_args,
            self.target_kwargs,
            retry_for,
            self.retry_delay,
            self.max_retries,
            self.retry_args,
            self.retry_kwargs,
            self.result_address,
        ) = args

        self.to_catch = tuple(util.to_catchable_exc(retry_for))
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

        client = None
        try:
            from .client import Client  # this helps avoid a circular import

            client = Client(*self.client_args, **self.client_kwargs)
            return_value = target_wrapper(
                client, *self.target_args, **self.target_kwargs
            )

            with util.create_zmq_ctx(linger=True) as zmq_ctx:
                with zmq_ctx.socket(zmq.PAIR) as result_sock:
                    result_sock.connect(self.result_address)
                    result_sock.send(serializer.dumps(return_value))
        except Exception as e:
            self._handle_exc(e)
        finally:
            if client is not None and client.wait_enabled:
                psutil.wait_procs(psutil.Process().children())
            util.clean_process_tree(self.exitcode)
