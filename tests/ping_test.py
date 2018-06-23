"""
Tests the "ping()" API
"""

import unittest
from time import sleep
import zproc


class TestServerPing(unittest.TestCase):
    def setUp(self):
        self.ctx = zproc.Context()

    def test_ping(self):
        self.assertEqual(self.ctx.ping(), self.ctx.server_process.pid)
        self.assertEqual(self.ctx.state.ping(), self.ctx.server_process.pid)

    def test_timeout(self):
        self.assertEqual(self.ctx.ping(timeout=1), self.ctx.server_process.pid)
        self.assertEqual(self.ctx.state.ping(timeout=1), self.ctx.server_process.pid)

    def test_timeouterror(self):
        self.assertRaises(TimeoutError, self.ctx.ping, timeout=0)
        self.assertRaises(TimeoutError, self.ctx.state.ping, timeout=0)

    def test_ping_after_kill(self):
        ctx = zproc.Context()
        sleep(1)
        ctx.close()
        self.assertRaises(TimeoutError, ctx.ping, timeout=0.1)
        self.assertRaises(TimeoutError, ctx.state.ping, timeout=0.1)


if __name__ == "__main__":
    unittest.main()
