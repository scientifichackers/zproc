"""
Tests the re-creation of object, using the UUID feature
"""

import unittest

import zproc
import uuid


class TestUUIDAPI(unittest.TestCase):
    def setUp(self):
        self.uuid = uuid.uuid1()

        ctx = zproc.Context(uuid=self.uuid)
        ctx.start_server()

        ctx.state["foo"] = 42

    def test_ctx_from_uuid(self):
        ctx = zproc.Context(uuid=self.uuid)

        self.assertEqual(ctx.state.copy(), {"foo": 42})

    def test_state_from_uuid(self):
        state = zproc.ZeroState(uuid=self.uuid)

        self.assertEqual(state.copy(), {"foo": 42})


if __name__ == "__main__":
    unittest.main()
