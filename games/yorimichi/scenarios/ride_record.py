"""Ride record: the player's pad, keys and skate state, one JSON line per frame, while they play. It only reads, so a
playtest can run under it. To replay a ride exactly, record it with
scenarios/ride_session.py instead.

    atelier live py "REC_TAKE='take-2302'" && atelier live py - < games/yorimichi/scenarios/ride_record.py
    ... the player plays, then:
    atelier live py "print(rec_close())"

Writes build/yorimichi/ride-record/<REC_TAKE>/: meta.json (the axis and button names) and frames.jsonl, one row a frame:
n, gt (game time), rt (real time), dt, ax (the axes as the player controller reads them, after the engine's dead
zone), b (the buttons held, a bit mask in meta's order), m (the mouse delta), p (the player's location and yaw) and s
(YorimichiLive.SkateState). It costs about 0.12 ms a frame.
"""
import json, os, time
import unreal

_world = live.L.game_world()
_pc = unreal.GameplayStatics.get_player_controller(_world, 0)


def _key(name):
    k = unreal.Key()
    k.import_text(name)
    assert k.export_text() == name, name
    return k


AXES = ['Gamepad_LeftX', 'Gamepad_LeftY', 'Gamepad_RightX', 'Gamepad_RightY', 'Gamepad_LeftTriggerAxis', 'Gamepad_RightTriggerAxis']
BUTTONS = ['Gamepad_FaceButton_Bottom', 'Gamepad_FaceButton_Right', 'Gamepad_FaceButton_Left', 'Gamepad_FaceButton_Top',
           'Gamepad_LeftShoulder', 'Gamepad_RightShoulder', 'Gamepad_LeftThumbstick', 'Gamepad_RightThumbstick',
           'Gamepad_DPad_Up', 'Gamepad_DPad_Down', 'Gamepad_DPad_Left', 'Gamepad_DPad_Right',
           'Gamepad_Special_Left', 'Gamepad_Special_Right',
           'W', 'A', 'S', 'D', 'SpaceBar', 'Q', 'E', 'C', 'B', 'G', 'LeftShift', 'LeftMouseButton', 'Escape']
_AK = [_key(n) for n in AXES]
_BK = [_key(n) for n in BUTTONS]
REC_DIR = os.path.join(live.ROOT, 'build/yorimichi/ride-record', globals().get('REC_TAKE', 'take1'))
os.makedirs(REC_DIR, exist_ok=True)
_rec = {'f': open(os.path.join(REC_DIR, 'frames.jsonl'), 'a'), 'n': 0, 't0': time.perf_counter()}
with open(os.path.join(REC_DIR, 'meta.json'), 'w') as _m:
    json.dump({'axes': AXES, 'buttons': BUTTONS, 'started': time.strftime('%Y-%m-%d %H:%M:%S')}, _m, indent=1)


def _frame(dt):
    pc = _pc
    ax = [round(pc.get_input_analog_key_state(k), 4) for k in _AK]
    mask = 0
    for i, k in enumerate(_BK):
        if pc.is_input_key_down(k): mask |= 1 << i
    m = pc.get_input_mouse_delta()
    t = live.L.player_transform()
    p = t.translation
    row = {'n': _rec['n'], 'gt': round(unreal.GameplayStatics.get_time_seconds(_world), 5),
           'rt': round(time.perf_counter() - _rec['t0'], 5), 'dt': round(dt, 5), 'ax': ax, 'b': mask,
           'm': [round(m[0], 3), round(m[1], 3)] if m else None,
           'p': [round(p.x, 1), round(p.y, 1), round(p.z, 1), round(t.rotation.rotator().yaw, 2)],
           's': live.L.skate_state()}
    _rec['f'].write(json.dumps(row, separators=(',', ':')) + '\n')
    _rec['n'] += 1
    if _rec['n'] % 60 == 0: _rec['f'].flush()


def rec_close():
    """Stop recording; the number of frames recorded."""
    live.stop('ride_rec')
    _rec['f'].flush(); _rec['f'].close()
    return _rec['n']


live.behave('ride_rec', _frame)
print('recording to', REC_DIR)
