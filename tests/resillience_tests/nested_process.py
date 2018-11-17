import time

import zproc

ctx = zproc.Context()


for i in range(250):

    @ctx.spawn(pass_context=True)
    def p1(ctx):
        @ctx.spawn(pass_context=True)
        def p2(ctx):
            @ctx.spawn(pass_state=False)
            def p3(ctx):
                @ctx.spawn(pass_state=False)
                def p4(ctx):
                    @ctx.spawn(pass_state=False)
                    def pn():
                        time.sleep(1)

        print(i)
        return i

    assert p1.wait() == i
