from functools import partial

import pytest

import zproc


@pytest.fixture
def ctx():
    return zproc.Context()


def test1(ctx):
    r1 = ctx.process_map(pow, range(10 ** 5), args=[10], count=4)
    r2 = map(lambda x: pow(x, 10), range(10 ** 5))

    assert list(r1) == list(r2)


def test_nested_map(ctx):
    @ctx.process(pass_context=True)
    def my_process(ctx):
        return list(ctx.process_map(pow, range(100), args=[2]))

    assert my_process.wait() == list(map(lambda x: pow(x, 2), range(100)))
