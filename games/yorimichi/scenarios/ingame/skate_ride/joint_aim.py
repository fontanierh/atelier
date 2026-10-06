
import unreal
st = dict(kv.split('=', 1) for kv in live.skate_state().split() if '=' in kv)
P = unreal.Vector(*[float(v) for v in st['hips'].split(',')])
J = P
try:
    _m = live.L.player().get_editor_property('mesh')
    if live.JW.get('joint') and _m.get_bone_index(live.JW['joint']) != -1:
        J = _m.get_socket_location(live.JW['joint'])
except Exception as e:
    print('no joint bone:', e)
_out = unreal.Vector(J.x - P.x, J.y - P.y, 0)
_out = _out * (1 / _out.length()) if _out.length() > 5 else live.L.player().get_actor_right_vector()
_mid = (J + P) * .5
unreal.MegaParkValidation.review_camera(_mid + _out * 120 + unreal.Vector(0, 0, 70), _mid, 45)
