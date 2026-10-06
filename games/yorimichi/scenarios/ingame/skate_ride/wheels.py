
import math
_ch = unreal.GameplayStatics.get_player_character(live.L.game_world(), 0)
# The board as shown: the skate component's wheel meshes (SkateWheel<end><side>, placed at the wheel bones' centres:
# front right, front left, back right, back left), not the hidden pose mesh, which stays in the clips' root space.
_parts = {c.get_name(): c for c in _ch.get_components_by_class(unreal.StaticMeshComponent)}
_w = [_parts[n] for n in ('SkateWheel00', 'SkateWheel01', 'SkateWheel10', 'SkateWheel11')]
_objects = [unreal.ObjectTypeQuery.OBJECT_TYPE_QUERY1, unreal.ObjectTypeQuery.OBJECT_TYPE_QUERY2]
_skip = [_ch] + list(_ch.get_attached_actors() or [])
live.WHITS = {}
def _hit(a, b):
    # The first hit that starts clear of what it hits: a trace that starts inside something (the rider's feet, a
    # volume) reports its own start, which is not the ground. What it skipped and what it took is counted in WHITS.
    a, b = unreal.Vector(*a), unreal.Vector(*b)
    hits = unreal.SystemLibrary.line_trace_multi_for_objects(live.L.game_world(), a, b, _objects, True, _skip, unreal.DrawDebugTrace.NONE, True) or []
    for h in hits:
        t = h.to_tuple()
        name = (t[9].get_name() if t[9] else '?') + '/' + (t[10].get_name() if t[10] else '?')
        if t[1] or t[3] <= 0:
            live.WHITS['skipped ' + name] = live.WHITS.get('skipped ' + name, 0) + 1
            continue
        live.WHITS[name] = live.WHITS.get(name, 0) + 1
        return ((t[5].x, t[5].y, t[5].z), (t[7].x, t[7].y, t[7].z))
    return None
def _wheels(dt):
    c = []
    for w in _w:
        l = w.get_world_location(); c.append((l.x, l.y, l.z))
    out = []
    for i, p in enumerate(c):
        q = c[i ^ 1]; ax = [q[k] - p[k] for k in range(3)]; s = math.sqrt(sum(v * v for v in ax)) or 1.
        # From 5 cm above the wheel's centre (under the deck, above the wheel's top) down the vertical for the ground's
        # normal, then down the normal itself, so a wheel up to 8 cm into the ground still reads.
        down = _hit((p[0], p[1], p[2] + 5), (p[0], p[1], p[2] - 80))
        hit = down and _hit(tuple(p[k] + down[1][k] * 5 for k in range(3)), tuple(p[k] - down[1][k] * 80 for k in range(3)))
        if not hit: out.append(None); continue
        n = down[1]; na = sum(n[k] * ax[k] for k in range(3)) / s
        out.append(round(sum((p[k] - hit[0][k]) * n[k] for k in range(3)) - WHEEL_R * math.sqrt(max(0., 1 - na * na)), 2))
    live.WREC.append((live.skate_state(), out))
live._wheels = _wheels
