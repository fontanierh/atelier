
import unreal
live.JW = {'t': -1., 'done': False, 'at': None, 'joint': None, 'angles': None, 'when': None}
def _jw(dt):
    s = live.JW
    if s['done']:
        return
    st = dict(kv.split('=', 1) for kv in live.skate_state().split() if '=' in kv)
    if st.get('mode') != '4' or st.get('phys') != 'Bail' or 'joint_past' not in st:
        if s['t'] >= 0 and st.get('mode') != '4':
            s['done'] = 'over'
        return
    s['t'] = s['t'] + dt if s['t'] >= 0 else 0.
    past = float(st['joint_past'])
    if past >= TARGET or s['t'] >= LATEST:
        unreal.GameplayStatics.set_global_time_dilation(live.L.game_world(), .0001)
        s.update(done=True, at=past, joint=st.get('joint'), angles=st.get('joint_angles'), when=s['t'])
live.behave('jointworst', _jw)
