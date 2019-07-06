import zproc

ctx = zproc.Client()

for i in range(250):

    @ctx.spawn
    def my_process(ctx):
        assert isinstance(ctx, zproc.Client)
        state = ctx.create_state()
        assert isinstance(state, zproc.StateMethods)
        print(i)
        return i

    assert my_process.wait() == i
