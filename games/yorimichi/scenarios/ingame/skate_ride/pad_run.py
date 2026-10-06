
def _pad_run(timeline, push_until, duration):
    live.REC = []; st = {'t': 0.0, 'i': 0, 'push': None}
    def axes(x, y):
        live.L.input_key('Gamepad_RightX', 'axis', float(x)); live.L.input_key('Gamepad_RightY', 'axis', float(-y))
    def tick(dt):
        t = st['t']
        if st['i'] + 1 < len(timeline) and timeline[st['i'] + 1][0] <= t: st['i'] += 1
        axes(*timeline[st['i']][1])
        down = push_until is not None and t < push_until
        if down != st['push']:
            live.L.input_key('Gamepad_FaceButton_Bottom', 'press' if down else 'release', 1 if down else 0); st['push'] = down
        live.REC.append('padt=%.4f pt=%d ' % (t, st['i']) + live.skate_state())
        st['t'] = t + dt
        if t >= duration:
            axes(0, 0); live.L.input_key('Gamepad_FaceButton_Bottom', 'release', 0); live.stop('pad_flick')
    live.behave('pad_flick', tick)
live.pad_run = _pad_run
