import pytest

import zproc


@pytest.fixture
def ctx():
    ctx = zproc.Context()
    ctx.workers.start()
    return ctx


def test_lazy(ctx):
    r1 = ctx.workers.map(pow, range(10 ** 5), args=[10], lazy=True)
    r2 = ctx.workers.map(pow, range(10 ** 5), args=[10], lazy=True)
    r3 = map(lambda x: pow(x, 10), range(10 ** 5))

    assert list(r1) == r2.as_list == list(r3)


def test_regular(ctx):
    r1 = ctx.workers.map(pow, range(10 ** 5), args=[10])
    r2 = map(lambda x: pow(x, 10), range(10 ** 5))

    assert r1 == list(r2)


# def test_nested_map(ctx):

#     @ctx.spawnpass_context=True)
#     def p1(ctx):
#         return list(ctx.worker_map(pow, range(100), args=[2]))
#
#     @ctx.spawnpass_context=True)
#     def p2(ctx):
#         return list(ctx.process_map(pow, range(100), args=[2]))
#
#     assert p1.wait() == list(map(lambda x: pow(x, 2), range(100))) == p2.wait()
