import zproc

ctx = zproc.Context()

for i in range(250):

    @ctx.spawn
    def my_process(ctx):
        assert isinstance(ctx, zproc.Context)
        state = ctx.create_state()
        assert isinstance(state, zproc.State)
        print(i)
        return i

    assert my_process.wait() == i
