
import re
live.SPIN=[0.0, 0.0, []]
def _spin(dt):
    s=live.skate_state(); f=lambda k, d: float((re.search(' '+k+'=([-0-9.]+)', s) or [0, d])[1])
    air=f('mode', 1)==2; up=f('deckup', 1)
    live.SPIN[0]+=dt; live.SPIN[1]=live.SPIN[1]+dt if air else 0.0
    t, a = live.SPIN[0], live.SPIN[1]
    x=float(LEFT)
    live.SPIN[2].append((int(f('tick', 0)), x))
    live.skate_input(left=(x,0), right=(0,-1) if OLLIE and .4<=t<POP else (0,1) if OLLIE and POP<=t<POP+.033 else (0,0))
live.behave('spin', _spin)
