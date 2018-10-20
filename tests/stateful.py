import zproc

ctx = zproc.Context()


@ctx.process(stateful=False)
def my_process():
    return 0


print(my_process.wait())
