import zproc

ctx = zproc.Context()
ctx.workers.start()

i = 0
while True:
    ctx.workers.map(lambda x: x, range(10 ** 5))
    print(i)
    i += 1
