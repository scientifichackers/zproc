import zproc

ctx = zproc.Context()


def test_nested_map():
    @ctx.process(pass_context=True)
    def my_process(ctx):
        return list(ctx.process_map(pow, range(100), args=[2]))

    assert my_process.wait() == list(map(lambda x: pow(x, 2), range(100)))
