import pytest

import zproc


@pytest.fixture
def ctx():
    return zproc.Client()


def test_not_pass_ctx(ctx):
    @ctx.spawn(pass_context=False)
    def my_process():
        return 0

    assert my_process.wait() == 0


def test_pass_ctx(ctx):
    @ctx.spawn(pass_context=True)
    def my_process(ctx):
        assert isinstance(ctx, zproc.Client)
        return 1

    assert my_process.wait() == 1
