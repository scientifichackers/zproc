"""
Tests the re-creation of object, using the UUID feature
"""

import unittest

import zproc


class TestUUIDAPI(unittest.TestCase):
    def setUp(self):
        self.ctx = zproc.Context()
        self.ctx.state['foo'] = 42

    def test_new_ctx_from_ctx(self):
        ctx = zproc.Context(uuid=self.ctx.uuid)

        self.assertEqual(ctx.state.copy(), {'foo': 42})

    def test_new_ctx_from_state(self):
        ctx = zproc.Context(uuid=self.ctx.state.uuid)

        self.assertEqual(ctx.state.copy(), {'foo': 42})

    def test_new_state_from_ctx(self):
        state = zproc.ZeroState(uuid=self.ctx.uuid)

        self.assertEqual(state.copy(), {'foo': 42})

    def test_new_state_from_state(self):
        state = zproc.ZeroState(uuid=self.ctx.state.uuid)

        self.assertEqual(state.copy(), {'foo': 42})


if __name__ == '__main__':
    unittest.main()
