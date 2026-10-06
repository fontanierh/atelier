
import re
def _pump(dt):
    s=live.skate_state(); f=lambda k, d: float((re.search(' '+k+'=([-0-9.]+)', s) or [0, d])[1])
    ground=f('mode', 1)==1; up=f('deckup', 1)
    live.skate_input(grab_left=PULL if (WHEN) else 0)
live.behave('pump', _pump)
