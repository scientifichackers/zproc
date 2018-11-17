import pytest

import zproc


@pytest.fixture
def ctx():
    return zproc.Context()


def test_pass_state(ctx):
    @ctx.spawn(pass_state=True)
    def my_process(state):
        assert isinstance(state, zproc.State)
        return 0

    assert my_process.wait() == 0


def test_not_pass_state(ctx):
    @ctx.spawn(pass_state=False)
    def my_process():
        return 0

    assert my_process.wait() == 0


def test_pass_ctx(ctx):
    for pass_state in True, False:

        @ctx.spawn(pass_context=True, pass_state=pass_state)
        def my_process(ctx):
            assert isinstance(ctx, zproc.Context)
            return 0

        assert my_process.wait() == 0
