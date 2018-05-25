"""
One process makes cookies while other eats them!

# Expected output
main: I made a cookie!
eater: I ate a cookie!
main: I made a cookie!
eater: I ate a cookie!
main: I made a cookie!
eater: I ate a cookie!
main: I made a cookie!
eater: I ate a cookie!
main: I made a cookie!
eater: I ate a cookie!
"""
from time import sleep

import zproc

ctx = zproc.Context()
ctx.state['cookies'] = 0


@ctx.processify()
def cookie_eater(state):
    while True:
        cookies = state.get_when_change('cookies')
        state['cookies'] = cookies - 1
        print('eater: I ate a cookie!')


sleep(.5)

for i in range(5):
    ctx.state['cookies'] += 1
    print('main: I made a cookie!')
    sleep(.5)

sleep(.5)
