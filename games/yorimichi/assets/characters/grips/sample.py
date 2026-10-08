"""Read-only sampler beside a running game: the hands on their props, for moments.py (the poser's scenes) or check.py.

    uv run python games/yorimichi/assets/characters/grips/sample.py PORT OUT.jsonl SECONDS [--held]

PORT is the game's live bridge (atelier play ... -- -liveport=PORT). About once a second it appends one row to OUT.jsonl
while the player holds the sword in the two-handed guard or the glider (drive the clips with a film or by hand):

- by default, what moments.py fits: each hand's skin (per finger, by the bone with most weight), its joints, and the
  held prop's vertices (the sword's) or the glider's two handle axes and its skinned vertices;
- with --held, what check.py measures: the move set's state, the grip report, both hands' bones and the props, as world
  transforms ([location, quaternion xyzw, scale]), in every pose (not only the two grips).

It only reads (LiveLibrary.SkinnedVertices and StaticVertices, socket transforms), so it runs beside a film. The code it
sends keeps its names inside a function: the live bridge shares its globals with the film.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scenarios')); import skate as qa  # noqa: E402

MOMENTS = r'''
def _grips_sample():
    import unreal, json
    L = unreal.LiveLibrary
    p = L.player(); m = p.mesh
    st = json.loads(live.L.move_state())
    def pts(v): return [[round(q.x, 2), round(q.y, 2), round(q.z, 2)] for q in v]
    out = {'mode': st.get('mode'), 'guard': st.get('sword_guard_carry'), 'hold': st.get('sword_hold')}
    try: out['grip'] = json.loads(m.get_anim_instance().grip_report())
    except Exception as e: out['grip'] = {'error': str(e)[-200:]}
    g = [c for c in p.get_components_by_class(unreal.SkeletalMeshComponent) if c.get_name() == 'Paraglider' and c.is_visible()]
    if not ((st.get('sword_guard_carry') or 0) > .9 or (st.get('mode') == 'glide' and g and (st.get('glide_hands') or 0) > .9)):
        print('U ' + json.dumps(out)); return
    digits = lambda f, s: [f'{n}{f}_{s}' for n in ('finger_', 'finger_tip_', 'finger_end_')]
    thumb = lambda s: [f'{j}{s}' for j in ('thumb_', 'thumb_tip_', 'thumb_end_')]
    for s in 'RL':
        out['fingers_' + s] = {str(f): pts(L.skinned_vertices(m, digits(f, s))) for f in range(4)}
        out['thumb_' + s] = pts(L.skinned_vertices(m, thumb(s)))
        out['palm_' + s] = pts(L.skinned_vertices(m, [f'hand_{s}']))
        # the whole hand once (a vertex with a third of its weight on any of its bones), not a sum of the fingers
        out['hand_' + s] = pts(L.skinned_vertices(m, [f'hand_{s}'] + thumb(s) + [b for f in range(4) for b in digits(f, s)]))
        out['joints_' + s] = {n: pts([m.get_socket_location(n)])[0] for n in [b for f in range(4) for b in digits(f, s)] + thumb(s) + [f'hand_{s}'] if m.get_bone_index(n) != -1}
    if st.get('mode') == 'glide' and g:
        # each handle's axis in the glider's component frame (BotwMoveSetDetail.h GliderHandles)
        T = g[0].get_world_transform()
        H = {'R': ((-24.8, -14.2, 1.2), (-30.5, 2.8, 1.1)), 'L': ((25.4, -14.2, 1.6), (30.1, 2.9, 1.0))}
        out['handle'] = 'glider'
        out['handle_axes'] = {s: pts([T.transform_location(unreal.Vector(*a)), T.transform_location(unreal.Vector(*b))]) for s, (a, b) in H.items()}
        out['handle_verts'] = pts(L.skinned_vertices(g[0], []))
    else:
        sw = [c for c in p.get_components_by_class(unreal.StaticMeshComponent) if c.static_mesh and c.is_visible() and 'sword' in c.get_name().lower() and 'sheath' not in c.get_name().lower()]
        if sw: out['handle'] = 'sword'; out['handle_verts'] = pts(L.static_vertices(sw[0]))
    print('U ' + json.dumps(out))
_grips_sample()
'''

HELD = r'''
def _grips_held():
    import unreal, json
    L = unreal.LiveLibrary
    p = L.player(); m = p.mesh
    def T(t):
        q = t.rotation
        return [[t.translation.x, t.translation.y, t.translation.z], [q.x, q.y, q.z, q.w], t.scale3d.x]
    out = {'move': json.loads(live.L.move_state())}
    try: out['grip'] = json.loads(m.get_anim_instance().grip_report())
    except Exception: pass
    for s in 'RL':
        for b in (f'hand_{s}', f'finger_1_{s}', f'finger_end_1_{s}', f'thumb_end_{s}', f'finger_end_3_{s}'):
            out[b] = T(m.get_socket_transform(b, unreal.RelativeTransformSpace.RTS_WORLD))
    for c in p.get_components_by_class(unreal.StaticMeshComponent):
        if c.static_mesh and 'sword' in c.get_name().lower() and 'sheath' not in c.get_name().lower(): out['sword'] = T(c.get_world_transform())
    for c in p.get_components_by_class(unreal.SkeletalMeshComponent):
        if 'paraglider' in c.get_name().lower(): out['glider'] = T(c.get_world_transform())
    print('U ' + json.dumps(out))
_grips_held()
'''


def main(args):
    qa.bridge.URL = f'http://127.0.0.1:{args.port}'
    code = HELD if args.held else MOMENTS
    end = time.time() + args.seconds
    with args.out.open('w') as out:
        while time.time() < end:
            t0 = time.time()
            try:
                r = qa.py(code)
                line = next((l for l in r.splitlines() if l.startswith('U ')), None)
                row = json.loads(line[2:]) if line else {'raw': r[-400:]}
            except Exception as e:
                row = {'error': str(e)[-400:]}
            out.write(json.dumps({'t': round(t0, 1), **row}) + '\n'); out.flush()
            time.sleep(max(0., args.every - (time.time() - t0)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('port', type=int)
    parser.add_argument('out', type=Path)
    parser.add_argument('seconds', type=float)
    parser.add_argument('--held', action='store_true', help="record the hands' and props' transforms for check.py")
    parser.add_argument('--every', type=float, default=1., help='seconds between samples')
    main(parser.parse_args())
