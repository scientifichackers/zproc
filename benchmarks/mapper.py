import multiprocessing
from time import perf_counter

import zproc

ctx = zproc.Client()
ctx.workers.start(2)


def sq(x):
    return x ** 2


SAMPLES = 10000000

s = perf_counter()
list(ctx.workers.map(sq, range(SAMPLES)))
print(perf_counter() - s)

with multiprocessing.Pool(2) as p:
    s = perf_counter()
    p.map(sq, range(SAMPLES))
    print(perf_counter() - s)
