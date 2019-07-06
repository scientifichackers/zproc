import pytest

import zproc


@pytest.fixture
def ctx():
    return zproc.Client()


@pytest.fixture
def swarm(ctx):
    return ctx.create_swarm()


def test_regular(swarm):
    r1 = swarm.map(pow, range(10 ** 5), args=[10])
    r2 = map(lambda x: pow(x, 10), range(10 ** 5))

    assert r1 == list(r2)


def test_lazy(swarm):
    r1 = swarm.map_lazy(pow, range(10 ** 5), args=[10])
    r2 = swarm.map_lazy(pow, range(10 ** 5), args=[10])
    r3 = map(lambda x: pow(x, 10), range(10 ** 5))

    assert list(r1) == r2.as_list == list(r3)


def test_nested_map(ctx):
    @ctx.spawn
    def p1(ctx: zproc.Client):
        swarm = ctx.create_swarm()
        return swarm.map(pow, range(100), args=[2])

    assert p1.wait() == list(map(lambda x: pow(x, 2), range(100)))


def test_remote_result(ctx):
    @ctx.spawn
    def p2(ctx: zproc.Client):
        swarm = ctx.create_swarm()
        result = swarm.map_lazy(pow, range(100), args=[2])
        return result.task_id

    result = zproc.SequenceTaskResult(ctx.server_address, p2.wait()).as_list
    assert result == list(map(lambda x: pow(x, 2), range(100)))
