"""
Tests the re-creation of object, using the UUID feature
"""

import unittest

import zproc


ADDRESS = ("tcp://127.0.0.1:50000", "tcp://127.0.0.1:500001")


class TestUUIDAPI(unittest.TestCase):
    def setUp(self):
        ctx = zproc.Context()
        ctx.state["foo"] = 42

        self.server_address = ctx.server_address

    def test1(self):
        ctx = zproc.Context(self.server_address)

        self.assertEqual(ctx.state.copy(), {"foo": 42})

    def test2(self):
        state = zproc.ZeroState(self.server_address)

        self.assertEqual(state.copy(), {"foo": 42})

    def test3(self):
        zproc.start_server(ADDRESS)

        ctx = zproc.Context(ADDRESS)
        self.assertEqual(ctx.state.copy(), {})

        state = zproc.ZeroState(ADDRESS)
        self.assertEqual(state.copy(), {})


if __name__ == "__main__":
    unittest.main()
