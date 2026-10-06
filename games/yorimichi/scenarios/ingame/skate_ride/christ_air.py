live.CHRIST=[False]
def _christ(dt):
    s=live.skate_state(); air='mode=2 ' in s
    if live.CHRIST[0] and not air: live.stop('christ'); live.skate_input(); return
    live.CHRIST[0]=live.CHRIST[0] or air
    live.skate_input(grab_left=live.CHRIST[0], brake=live.CHRIST[0])
live.behave('christ', _christ)
