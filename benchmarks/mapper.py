from time import perf_counter

import zproc
import multiprocessing

ctx = zproc.Context()


def test(x):
    return x ** 2


SAMPLES = 10000000

s = perf_counter()
list(ctx.process_map(test, range(SAMPLES)))
print(perf_counter() - s)

with multiprocessing.Pool() as p:
    s = perf_counter()
    p.map(test, range(SAMPLES))
    print(perf_counter() - s)
