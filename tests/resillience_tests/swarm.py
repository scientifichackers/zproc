import zproc

swarm = zproc.Context().create_swarm()

fn = lambda x: x

i = 0
while True:
    assert swarm.map(fn, range(10 ** 5)) == list(map(fn, range(10 ** 5)))
    print(i)
    i += 1
