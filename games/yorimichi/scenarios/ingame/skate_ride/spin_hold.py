
live.AIRT=[0.0]
def _spin(dt):
    s=live.skate_state(); air='mode=2 ' in s
    live.AIRT[0]=live.AIRT[0]+dt if air else 0.0
    live.skate_input(left=(1,0) if air and live.AIRT[0]<HOLD else (0,0))
live.behave('spin', _spin)
