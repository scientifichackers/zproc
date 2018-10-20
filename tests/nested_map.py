import zproc

ctx = zproc.Context()


@ctx.process(pass_context=True)
def my_process(ctx):
    return list(ctx.process_map(pow, range(100), args=[2]))


print(my_process.wait())
