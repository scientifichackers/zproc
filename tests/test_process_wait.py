import pytest
import time

import zproc

TOLERANCE = 0.1


@pytest.fixture
def ctx():
    return zproc.Context(stateful=False)


def test_timeout_accuracy1(ctx):
    @ctx.process
    def test():
        time.sleep(1.5)

    start = time.time()
    try:
        ctx.wait_all(1)
    except TimeoutError:
        end = time.time()
    else:
        raise ValueError("This should have raised TimeoutError!")
    diff = end - start

    assert diff == pytest.approx(1, TOLERANCE)


def test_timeout_accuracy2(ctx):
    @ctx.process
    def test():
        time.sleep(1.5)

    start = time.time()
    try:
        test.wait(1)
    except TimeoutError:
        end = time.time()
    else:
        raise ValueError("This should have raised TimeoutError!")
    diff = end - start

    assert diff == pytest.approx(1, TOLERANCE)


def test_timeout_accuracy3(ctx):
    @ctx.process
    def test1():
        time.sleep(0.5)

    @ctx.process
    def test2():
        time.sleep(1)

    start = time.time()
    try:
        ctx.wait_all(0.6)
    except TimeoutError:
        end = time.time()
    else:
        raise ValueError("This should have raised TimeoutError!")
    diff = end - start

    assert diff == pytest.approx(0.6, TOLERANCE)


def test_timeout1(ctx):
    @ctx.process
    def test():
        time.sleep(1.5)

    with pytest.raises(TimeoutError):
        ctx.wait_all(1)


def test_timeout2(ctx):
    @ctx.process
    def test():
        time.sleep(1.5)

    with pytest.raises(TimeoutError):
        test.wait(1)


def test_wait_all_timeout(ctx):
    @ctx.process
    def test1():
        time.sleep(0.5)

    @ctx.process
    def test2():
        time.sleep(1)

    # will raise an exc
    with pytest.raises(TimeoutError):
        ctx.wait_all(0.6)


def test_wait_all_timeout_dumb(ctx):
    @ctx.process
    def test1():
        time.sleep(0.5)

    @ctx.process
    def test2():
        time.sleep(1)

    # won't raise exc
    for i in ctx.process_list:
        i.wait(0.6)


def test_wait_error(ctx):
    @ctx.process
    def test():
        raise ValueError

    with pytest.raises(zproc.ProcessWaitError):
        test.wait()

    with pytest.raises(zproc.ProcessWaitError):
        ctx.wait_all()


def test_exit(ctx):
    @ctx.process
    def test():
        raise zproc.ProcessExit(1)

    with pytest.raises(zproc.ProcessWaitError):
        test.wait()

    assert test.exitcode == 1

    with pytest.raises(zproc.ProcessWaitError):
        ctx.wait_all()
