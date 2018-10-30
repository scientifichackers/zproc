import zproc

ctx = zproc.Context()


for i in range(250):

    @ctx.process
    def my_process(state):
        assert isinstance(state, zproc.State)
        print(i)
        return i

    assert my_process.wait() == i
