import zproc

ctx = zproc.Context()


def test_stateful_false():
    @ctx.process(stateful=False)
    def my_process():
        return 0

    assert my_process.wait() == 0


def test_pass_ctx():
    for stateful in (True, False):

        @ctx.process(pass_context=True, stateful=stateful)
        def my_process(ctx):
            assert isinstance(ctx, zproc.Context)
            return 0

        assert my_process.wait() == 0


def test_stateful_true():
    @ctx.process(stateful=True)
    def my_process(state):
        assert isinstance(state, zproc.State)
        return 0

    assert my_process.wait() == 0
