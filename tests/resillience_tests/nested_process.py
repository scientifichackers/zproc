import time

import zproc

ctx = zproc.Client()

for i in range(250):

    @ctx.spawn
    def p1(ctx):
        @ctx.spawn
        def p2(ctx):
            @ctx.spawn
            def p3(ctx):
                @ctx.spawn
                def p4(ctx):
                    @ctx.spawn(pass_context=False)
                    def pn():
                        time.sleep(1)

        print(i)
        return i

    assert p1.wait() == i
