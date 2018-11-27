import zmq

from zproc import util, serializer


class _TaskResultBase:
    def __init__(self, server_address: str, task_id: bytes):
        #: Passed on from the constructor
        self.task_id = task_id

        self._zmq_ctx = util.create_zmq_ctx()
        self._server_meta = util.get_server_meta(self._zmq_ctx, server_address)
        self._dealer = self._create_dealer()

    def _create_dealer(self) -> zmq.Socket:
        sock = self._zmq_ctx.socket(zmq.DEALER)
        sock.connect(self._server_meta.task_router)
        return sock

    def _get_chunk(self, index: int):
        chunk_id = util.encode_chunk_id(self.task_id, index)
        return serializer.loads(
            util.strict_request_reply(chunk_id, self._dealer.send, self._dealer.recv)
        )

    def __del__(self):
        try:
            self._dealer.close()
            util.close_zmq_ctx(self._zmq_ctx)
        except Exception:
            pass


class SimpleTaskResult(_TaskResultBase):
    def __init__(self, server_address: str, task_id: bytes):
        super().__init__(server_address, task_id)

        task_detail = util.deconstruct_task_id(self.task_id)
        if task_detail is not None:
            raise ValueError(
                "Invalid `task_id` for a %r. Did you mean to use %r?"
                % (self.__class__.__qualname__, SequenceTaskResult.__qualname__)
            )

    @property
    def value(self):
        return self._get_chunk(-1)


class SequenceTaskResult(_TaskResultBase):
    _chunk_index = -1
    _iter_index = -1
    _max_ready_index = -1

    def __init__(self, server_address: str, task_id: bytes):
        super().__init__(server_address, task_id)

        task_detail = util.deconstruct_task_id(self.task_id)
        if task_detail is None:
            raise ValueError(
                "Invalid `task_id` for a %r. Did you mean to use %r?"
                % (self.__class__.__qualname__, SimpleTaskResult.__qualname__)
            )

        self._chunk_length, self._length, self._num_chunks = task_detail
        self._max_index = self._num_chunks - 1
        self._as_list = [None] * self._length

    def _get_next_chunk(self):
        if self._chunk_index >= self._max_index:
            raise StopIteration

        self._chunk_index += 1
        self._max_ready_index += self._chunk_length

        chunk = self._get_chunk(self._chunk_index)
        i, j = self._chunk_index, self._chunk_length
        self._as_list[i * j : (i + 1) * j] = chunk

    @property
    def as_list(self):
        try:
            while True:
                self._get_next_chunk()
        except StopIteration:
            return self._as_list

    def __len__(self):
        return self._length

    def __iter__(self):
        return self

    def __next__(self):
        self._iter_index += 1
        if self._iter_index > self._max_ready_index:
            self._get_next_chunk()
        return self._as_list[self._iter_index]
