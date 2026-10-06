
import unreal
live.HW = {'t': 0., 'min': 99., 'done': False, 'at': None}
def _hw(dt):
    s = live.HW
    if s['done']:
        return
    st = dict(kv.split('=', 1) for kv in live.skate_state().split() if '=' in kv)
    if 'hand_gap' not in st:
        return
    r = float(st['hand_gap'].split(',')[1])
    s['t'] += dt
    if s['t'] < 1.6:
        s['min'] = min(s['min'], r)
    elif r <= s['min'] + .3 or s['t'] > 4.5:
        unreal.GameplayStatics.set_global_time_dilation(live.L.game_world(), .0001)
        s['done'], s['at'] = True, r
live.behave('handworst', _hw)
