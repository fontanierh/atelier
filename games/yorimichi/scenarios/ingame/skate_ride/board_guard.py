
import math
_world = live.L.game_world()
_ch = unreal.GameplayStatics.get_player_character(_world, 0)
_deck = next(c for c in _ch.get_components_by_class(unreal.StaticMeshComponent) if c.get_name() == 'SkateDeck')
_lo, _hi = _deck.get_local_bounds()
_box = [unreal.Vector(x, y, z) for x in (_lo.x, _hi.x) for y in (_lo.y, _hi.y) for z in (_lo.z, _hi.z)]
_skip = [_ch] + list(_ch.get_attached_actors() or [])
live.GUARD_BOX = [_lo.x, _lo.y, _lo.z, _hi.x, _hi.y, _hi.z]
live.GUARD_ERR = []
_half = [(_hi.x - _lo.x) * .5, (_hi.y - _lo.y) * .5, (_hi.z - _lo.z) * .5]
_mid = unreal.Vector((_lo.x + _hi.x) * .5, (_lo.y + _hi.y) * .5, (_lo.z + _hi.z) * .5)
_tlerp = getattr(unreal.MathLibrary, 't_lerp', None)
live.GUARD_TURNS = 4 if _tlerp else 1
def _trace(a, b):
    h = unreal.SystemLibrary.line_trace_single_by_profile(_world, a, b, 'Pawn', False, _skip, unreal.DrawDebugTrace.NONE, True)
    return h.to_tuple() if h else None
def _dot(a, b):
    return a.x * b.x + a.y * b.y + a.z * b.z
def _past(p, t):
    d = _dot(t[5] - p, t[7])
    if d <= .05:
        return 0.
    return d if _trace(p, p + t[7] * (d + 2.)) else 0.
def _named(t):
    return (t[10].get_name() if t[10] else '?') + '/' + (t[9].get_name() if t[9] else '?')
def _swept(xa, xb):
    s = xb.scale3d
    he = unreal.Vector(max(.5, _half[0] * s.x - 1.5), max(.5, _half[1] * s.y - 1.5), max(.5, _half[2] * s.z - 1.5))
    worst, what, last = 0., '', xa
    for k in range(1, live.GUARD_TURNS + 1):
        x = _tlerp(xa, xb, k / float(live.GUARD_TURNS)) if _tlerp else xb
        a = unreal.MathLibrary.transform_location(last, _mid)
        b = unreal.MathLibrary.transform_location(x, _mid)
        last = x
        h = unreal.SystemLibrary.box_trace_single_by_profile(_world, a, b, he, x.rotation.rotator(), 'Pawn', False, _skip,
                                                            unreal.DrawDebugTrace.NONE, True)
        if not h:
            continue
        t = h.to_tuple()
        if t[1] or t[7].z >= .7:
            continue
        past = (1. - t[2]) * math.sqrt(_dot(b - a, b - a))
        if past > worst:
            worst, what = past, 'swept ' + _named(t)
    return worst, what
def _guard(dt):
    try:
        xf = _deck.get_world_transform()
        o = _deck.get_world_location()
        pts = [o] + [unreal.MathLibrary.transform_location(xf, c) for c in _box]
        worst = {'wall': [0., ''], 'floor': [0., '']}
        def note(what, t, depth):
            kind = 'floor' if t[7].z >= .7 else 'wall'
            if depth > worst[kind][0]:
                worst[kind] = [depth, what + ' ' + _named(t)]
        inside = 0
        for i, p in enumerate(pts[1:]):
            t = _trace(o, p)
            if t is None:
                continue
            if t[1]:
                inside = 1
                break
            note('corner%d' % i, t, _past(p, t))
        prev = live.GUARD_PREV[0]
        if prev is not None:
            for i, (a, p) in enumerate(zip(prev, pts)):
                if _dot(p - a, p - a) < .0025:
                    continue
                t = _trace(a, p)
                if t is None or t[1] or _dot(a - t[5], t[7]) <= 0:
                    continue
                note(('top' if i == 0 else 'corner%d' % (i - 1)) + ' crossed', t, _past(p, t))
        state = live.skate_state()
        swept = [0., '']
        if live.GUARD_PREV_XF[0] is not None and ' mode=3 ' not in ' ' + state.split(' | ')[0] + ' ':
            swept = list(_swept(live.GUARD_PREV_XF[0], xf))
        # A deck hidden this frame (dissolved out, to come back in elsewhere: the get-up's board) is placed, not moved:
        # the next frame is not swept or crossed from it.
        hidden = ' vis=0 ' in ' ' + state.split(' | ')[0] + ' '
        live.GUARD_PREV[0] = None if hidden else pts
        live.GUARD_PREV_XF[0] = None if hidden else xf
        live.GUARD.append([state, round(worst['wall'][0], 2), worst['wall'][1], round(worst['floor'][0], 2),
                           worst['floor'][1], inside, round(swept[0], 2), swept[1]])
    except Exception as e:
        live.GUARD_ERR.append(repr(e))
live._guard = _guard
def _ground(x, y, z):
    h = _trace(unreal.Vector(x, y, z), unreal.Vector(x, y, z - 1500.))
    return None if h is None or h[1] else [h[5].x, h[5].y, h[5].z]
def _face(x, y, z, yaw, reach, heights):
    # From the ground under (x, y, z), a level trace along yaw at each height over it: the face each meets.
    g = _ground(x, y, z)
    if g is None:
        return None
    d = unreal.Vector(math.cos(math.radians(yaw)), math.sin(math.radians(yaw)), 0.)
    hits = []
    for up in heights:
        a = unreal.Vector(g[0], g[1], g[2] + up)
        t = _trace(a, a + d * reach)
        hits.append(None if t is None or t[1] else [t[3], [t[5].x, t[5].y, t[5].z], [t[7].x, t[7].y, t[7].z], _named(t)])
    # The ground along the way, at each quarter of the reach (None where there is none).
    path = [_ground(g[0] + d.x * reach * k / 4, g[1] + d.y * reach * k / 4, g[2] + 300.) for k in (1, 2, 3)]
    return {'ground': g, 'dir': [d.x, d.y], 'hits': hits, 'path': path}
live._ground = _ground
live._face = _face
