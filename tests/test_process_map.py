from functools import partial

import zproc

ctx = zproc.Context()


def pow(base, exp):
    return base ** exp


def test1():
    r1 = list(ctx.process_map(pow, range(10 ** 6), args=[10], count=4))
    r2 = list(map(partial(pow, exp=10), range(10 ** 6)))

    assert r1 == r2


def test2():
    r1 = list(ctx.process_map(pow, range(10 ** 6), args=[10], count=4))
    r2 = list(map(partial(pow, exp=10), range(10 ** 6)))

    assert r1 == r2


def test3():
    r1 = list(ctx.process_map(pow, range(10 ** 6), args=[10], count=4))
    r2 = list(map(partial(pow, exp=10), range(10 ** 6)))

    assert r1 == r2


if __name__ == "__main__":
    test1()
