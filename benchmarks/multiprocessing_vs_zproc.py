import multiprocessing
import time

import zproc

ctx = zproc.Context()
ctx.workers.start()


def test123(x):
    return x * x


with multiprocessing.Pool() as p:
    s = time.perf_counter()
    print(len(p.map(test123, range(10 ** 7))))
    e = time.perf_counter()
    print("Process Pool-", e - s)


s = time.perf_counter()
print(len(ctx.workers.map(test123, range(10 ** 7))))
e = time.perf_counter()
print("Zproc Worker-", e - s)
