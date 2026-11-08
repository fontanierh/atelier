"""The Belmonte station (plain Python): every mesh of the terminus as track.Mesh LODs, in the station frame of
station_site.py, and the pieces track.json places. track_build.py exports them with the track; the tests check the
budgets without Blender. Design and references: games/yorimichi/docs/BELMONTE_STATION.md and
assets/belmonte/concepts/station/ (Paul's elevations, 2026-10-17).

A Tuscan terminus after King's Cross and Saint-Lazare: two glazed train sheds side by side (the line's track in the
south-west one, a decorative siding with three old coaches in the other), a clock tower between their great arches,
a Beaux-Arts headhouse in honey stone with an arcaded street front, iron canopies and lower terracotta-roofed wings.
The track arrives in a shallow cutting: platforms and concourse at platform level, the vestibule, forecourt and access
road at street level, a double staircase between them. The road's overbridge is overbridge.py's.

Meshes are built in the station frame (a along the track to the facade, u left, z up from the rail top) and turned
into the world frame relative to their piece origin (no rotation in Unreal, like every track piece). LOD2 is also
the collision of the walkable pieces: it keeps the openings, floors and stairs (as ramps).
"""
import math

import numpy as np

from train import station_site as S
from train import track as T

BAYS = 10                   # train-shed bays of BAY metres (the side elevations' rhythm, stretched to the train)
BAY = S.SHED_LENGTH / BAYS
SPAN = 22.                  # each shed's clear span
SPRING = S.STREET + 15.6    # the vaults spring at the headhouse cornice (front elevation: 15.6 m over the street)
RISE = 13.4                 # vault rise: crown at the arch keystone's height
SHEDS = ((0., 'main'), (S.SIDING, 'siding'))     # shed centre lines (u)
WALL = 1.5                  # outer shed walls, inner faces at u = 10.5 and -39.5
FRONT = S.HEADHOUSE[1]      # the street facade (a)
VEST = S.VESTIBULE[0]       # the vestibule's back wall; the stairs run from it down to STAIR_FOOT
STAIR_FOOT = 7.
SCREEN = 17.                # the great arch windows over the stair hall
TOWER = (19., 25.5, S.AXIS_U - 3.5, S.AXIS_U + 3.5)
TOWER_TOP = S.STREET + 38.
CORNICE = S.STREET + 15.6
WING_CORNICE = S.STREET + 16.6
GROUND_FLOOR = S.STREET + 7.3
FRONT_BAYS = 9              # arcade bays across the central block (u -41 .. 12)
SHED_START = -S.SHED_LENGTH
COACHES = (-12.5, -25.5, -38.5)     # coach centres (a) on the siding
COACH = (12., 2.7)
# --- building blocks in the station frame (a, u, z) ---------------------------------------------------------------


def box(m, a0, a1, u0, u1, z0, z1, mat, bottom=True):
    if a1 - a0 <= 1e-6 or u1 - u0 <= 1e-6 or z1 - z0 <= 1e-6:
        return m
    return T.box(m, ((a0 + a1) / 2, (u0 + u1) / 2, (z0 + z1) / 2), (a1 - a0, u1 - u0, z1 - z0), mat, bottom=bottom)


def prism_a(m, outline, a0, a1, mat):
    """A polygon in the (u, z) plane, counter-clockwise (u right, z up), extruded from a0 to a1, faces outward."""
    n = len(outline)
    verts = [(a0, u, z) for u, z in outline] + [(a1, u, z) for u, z in outline]
    faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
    faces += [(j, (j + 1) % n, n + (j + 1) % n, n + j) for j in range(n)]
    return m.add(verts, faces, mat)


def prism_u(m, outline, u0, u1, mat):
    """A polygon in the (a, z) plane, counter-clockwise (a right, z up), extruded from u0 to u1, faces outward."""
    n = len(outline)
    verts = [(a, u0, z) for a, z in outline] + [(a, u1, z) for a, z in outline]
    faces = [tuple(range(n)), tuple(range(2 * n - 1, n - 1, -1))]
    faces += [(j, n + j, n + (j + 1) % n, (j + 1) % n) for j in range(n)]
    return m.add(verts, faces, mat)


def bar(m, p, q, w, mat):
    """A square bar of width w from p to q (any direction)."""
    return T.cylinder(m, p, q, w / math.sqrt(2), mat, sides=4)


def arch(c, half, spring, rise, segs, start=0., end=math.pi):
    """Points (u, z) of a semi-ellipse over [c - half, c + half] springing at `spring`, from angle start to end
    (0 = the right springing, counter-clockwise)."""
    t = np.linspace(start, end, segs + 1)
    return [(c + half * math.cos(x), spring + rise * math.sin(x)) for x in t]


def arched_opening(c, half, sill, spring, segs):
    """The outline of a round-headed opening (u, z), counter-clockwise."""
    return [(c - half, sill), (c + half, sill), *arch(c, half, spring, half, segs)[:-1], (c - half, spring)]


def wall_with_openings(m, d0, d1, h0, h1, z0, z1, openings, mat, segs, along='u'):
    """A wall in the plane a (along='u': spans u h0..h1, thickness a d0..d1) or u (along='a') from z0 to z1, pierced by
    round-headed openings [(centre, half width, sill, spring)]: piers between them, a spandrel over each."""
    edges = sorted(openings)
    cursor = h0
    pieces = []
    for c, half, sill, spring in edges:
        pieces.append((cursor, c - half, z0, z1))
        if sill > z0:
            pieces.append((c - half, c + half, z0, sill))
        cursor = c + half
        # the spandrel over the arch: its soffit left to right (arch() runs right to left), then the top edge back
        top = spring + half
        outline = _ccw([(c - half, spring)] + arch(c, half, spring, half, segs)[::-1][1:-1] +
                       [(c + half, spring), (c + half, z1), (c - half, z1)])
        if top < z1:
            (prism_a if along == 'u' else _prism_a_as_u)(m, outline, d0, d1, mat)
    pieces.append((cursor, h1, z0, z1))
    for p0, p1, q0, q1 in pieces:
        if along == 'u':
            box(m, d0, d1, p0, p1, q0, q1, mat)
        else:
            box(m, p0, p1, d0, d1, q0, q1, mat)
    return m


def _prism_a_as_u(m, outline, d0, d1, mat):
    """A (h, z) outline for a wall running along a: h is a, extruded across u from d0 to d1."""
    return prism_u(m, _ccw(outline), d0, d1, mat)


def _ccw(outline):
    area = sum(x0 * z1 - x1 * z0 for (x0, z0), (x1, z1) in zip(outline, outline[1:] + outline[:1]))
    return outline if area > 0 else outline[::-1]


def sweep(m, pts, a0, a1, mat, closed=False):
    """A band through the (u, z) points pts, extruded from a0 to a1: a curved surface, faces towards +normal of the
    polyline's left side (outward for a counter-clockwise curve); both ends open."""
    n = len(pts)
    verts = [(a0, u, z) for u, z in pts] + [(a1, u, z) for u, z in pts]
    faces = [(n + j, j, j + 1, n + j + 1) for j in range(n - 1)]
    return m.add(verts, faces, mat)


def rib(m, pts, a0, a1, depth, mat):
    """A curved bar of `depth` under the (u, z) points pts (towards the arc's centre), a0..a1 thick."""
    inner = []
    for k, (u, z) in enumerate(pts):
        pu, pz = pts[max(k - 1, 0)]
        qu, qz = pts[min(k + 1, len(pts) - 1)]
        tu, tz = qu - pu, qz - pz
        norm = math.hypot(tu, tz) or 1.
        inner.append((u + tz / norm * depth, z - tu / norm * depth))
    outline = _ccw(list(pts) + inner[::-1])
    return prism_a(m, outline, a0, a1, mat)


def finial(m, a, u, z, size, mat, lod):
    """An urn finial on a pedestal: a stack of boxes (LOD0), one box beyond."""
    if lod > 0:
        return box(m, a - size / 2, a + size / 2, u - size / 2, u + size / 2, z, z + size * 1.6, mat)
    s = size
    box(m, a - s * .55, a + s * .55, u - s * .55, u + s * .55, z, z + s * .5, mat)
    box(m, a - s * .3, a + s * .3, u - s * .3, u + s * .3, z + s * .5, z + s * .7, mat)
    T.cylinder(m, (a, u, z + s * .7), (a, u, z + s * 1.5), s * .45, mat, sides=8)
    T.cylinder(m, (a, u, z + s * 1.5), (a, u, z + s * 2.), s * .12, mat, sides=6)
    return m


def balustrade(m, a0, a1, u0, u1, z, mat, lod, height=1.1):
    """A balustrade along a (u0 == u1 ... thickness) or along u: base, rail and balusters at LOD0."""
    box(m, a0, a1, u0, u1, z, z + .18, mat)
    box(m, a0, a1, u0, u1, z + height - .15, z + height, mat)
    if lod == 0:
        along_a = (a1 - a0) > (u1 - u0)
        length = (a1 - a0) if along_a else (u1 - u0)
        n = max(1, int(length / .45))
        for k in range(n):
            t = (k + .5) / n
            if along_a:
                a = a0 + t * (a1 - a0)
                box(m, a - .09, a + .09, u0 + .05, u1 - .05, z + .18, z + height - .15, mat)
            else:
                u = u0 + t * (u1 - u0)
                box(m, a0 + .05, a1 - .05, u - .09, u + .09, z + .18, z + height - .15, mat)
    elif lod == 1:
        box(m, a0 + .08, a1 - .08, u0 + .08, u1 - .08, z + .18, z + height - .15, mat)
    return m


# --- the train sheds ------------------------------------------------------------------------------------------------


def vault_profile(c, segs):
    return arch(c, SPAN / 2, SPRING, RISE, segs)


def sheds(lod):
    m = T.Mesh()
    a0 = SHED_START
    segs = (14, 8, 6)[lod]
    platform = S.PLATFORM
    base = S.FORMATION
    # Platforms: P1 between the main track and the south-west wall, the island between the tracks, P3 by the north-east
    # wall; stone copings at the edges.
    e = S.EDGE
    for u0, u1, edges in ((e, 10.5, (e,)), (S.SIDING + e, -e, (S.SIDING + e, -e)), (-39.5, S.SIDING - e, (S.SIDING - e,))):
        box(m, a0, .5, u0, u1, base, platform, 'MI_B_flag')
        if lod == 0:        # stone copings along the track edges
            for edge in edges:
                inner = edge + (.6 if edge == u0 else -.6)
                box(m, a0, .5, min(edge, inner) - .02, max(edge, inner), platform, platform + .03, 'MI_B_stone')
    # Outer walls: stone to the clerestory, arched windows between pilasters, the iron clerestory to the springing.
    clere = SPRING - 9.
    for side, (w0, w1) in (('sw', (10.5, 12.)), ('ne', (-41., -39.5))):
        outer = w1 if side == 'sw' else w0
        openings = []
        for k in range(BAYS):
            b0 = a0 + k * BAY
            for f in (.3, .7):
                openings.append((b0 + f * BAY, 1.5, platform + 4.5, platform + 9.))
        if lod < 2:
            wall_with_openings(m, w0, w1, a0, 0., base, clere, openings, 'MI_B_ashlar', (6, 3)[lod], along='a')
            mid = (w0 + w1) / 2
            for c, half, sill, spring in openings:
                box(m, c - half, c + half, mid - .03, mid + .03, sill, spring + half, 'MI_B_glass_dark')
        else:
            box(m, a0, 0., w0, w1, base, clere, 'MI_B_ashlar')
        # pilasters and the cornice outside
        if lod < 2:
            p0, p1 = (w1, w1 + .45) if side == 'sw' else (w0 - .45, w0)
            for k in range(BAYS + 1):
                b = a0 + k * BAY
                box(m, b - .7, b + .7, p0, p1, base, clere + .6, 'MI_B_stone')
        c0, c1 = (w1 - .2, w1 + .8) if side == 'sw' else (w0 - .8, w0 + .2)
        box(m, a0, 0., c0, c1, clere, clere + .7, 'MI_B_stone')
        # clerestory: iron posts per bay and half-bay, glazing bars (LOD0, open) or glass (LOD1+)
        g0, g1 = (w0 + .5, w0 + .7) if side == 'sw' else (w1 - .7, w1 - .5)
        if lod == 0:
            for k in range(BAYS * 2 + 1):
                b = a0 + k * BAY / 2
                box(m, b - .18, b + .18, g0 - .1, g1 + .1, clere + .7, SPRING, 'MI_ST_Green')
            for z in (clere + 3.5, clere + 6.3):
                box(m, a0, 0., g0, g1, z - .08, z + .08, 'MI_ST_Green')
            for k in range(BAYS * 8):
                b = a0 + (k + .5) * BAY / 8
                box(m, b - .04, b + .04, g0 + .05, g1 - .05, clere + .7, SPRING, 'MI_ST_Green')
        else:
            box(m, a0, 0., g0, g1, clere + .7, SPRING, 'MI_ST_Glass')
    # The spine between the sheds: iron columns at every bay and half bay on both edges, a box girder each side and a
    # flat gutter roof over the 7 m between.
    for u in (-11., -18.):
        for k in range(BAYS * 2 + 1):
            b = a0 + k * BAY / 2
            if lod == 0:
                T.cylinder(m, (b, u, platform), (b, u, SPRING - 1.2), .28, 'MI_ST_Green', sides=8)
                box(m, b - .45, b + .45, u - .45, u + .45, platform, platform + .9, 'MI_ST_Green')
                box(m, b - .5, b + .5, u - .5, u + .5, SPRING - 1.5, SPRING - 1.2, 'MI_ST_Green')
            elif lod == 1 or k % 2 == 0:
                box(m, b - .25, b + .25, u - .25, u + .25, platform, SPRING - 1.2, 'MI_ST_Green')
        box(m, a0, SCREEN, u - .35, u + .35, SPRING - 1.2, SPRING, 'MI_ST_Green')
        if lod == 0:        # arched brackets between the columns, under the girder
            half = BAY / 4
            for k in range(BAYS * 2):
                mid = a0 + k * BAY / 2 + half
                soffit = [(mid + half * math.cos(t), SPRING - 3. + 1.8 * math.sin(t)) for t in np.linspace(.15, math.pi - .15, 7)]
                outline = _ccw([(mid + half, SPRING - 1.2)] + [(mid + half, SPRING - 2.7)] + soffit[1:-1] +
                               [(mid - half, SPRING - 2.7), (mid - half, SPRING - 1.2)])
                prism_u(m, outline, u - .1, u + .1, 'MI_ST_Green')
    box(m, a0, SCREEN, -18.35, -10.65, SPRING, SPRING + .5, 'MI_B_stone')
    # Vaults: iron ribs and purlins with open glazing (LOD0), glass shells beyond.
    for c, _ in SHEDS:
        prof = vault_profile(c, segs)
        if lod == 0:
            n_ribs = BAYS * 4
            for k in range(n_ribs + 1):
                b = a0 + k * (SCREEN - a0) / n_ribs
                heavy = k % 4 == 0
                rib(m, prof, b - (.2 if heavy else .08), b + (.2 if heavy else .08), .9 if heavy else .3, 'MI_ST_Green')
                if heavy:       # trussed bay arch: an inner chord and diagonals
                    inner = [(c + (SPAN / 2 - 1.6) * math.cos(t), SPRING + (RISE - 1.6) * math.sin(t))
                             for t in np.linspace(0, math.pi, segs + 1)]
                    rib(m, inner, b - .12, b + .12, .2, 'MI_ST_Green')
                    for j in range(segs):
                        p, q = prof[j], inner[j + 1]
                        bar(m, (b, p[0], p[1]), (b, q[0], q[1]), .12, 'MI_ST_Green')
            for j in range(1, segs):
                u, z = prof[j]
                box(m, a0, SCREEN, u - .09, u + .09, z - .12, z + .06, 'MI_ST_Green')
            # the ridge lantern
            box(m, a0, SCREEN, c - 1.6, c + 1.6, SPRING + RISE, SPRING + RISE + 1.4, 'MI_ST_Green')
            box(m, a0, SCREEN, c - 1.9, c + 1.9, SPRING + RISE + 1.4, SPRING + RISE + 1.6, 'MI_ST_Green')
        else:
            sweep(m, prof[::-1], a0, SCREEN, 'MI_ST_Glass')
            for k in range(BAYS + 1):
                b = a0 + k * BAY
                rib(m, prof, b - .25, b + .25, .7, 'MI_ST_Green')
            box(m, a0, SCREEN, c - 1.6, c + 1.6, SPRING + RISE - .3, SPRING + RISE + 1.4, 'MI_ST_Green')
        # eaves gutters over the outer walls
    # The rear end: stone piers framing each shed's open arch, an iron screen over the trains' opening.
    rear0, rear1 = a0 - 2., a0 + .5
    for c, _ in SHEDS:
        prof = vault_profile(c, segs)
        ring = arch(c, SPAN / 2 + 1.4, SPRING, RISE + 1.4, segs)
        rib(m, ring, rear0, rear1, 1.4, 'MI_B_ashlar')
        transom = S.PLATFORM + 11.
        box(m, a0 - .3, a0 + .3, c - SPAN / 2, c + SPAN / 2, transom - .5, transom + .3, 'MI_ST_Green')
        if lod == 0:
            for j in range(1, 10):
                u = c - SPAN / 2 + j * SPAN / 10
                top = SPRING + RISE * math.sin(math.acos(max(-1., min(1., (u - c) / (SPAN / 2)))))
                box(m, a0 - .1, a0 + .1, u - .07, u + .07, transom, top, 'MI_ST_Green')
            for z in np.arange(transom + 2.5, SPRING + RISE, 2.5):
                half = SPAN / 2 * math.sqrt(max(0., 1 - ((z - SPRING) / RISE) ** 2)) if z > SPRING else SPAN / 2
                box(m, a0 - .1, a0 + .1, c - half, c + half, z - .06, z + .06, 'MI_ST_Green')
        else:
            outline = _ccw([(c + SPAN / 2, transom), *prof, (c - SPAN / 2, transom)])
            prism_a(m, outline, a0 - .05, a0 + .05, 'MI_ST_Glass')
    for u0, u1, top in ((10.5, 15., SPRING + RISE + 1.), (-44.5, -39.5, SPRING + RISE + 1.), (-19., -10., SPRING + 2.)):
        box(m, rear0, rear1 + 9. if u0 > 0 or u0 < -40 else rear1, u0, u1, S.FORMATION, top, 'MI_B_ashlar')
        box(m, rear0 - .4, rear1 + .4, u0 - .4, u1 + .4, top, top + .8, 'MI_B_stone')
        if lod < 2:
            finial(m, (rear0 + rear1) / 2, (u0 + u1) / 2, top + .8, 1.6, 'MI_B_stone', lod)
    # The front: the great arch windows over the stair hall, framed by an archivolt and a keystone cartouche.
    for c, _ in SHEDS:
        prof = vault_profile(c, segs)
        ring = arch(c, SPAN / 2 + 1.6, SPRING, RISE + 1.6, segs)
        rib(m, ring, SCREEN, VEST + .6, 1.6, 'MI_B_ashlar')
        box(m, SCREEN, VEST + 1., c - 1.3, c + 1.3, SPRING + RISE - .6, SPRING + RISE + 2.6, 'MI_B_stone')
        if lod < 2:
            finial(m, VEST, c, SPRING + RISE + 2.6, 1.4, 'MI_B_stone', lod)
        if lod == 0:        # mullions and transoms inside the arch, a fan of glazing bars round an inner ring
            rib(m, prof, SCREEN - .12, SCREEN + .12, .35, 'MI_ST_Green')
            inner = .55
            rib(m, arch(c, SPAN / 2 * inner, SPRING, RISE * inner, segs), SCREEN - .1, SCREEN + .1, .22, 'MI_ST_Green')
            for k in range(1, 12):
                u = c - SPAN / 2 + k * SPAN / 12
                x = (u - c) / (SPAN / 2)
                top = SPRING + RISE * math.sqrt(max(0., 1 - x * x))
                low = SPRING + RISE * inner * math.sqrt(max(0., 1 - (x / inner) ** 2)) if abs(x) < inner else SPRING
                box(m, SCREEN - .07, SCREEN + .07, u - .07, u + .07, low, top, 'MI_ST_Green')
            for z in np.arange(SPRING + 2.4, SPRING + RISE, 2.4):
                half = SPAN / 2 * math.sqrt(max(0., 1 - ((z - SPRING) / RISE) ** 2))
                inner_half = SPAN / 2 * inner * math.sqrt(max(0., 1 - ((z - SPRING) / (RISE * inner)) ** 2))
                for u0, u1 in ((c - half, c - inner_half), (c + inner_half, c + half)) if inner_half > 0 else ((c - half, c + half),):
                    box(m, SCREEN - .06, SCREEN + .06, u0, u1, z - .05, z + .05, 'MI_ST_Green')
            for t in np.linspace(0, math.pi, 9)[1:-1]:
                q = (c + SPAN / 2 * inner * math.cos(t), SPRING + RISE * inner * math.sin(t))
                bar(m, (SCREEN, c, SPRING), (SCREEN, *q), .09, 'MI_ST_Green')
            box(m, SCREEN - .12, SCREEN + .12, c - SPAN / 2, c + SPAN / 2, SPRING - .25, SPRING + .1, 'MI_ST_Green')
        else:
            prism_a(m, _ccw([(c + SPAN / 2, SPRING), *prof[1:-1], (c - SPAN / 2, SPRING)]), SCREEN - .05, SCREEN + .05,
                    'MI_ST_Glass')
    # The outer pylons framing the arches on the street side, and the gutter walls over the outer shed walls.
    for u0, u1 in ((10., 13.5), (-42.5, -39.)):
        box(m, 15., FRONT + .5, u0, u1, S.FORMATION, S.STREET + 18., 'MI_B_ashlar')
        box(m, 14.6, FRONT + .9, u0 - .4, u1 + .4, S.STREET + 18., S.STREET + 18.8, 'MI_B_stone')
        if lod < 2:
            finial(m, (15. + FRONT + .5) / 2, (u0 + u1) / 2, S.STREET + 18.8, 2.2, 'MI_B_stone', lod)
    for u0, u1 in ((10.5, 12.6), (-41.6, -39.5)):
        box(m, a0, 15., u0, u1, SPRING - .4, SPRING + .9, 'MI_B_stone')
    # The decorative siding: ballast, two rails, sleepers (LOD0) and a buffer stop at each end.
    s0, s1 = a0 + 2., -2.
    box(m, s0 - 1., s1 + 1., S.SIDING - 1.7, S.SIDING + 1.7, base, -.2, 'MI_B_gravel')
    for side in (-1., 1.):
        u = S.SIDING + side * T.GAUGE / 2
        box(m, s0, s1, u - .035, u + .035, -.15, 0., 'MI_B_iron')
    if lod == 0:
        for b in np.arange(s0, s1, T.SLEEPER_SPACING):
            box(m, b - .125, b + .125, S.SIDING - 1.3, S.SIDING + 1.3, -.2, -.05, 'MI_B_wood')
    if lod < 2:
        for end, sign in ((s0, -1.), (s1, 1.)):
            box(m, end - .3 * sign - .3, end - .3 * sign + .3, S.SIDING - 1.2, S.SIDING + 1.2, 0., 1.4, 'MI_B_wood')
            box(m, end + .4 * sign - .5, end + .4 * sign + .5, S.SIDING - 1.4, S.SIDING + 1.4, -.2, .3, 'MI_B_stone')
    # The concourse at platform level between the buffer stops and the stairs.
    box(m, .5, STAIR_FOOT, -39.5, 10.5, base, platform, 'MI_B_flag')
    return m


# --- the headhouse --------------------------------------------------------------------------------------------------


def headhouse(lod):
    m = T.Mesh()
    segs = (8, 4, 3)[lod]
    st, base = S.STREET, S.FORMATION
    c0, c1 = -41., 12.                          # the central block between the wings
    width = (c1 - c0) / FRONT_BAYS
    # The stair hall: two flights from the vestibule down to the concourse, one per shed, a landing between.
    flights = ((-8., 8.), (-37., -21.))
    drop = st - S.PLATFORM
    for f0, f1 in flights:
        if lod == 0:
            n = int(round(drop / .17))
            run = (VEST - STAIR_FOOT) / n
            outline = [(STAIR_FOOT, base), (VEST, base), (VEST, st)]
            for k in range(n, 0, -1):
                a = STAIR_FOOT + k * run
                z = S.PLATFORM + k * drop / n
                outline += [(a, z), (a - run, z)] if k > 1 else [(a, z), (STAIR_FOOT, z)]
            outline.append((STAIR_FOOT, S.PLATFORM))
            prism_u(m, _ccw(outline), f0, f1, 'MI_B_stone')
        else:
            prism_u(m, _ccw([(STAIR_FOOT, base), (VEST, base), (VEST, st), (STAIR_FOOT, S.PLATFORM)]), f0, f1, 'MI_B_stone')
    # landings and side blocks at street level between and beside the flights
    for u0, u1, edges in ((-21., -8., (-21., -8.)), (8., 10.5, (8.,)), (-39.5, -37., (-37.,))):
        box(m, STAIR_FOOT, VEST, u0, u1, base, st, 'MI_B_ashlar')
        for edge in edges:      # balustrades along the flights
            inner = (edge, edge + .35) if edge == u0 else (edge - .35, edge)
            balustrade(m, STAIR_FOOT, VEST, inner[0], inner[1], st, 'MI_B_stone', lod)
        balustrade(m, STAIR_FOOT, STAIR_FOOT + .35, u0, u1, st, 'MI_B_stone', lod)     # over the concourse
    # The vestibule: floor at street level, ceiling under the first floor, the back wall open onto the stairs.
    box(m, VEST, FRONT, c0, c1, base, st, 'MI_B_flag')
    box(m, VEST, FRONT - .8, c0, c1, GROUND_FLOOR, GROUND_FLOOR + .6, 'MI_B_plaster')
    back = [((f0 + f1) / 2, 5., st, GROUND_FLOOR - 5.) for f0, f1 in flights]     # an arch onto each flight
    wall_with_openings(m, VEST - .8, VEST, c0, c1, st, CORNICE, back, 'MI_B_ashlar', segs)
    # The street front: nine open arches, pilasters, first-floor windows, cornice, balustrade.
    arches = [(c0 + (k + .5) * width, width / 2 - .85, st, st + 4.5) for k in range(FRONT_BAYS)]
    wall_with_openings(m, FRONT - .8, FRONT, c0, c1, st, GROUND_FLOOR, arches, 'MI_B_ashlar', segs)
    box(m, FRONT - .8, FRONT, c0, c1, base, st, 'MI_B_ashlar')
    windows = [(c0 + (k + .5) * width, .95, GROUND_FLOOR + 1.6, GROUND_FLOOR + 4.6) for k in range(FRONT_BAYS)]
    if lod < 2:
        wall_with_openings(m, FRONT - .8, FRONT, c0, c1, GROUND_FLOOR, CORNICE, windows, 'MI_B_ashlar', segs)
        for c, half, sill, spring in windows:
            box(m, FRONT - .55, FRONT - .45, c - half, c + half, sill, spring + half, 'MI_B_glass_dark')
            if lod == 0:
                box(m, FRONT, FRONT + .5, c - half - .3, c + half + .3, sill - .25, sill, 'MI_B_stone')
                balustrade(m, FRONT, FRONT + .45, c - half - .2, c + half + .2, sill, 'MI_B_stone', lod, .9)
    else:
        box(m, FRONT - .8, FRONT, c0, c1, GROUND_FLOOR, CORNICE, 'MI_B_ashlar')
    # the hall's ceiling and the first floor's solid mass behind the facade
    box(m, VEST, FRONT - .8, c0, c1, GROUND_FLOOR + .6, CORNICE, 'MI_B_ashlar')
    if lod < 2:
        for k in range(FRONT_BAYS + 1):
            u = c0 + k * width
            box(m, FRONT, FRONT + .35, u - .55, u + .55, st, GROUND_FLOOR, 'MI_B_stone')
            box(m, FRONT, FRONT + .3, u - .45, u + .45, GROUND_FLOOR + .5, CORNICE - .6, 'MI_B_stone')
            if lod == 0:
                box(m, FRONT, FRONT + .45, u - .6, u + .6, CORNICE - 1., CORNICE - .6, 'MI_B_stone')   # capitals
        box(m, FRONT, FRONT + .5, c0, c1, GROUND_FLOOR, GROUND_FLOOR + .5, 'MI_B_stone')             # string course
    box(m, VEST - .9, FRONT + .9, c0 - .2, c1 + .2, CORNICE, CORNICE + .7, 'MI_B_stone')             # cornice
    box(m, VEST - .9, FRONT, c0, c1, CORNICE + .7, CORNICE + .75, 'MI_B_stone')                     # roof
    balustrade(m, FRONT + .2, FRONT + .7, c0, c1, CORNICE + .7, 'MI_B_stone', lod)
    if lod < 2:
        for k in range(FRONT_BAYS + 1):
            finial(m, FRONT + .45, c0 + k * width, CORNICE + 1.8, .9, 'MI_B_stone', lod)
    # The pediment under the tower, with its cartouche.
    pu0, pu1 = S.AXIS_U - 1.5 * width, S.AXIS_U + 1.5 * width
    prism_a(m, _ccw([(pu0, CORNICE + .7), (pu1, CORNICE + .7), (S.AXIS_U, CORNICE + 4.6)]), FRONT - .6, FRONT + .6, 'MI_B_ashlar')
    if lod < 2:
        box(m, FRONT + .5, FRONT + .9, S.AXIS_U - 1.6, S.AXIS_U + 1.6, CORNICE + 1.1, CORNICE + 3.6, 'MI_B_stone')
    # The canopies: iron and glass over the three arcade groups, on wall brackets, with a lace valance.
    if lod < 2:
        for g in range(3):
            u0, u1 = c0 + g * 3 * width + .4, c0 + (g + 1) * 3 * width - .4
            z = st + 5.9
            box(m, FRONT, FRONT + 4.2, u0, u1, z, z + .12, 'MI_ST_Glass')
            box(m, FRONT, FRONT + 4.3, u0 - .1, u0 + .1, z - .1, z + .2, 'MI_ST_Green')
            box(m, FRONT, FRONT + 4.3, u1 - .1, u1 + .1, z - .1, z + .2, 'MI_ST_Green')
            box(m, FRONT + 4.1, FRONT + 4.35, u0, u1, z - .5, z + .25, 'MI_ST_Green')
            if lod == 0:
                for k in range(7):
                    u = u0 + (k + .5) * (u1 - u0) / 7
                    bar(m, (FRONT, u, z - 1.6), (FRONT + 3.4, u, z), .12, 'MI_ST_Green')
                for k in range(int((u1 - u0) / .6)):
                    u = u0 + (k + .5) * .6
                    box(m, FRONT + 4.15, FRONT + 4.3, u - .05, u + .05, z - .9, z - .5, 'MI_ST_Green')
                for u in (u0 - .6, u1 + .6):     # wall lanterns
                    box(m, FRONT, FRONT + .5, u - .06, u + .06, st + 3.6, st + 3.75, 'MI_ST_Green')
                    box(m, FRONT + .3, FRONT + .6, u - .15, u + .15, st + 3.2, st + 3.7, 'MI_ST_Clock')
    # The clock tower: a brick shaft with stone quoins, four dials, a belfry cornice and a tiled spire.
    a0, a1, u0, u1 = TOWER
    box(m, a0, a1, u0, u1, GROUND_FLOOR, TOWER_TOP, 'MI_B_plaster')
    if lod < 2:
        for a in (a0, a1):
            for u in (u0, u1):
                box(m, a - .3, a + .3, u - .3, u + .3, CORNICE, TOWER_TOP, 'MI_B_ashlar')
    clock = TOWER_TOP - 7.
    box(m, a0 - .4, a1 + .4, u0 - .4, u1 + .4, clock - 3., clock - 2.6, 'MI_B_stone')
    box(m, a0 - .2, a1 + .2, u0 - .2, u1 + .2, clock - 2.6, TOWER_TOP - 1.5, 'MI_B_ashlar')
    dial = 2.3
    sides = (24, 12, 8)[lod]
    for normal, centre in (((1, 0), (a1 + .2, S.AXIS_U)), ((-1, 0), (a0 - .2, S.AXIS_U)),
                           ((0, 1), ((a0 + a1) / 2, u1 + .2)), ((0, -1), ((a0 + a1) / 2, u0 - .2))):
        na, nu = normal
        p = (centre[0], centre[1], clock + .4)
        q = (centre[0] + na * .12, centre[1] + nu * .12, clock + .4)
        T.cylinder(m, p, q, dial, 'MI_ST_Clock', sides=sides)
        if lod < 2:         # the stone ring stands just behind the dial's face
            T.cylinder(m, (p[0] - na * .05, p[1] - nu * .05, p[2]), (p[0] + na * .08, p[1] + nu * .08, p[2]), dial + .3,
                       'MI_B_stone', sides=sides)
            # hands at ten past ten
            tip = .14
            for length, angle in ((dial * .55, math.radians(60)), (dial * .85, math.radians(-60))):
                du, dz = math.sin(angle) * length, math.cos(angle) * length
                start = (q[0] + na * .03, q[1] + nu * .03, q[2])
                if na:
                    end = (start[0], start[1] - na * du, start[2] + dz)
                else:
                    end = (start[0] + nu * du, start[1], start[2] + dz)
                bar(m, start, end, tip, 'MI_B_iron')
    box(m, a0 - .7, a1 + .7, u0 - .7, u1 + .7, TOWER_TOP - 1.5, TOWER_TOP, 'MI_B_stone')
    if lod < 2:
        balustrade(m, a0 - .6, a1 + .6, u0 - .6, u0 - .2, TOWER_TOP, 'MI_B_stone', lod, .9)
        balustrade(m, a0 - .6, a1 + .6, u1 + .2, u1 + .6, TOWER_TOP, 'MI_B_stone', lod, .9)
    # the belfry's open lantern and the tiled pyramid
    if lod == 0:
        for a in (a0 + .6, a1 - .6):
            for u in (u0 + .6, u1 - .6):
                box(m, a - .45, a + .45, u - .45, u + .45, TOWER_TOP, TOWER_TOP + 3.4, 'MI_B_ashlar')
        box(m, a0 + .1, a1 - .1, u0 + .1, u1 - .1, TOWER_TOP, TOWER_TOP + .2, 'MI_B_stone')
    else:
        box(m, a0 + .2, a1 - .2, u0 + .2, u1 - .2, TOWER_TOP, TOWER_TOP + 3.4, 'MI_B_ashlar')
    roof = TOWER_TOP + 3.4
    box(m, a0 - .2, a1 + .2, u0 - .2, u1 + .2, roof, roof + .5, 'MI_B_stone')
    apex = ((a0 + a1) / 2, (u0 + u1) / 2, roof + 4.2)
    corners = [(a0 - .1, u0 - .1), (a1 + .1, u0 - .1), (a1 + .1, u1 + .1), (a0 - .1, u1 + .1)]
    verts = [(a, u, roof + .5) for a, u in corners] + [apex]
    m.add(verts, [(0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)], 'MI_B_roof')
    T.cylinder(m, apex, (apex[0], apex[1], apex[2] + 3.6), .1, 'MI_ST_Green', sides=6)
    if lod == 0:
        T.cylinder(m, (apex[0], apex[1], apex[2] + .4), (apex[0], apex[1], apex[2] + 1.1), .35, 'MI_ST_Green', sides=8)
    # The wings: two storeys of brick panels between stone pilasters, arched ground-floor doors (closed), pedimented
    # windows, a cornice and a hipped terracotta roof; corner pavilions with finials.
    for w0, w1 in ((c1, S.HEADHOUSE[3]), (S.HEADHOUSE[2], c0)):
        wing(m, w0, w1, lod, segs, outer=w1 if w0 == c1 else w0)
    return m


def wing(m, w0, w1, lod, segs, outer):
    st, base = S.STREET, S.FORMATION
    a0, a1 = S.HEADHOUSE[0], FRONT
    box(m, a0, a1, w0, w1, base, WING_CORNICE, 'MI_B_plaster')
    if lod < 2:
        # quoins and pilasters at the corners and the bay lines of the street front and the outer side
        for u in np.linspace(w0, w1, 4):
            box(m, a1, a1 + .3, u - .5, u + .5, st, WING_CORNICE, 'MI_B_ashlar')
        for a in np.linspace(a0, a1, 5):
            face = (outer, outer + .3) if outer == w1 else (outer - .3, outer)
            box(m, a - .5, a + .5, face[0], face[1], st - 1., WING_CORNICE, 'MI_B_ashlar')
        box(m, a1, a1 + .4, w0, w1, st, st + 1.2, 'MI_B_ashlar')                       # plinth
        box(m, a1, a1 + .35, w0, w1, GROUND_FLOOR - .2, GROUND_FLOOR + .3, 'MI_B_stone')
        bay = (w1 - w0) / 3
        for k in range(3):
            u = w0 + (k + .5) * bay
            # ground floor: an arched door, glazed, in a stone surround
            box(m, a1, a1 + .25, u - 1.7, u + 1.7, st + 1.2, st + 5.6, 'MI_B_ashlar')
            box(m, a1 + .25, a1 + .3, u - 1.3, u + 1.3, st + 1.2, st + 4.6, 'MI_B_glass_dark')
            if lod == 0:
                prism_a(m, _ccw(arch(u, 1.3, st + 4.6, 1.0, segs)), a1 + .25, a1 + .3, 'MI_B_glass_dark')
            # first floor: a window with a pediment
            box(m, a1, a1 + .25, u - 1.2, u + 1.2, GROUND_FLOOR + 1., GROUND_FLOOR + 5.2, 'MI_B_ashlar')
            box(m, a1 + .25, a1 + .3, u - .9, u + .9, GROUND_FLOOR + 1.3, GROUND_FLOOR + 4.8, 'MI_B_glass_dark')
            if lod == 0:
                prism_a(m, [(u - 1.5, GROUND_FLOOR + 5.2), (u + 1.5, GROUND_FLOOR + 5.2), (u, GROUND_FLOOR + 6.2)],
                        a1, a1 + .45, 'MI_B_stone')
                balustrade(m, a1 + .3, a1 + .7, u - 1.1, u + 1.1, GROUND_FLOOR + 1., 'MI_B_stone', lod, .8)
        # the outer side: four windows per floor
        side_bay = (a1 - a0) / 4
        face = (outer, outer + .3) if outer == w1 else (outer - .3, outer)
        glass = (outer + .3, outer + .35) if outer == w1 else (outer - .35, outer - .3)
        for k in range(4):
            a = a0 + (k + .5) * side_bay
            for z0, z1 in ((st + 1.5, st + 5.), (GROUND_FLOOR + 1.3, GROUND_FLOOR + 4.8)):
                box(m, a - 1.2, a + 1.2, face[0], face[1], z0 - .3, z1 + .3, 'MI_B_ashlar')
                box(m, a - .9, a + .9, glass[0], glass[1], z0, z1, 'MI_B_glass_dark')
    box(m, a0 - .6, a1 + .7, w0 - (.7 if outer == w0 else 0.), w1 + (.7 if outer == w1 else 0.), WING_CORNICE,
        WING_CORNICE + .6, 'MI_B_stone')
    balustrade(m, a1 + .2, a1 + .6, w0, w1, WING_CORNICE + .6, 'MI_B_stone', lod)
    # the hipped roof
    r0, r1 = (a0 + .3, a1 - .3), (w0 + .3, w1 - .3)
    z0, ridge = WING_CORNICE + .6, WING_CORNICE + 3.5
    inset = min(r1[1] - r1[0], r0[1] - r0[0]) / 2
    ra = ((r0[0] + r0[1]) / 2, (r0[0] + r0[1]) / 2)
    ua = ((r1[0] + r1[1]) / 2, (r1[0] + r1[1]) / 2)
    if r0[1] - r0[0] > r1[1] - r1[0]:
        ra = (r0[0] + inset, r0[1] - inset)
    else:
        ua = (r1[0] + inset, r1[1] - inset)
    v = [(r0[0], r1[0], z0), (r0[1], r1[0], z0), (r0[1], r1[1], z0), (r0[0], r1[1], z0),
         (ra[0], ua[0], ridge), (ra[1], ua[1], ridge)]
    m.add(v, [(0, 1, 5, 4), (1, 2, 5), (2, 3, 4, 5), (3, 0, 4)], 'MI_B_roof')
    if lod < 2:
        for a in (a0, a1):
            u = outer
            finial(m, a + (.3 if a == a0 else -.3), u + (-.3 if outer == w1 else .3), WING_CORNICE + .6, 1.2, 'MI_B_stone', lod)
        for k in range(2):      # chimneys
            a = a0 + (k + 1) * (a1 - a0) / 3
            u = (w0 + w1) / 2
            box(m, a - .5, a + .5, u - .5, u + .5, WING_CORNICE, ridge + 1.2, 'MI_B_ashlar')
    return m


# --- the old coaches on the siding ----------------------------------------------------------------------------------


def coaches(lod):
    m = T.Mesh()
    length, width = COACH
    for a in COACHES:
        a0, a1 = a - length / 2, a + length / 2
        u0, u1 = S.SIDING - width / 2, S.SIDING + width / 2
        if lod == 2:
            box(m, a0, a1, u0, u1, .5, 3.9, 'MI_ST_Coach')
            continue
        box(m, a0 + .3, a1 - .3, S.SIDING - 1., S.SIDING + 1., .55, 1.05, 'MI_B_iron')         # underframe
        box(m, a0 + 1.2, a1 - 1.2, u0, u1, 1.05, 3.55, 'MI_ST_Coach')                          # body
        roof = [(u1 + .1, 3.55), *arch(S.SIDING, width / 2 + .1, 3.55, .45, (6, 4)[lod])[1:-1], (u0 - .1, 3.55)]
        prism_a(m, _ccw(roof), a0 + .4, a1 - .4, 'MI_ST_CoachRoof')
        for end in (a0, a1):                                                                     # open end platforms
            e0, e1 = (end, end + 1.2) if end == a0 else (end - 1.2, end)
            box(m, e0, e1, u0 + .1, u1 - .1, .95, 1.1, 'MI_B_wood')
            if lod == 0:
                for u in (u0 + .15, u1 - .15):
                    box(m, e0 + .05, e1 - .05, u - .03, u + .03, 1.9, 1.98, 'MI_B_iron')
                    box(m, (e0 + e1) / 2 - .03, (e0 + e1) / 2 + .03, u - .03, u + .03, 1.1, 1.98, 'MI_B_iron')
                buffer_a = end - .35 if end == a0 else end + .35
                for u in (S.SIDING - .85, S.SIDING + .85):
                    T.cylinder(m, (end, u, .95), (buffer_a, u, .95), .17, 'MI_B_iron', sides=8)
        if lod == 0:
            for k in range(8):                                                                    # windows
                wa = a0 + 1.7 + (k + .5) * (length - 3.4) / 8
                for face in (u0 - .02, u1 + .02):
                    box(m, wa - .32, wa + .32, min(face, face + .01), max(face, face + .01), 2.15, 3.1, 'MI_B_glass_dark')
            for wa in (a - 3., a + 3.):                                                            # axles and wheels
                for u in (S.SIDING - .72, S.SIDING + .72):
                    T.cylinder(m, (wa, u - .07, .5), (wa, u + .07, .5), .5, 'MI_B_iron', sides=10)
        else:
            for wa in (a - 3., a + 3.):
                box(m, wa - .5, wa + .5, S.SIDING - .8, S.SIDING + .8, 0., 1., 'MI_B_iron')
    return m


# --- the whole station ----------------------------------------------------------------------------------------------


def to_world(mesh, site):
    """The station-frame mesh turned into the world axes (still relative to the station origin)."""
    v = np.asarray(mesh.verts, float)
    if not len(v):
        return mesh
    a, u, z = v[:, 0], v[:, 1], v[:, 2]
    x = a * site.t[0] + u * site.n[0]
    y = a * site.t[1] + u * site.n[1]
    out = T.Mesh(verts=[tuple(map(float, p)) for p in np.c_[x, y, z]], faces=list(mesh.faces), mats=list(mesh.mats))
    return out


# --- forecourt and access road --------------------------------------------------------------------------------------


PAVING = .02                # the forecourt's and the access road's paving over their ground (street level)


def forecourt(site, lod):
    """The paved square at street level and the access road (cobbles, a kerb along the square's edges), relative to
    the station origin; the road starts on the square's front edge and follows its carved floor (site.access_z), its
    end dipping under the junction's ground. The paving stands PAVING over the ground, flush with the vestibule's
    floor at the facade."""
    m = T.Mesh()
    a0, a1, u0, u1 = S.FORECOURT
    st = S.STREET
    box(m, a0 - .5, a1, u0, u1, st - .6, st + PAVING, 'MI_B_cobble')
    if lod < 2:
        box(m, a0, a1, u0 - .3, u0, st, st + .18, 'MI_B_stone')
        box(m, a0, a1, u1, u1 + .3, st, st + .18, 'MI_B_stone')
    pts, _ = site.access()
    rel = np.array([site.local(x, y) for x, y in pts])
    lengths = np.hypot(*np.diff(rel, axis=0).T)
    cum = np.concatenate([[0.], np.cumsum(lengths)])
    total = float(cum[-1])
    stops = np.unique(np.concatenate([cum, [S.ACCESS_FLAT]] if S.ACCESS_FLAT < total else [cum]))

    def at(s_):
        k = min(int(np.searchsorted(cum, s_, side='right')) - 1, len(lengths) - 1)
        d = (rel[k + 1] - rel[k]) / lengths[k]
        return rel[k] + d * (s_ - cum[k]), d, float(site.access_z(s_ / total)) - site.rail

    def slab(top):
        v = top + [(a, u, z - .6) for a, u, z in top]
        m.add(v, [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)], 'MI_B_cobble')
    for sa, sb in zip(stops[:-1], stops[1:]):
        (p, d, za), (q, _, zb) = at(sa), at(sb)
        n = np.array([-d[1], d[0]]) * 3.5
        left, right = p - n, p + n
        if sa == 0.:            # the road leaves the square's front edge at a slant: start it on that edge
            left, right = (c + d * (a1 - c[0]) / d[0] for c in (left, right))
        slab([(*left, za + PAVING), (*(q - n), zb + PAVING), (*(q + n), zb + PAVING), (*right, za + PAVING)])
    if lod < 2:                 # the road's end dips under the junction's ground: no paving edge shows there
        q, d, zb = at(total)
        n, r = np.array([-d[1], d[0]]) * 3.5, q + d * 1.5
        slab([(*(q - n), zb + PAVING), (*(r - n), zb - .04), (*(r + n), zb - .04), (*(q + n), zb + PAVING)])
    if lod == 0:        # lamp posts along the square
        for u in (u0 + 2., u1 - 2.):
            for a in (a0 + 4., a1 - 3.):
                T.cylinder(m, (a, u, st), (a, u, st + 4.2), .09, 'MI_ST_Green', sides=6)
                box(m, a - .25, a + .25, u - .25, u + .25, st + 4.2, st + 4.8, 'MI_ST_Clock')
    return m


def layout(line, *, make=None):
    """(meshes {name: [LODs]}, the station's record for track.json) at the end of a line ending at the station's site,
    else ({}, None). The road's overbridge is overbridge.py's."""
    make = make or (lambda builder, *args: builder(*args))
    end, before = line.frame(line.length)[0], line.frame(line.length - 10.)[0]
    site = S.for_line([before[:2], end[:2]], [before[2], end[2]])
    if site is None:
        return {}, None
    origin = (*site.origin, site.rail)
    meshes = {
        'SM_ST_Headhouse': [make(to_world, make(headhouse, k), site) for k in range(3)],
        'SM_ST_Sheds': [make(to_world, make(sheds, k), site) for k in range(3)],
        'SM_ST_Coaches': [make(to_world, make(coaches, k), site) for k in range(3)],
        'SM_ST_Forecourt': [make(to_world, make(forecourt, site, k), site) for k in range(3)],
    }
    rows = [dict(name=name, origin=[round(float(c), 3) for c in origin], collision=f'LOD{len(meshes[name]) - 1}')
            for name in meshes]
    doc = dict(pieces=rows, frame=dict(origin=list(origin), along=[round(float(c), 6) for c in site.t],
                                       left=[round(float(c), 6) for c in site.n]),
               levels=dict(rail=round(site.rail, 3), platform=round(site.rail + S.PLATFORM, 3),
                           street=round(site.rail + S.STREET, 3)),
               access=[[round(float(x), 2), round(float(y), 2)] for x, y in site.access()[0]])
    return meshes, doc
