
import unreal
st = dict(kv.split('=', 1) for kv in live.skate_state().split() if '=' in kv)
P = unreal.Vector(*[float(v) for v in st.get('hips', st.get('hip')).split(',')])
H = P
try:
    _m = live.L.player().get_editor_property('mesh')
    _b = next((n for n in ('hand_R', 'Wrist_R', 'hand_r') if _m.get_bone_index(n) != -1), None)
    H = _m.get_socket_location(_b) if _b else P
except Exception as e:
    print('no right hand:', e)
_out = unreal.Vector(H.x - P.x, H.y - P.y, 0)
_out = _out * (1 / _out.length()) if _out.length() > 1 else live.L.player().get_actor_right_vector()
unreal.MegaParkValidation.review_camera(H + _out * 85 + unreal.Vector(0, 0, 8), H, 40)
