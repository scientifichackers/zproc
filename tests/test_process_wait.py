import time

import pytest

import zproc

TOLERANCE = 0.1


@pytest.fixture
def ctx():
    return zproc.Context(pass_context=False)


def test_timeout_accuracy(ctx):
    @ctx.spawn
    def test():
        time.sleep(0.5)

    start = time.time()
    try:
        ctx.wait(0.05)
    except TimeoutError:
        end = time.time()
    else:
        raise ValueError("This should have raised TimeoutError!")
    diff = end - start

    assert diff == pytest.approx(0.05, TOLERANCE)


def test_timeout_accuracy_parallel(ctx):
    @ctx.spawn
    def test1():
        time.sleep(0.5)

    @ctx.spawn
    def test2():
        time.sleep(1)

    start = time.time()
    try:
        ctx.wait(0.6)
    except TimeoutError:
        end = time.time()
    else:
        raise ValueError("This should have raised TimeoutError!")
    diff = end - start

    assert diff == pytest.approx(0.6, TOLERANCE)


def test_timeout1(ctx):
    @ctx.spawn
    def test():
        time.sleep(0.5)

    with pytest.raises(TimeoutError):
        ctx.wait(0.1)


def test_timeout2(ctx):
    @ctx.spawn
    def test():
        time.sleep(0.5)

    with pytest.raises(TimeoutError):
        test.wait(0.1)


def test_wait_timeout(ctx):
    @ctx.spawn
    def test1():
        time.sleep(0.5)

    @ctx.spawn
    def test2():
        time.sleep(1)

    # will raise an exc
    with pytest.raises(TimeoutError):
        ctx.wait(0.6)


def test_wait_timeout_dumb(ctx):
    @ctx.spawn
    def test1():
        time.sleep(0.5)

    @ctx.spawn
    def test2():
        time.sleep(1)

    # won't raise exc
    for i in ctx.process_list:
        i.wait(0.6)


def test_wait_error(ctx):
    @ctx.spawn
    def test():
        raise ValueError

    with pytest.raises(zproc.ProcessWaitError):
        test.wait()

    with pytest.raises(zproc.ProcessWaitError):
        ctx.wait()


def test_exit(ctx):
    @ctx.spawn
    def test():
        raise zproc.ProcessExit(1)

    with pytest.raises(zproc.ProcessWaitError):
        test.wait()

    assert test.exitcode == 1

    with pytest.raises(zproc.ProcessWaitError):
        ctx.wait()
