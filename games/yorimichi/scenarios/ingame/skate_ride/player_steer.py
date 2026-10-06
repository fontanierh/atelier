
live.LIPP=[False]
def _lipp(dt):
    live.LIPP[0]=live.LIPP[0] or 'mode=2 ' in live.skate_state()
    live.skate_input(left=(0,0) if live.LIPP[0] else (STEER,0))
live.behave('lipp', _lipp)
