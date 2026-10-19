"""Hidamari stable (陽だまり厩舎), Blender, headless: `atelier build yorimichi world.hidamari_stable`.

Builds Henry's racing stable from layout.py with Hidamari's building kit (village.build.Mesh, one vertex-colour
material, kawara tile roofs): a long timber barn (umaya) with a central aisle, ten stalls, a tack room and the
jockeys' office; the roofed entrance gate with the name plate, the sand yard (trough, hitching rail, stone lanterns),
the fenced paddock, the yard's ground overlays and the earth road from the end of Hidamari's street. The pad itself
and its slopes are Hidamari's own terrain (layout.grade).

Outputs in build/yorimichi/hidamari-stable/:
- hidamari-stable.blend: every LOD in its own collection, collision boxes and anchors as empties.
- glb/SM_HS_Stable_LOD0/1/2.glb: the stable, one material (M_HS_Stable, vertex colours); glb/SM_HS_StallDoor_LOD0/1/2
  and SM_HS_RoomDoor_LOD0/1/2: the sliding door leaves (origin at the closed leaf's bottom centre, placed by the
  placements); glb/SM_HS_Ground.glb (the yard and paddock overlays) and SM_HS_Road.glb (the road), both walkable and
  in Hidamari's surfaces (HDS_<slug> slots); SM_HS_RoadSign.glb (the lanterns and sign where the road leaves the street);
  glb/SM_HS_Stable_Collision.glb: the UCX_ boxes.
- placements.json: the site, every mesh with its placement, the stalls (door pivots, name plates, horse spots), the
  rooms, the sign and notice board anchors, NPC spots, the road and the island clearance polygons.
- manifest.json: triangle counts per LOD, budgets, checksums and checks.

All meshes are in the stable's frame (layout.py): metres, origin on the pad's top at SITE, Blender's standard glTF
export (Y-up).
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import hashlib
import json
import math
import random

import bpy
import numpy as np

from village import build as v
from hidamari import surfaces
from hidamari import arcade
from hidamari import layout as H
from hidamari.kit import kawara
from hidamari.kit._lettering import raised_text
from hippodrome import layout as HL
from hidamari_stable import layout as L

OUT = yori.OUT / 'hidamari-stable'
GLB = OUT / 'glb'
R = random.Random(1907)
MATERIAL = 'M_HS_Stable'


def palette():
    arcade.palette(); kawara.palette()
    v.PALETTE.update({
        'hs_char': (.030, .027, .028), 'hs_char_light': (.055, .046, .040),     # charred cedar boards (yakisugi)
        'hs_plaster': (.60, .52, .38), 'hs_timber': (.13, .065, .025), 'hs_timber_light': (.23, .125, .052),
        'hs_timber_dark': (.06, .03, .014), 'hs_stone': (.30, .275, .22), 'hs_stone_dark': (.17, .16, .13),
        'hs_sand': (.46, .36, .21), 'hs_soil': (.19, .13, .07), 'hs_straw': (.56, .41, .15), 'hs_hay': (.62, .47, .17),
        'hs_floor': (.21, .11, .045), 'hs_iron': (.05, .05, .055), 'hs_cork': (.42, .25, .10), 'hs_card': (.70, .63, .50),
        'hs_pin': (.60, .08, .04), 'hs_plate': (.62, .55, .40), 'hs_sign': (.07, .04, .02), 'hs_letter': (.70, .60, .40),
        'hs_grass': H.ISLAND_LAWN, 'hs_gravel': (.22, .20, .165), 'hs_bamboo': (.40, .37, .15), 'hs_rope': (.48, .36, .18),
        'hs_water': (.06, .14, .095), 'hs_leather': (.24, .09, .03), 'hs_pad': (.08, .13, .22), 'hs_gold': (.62, .42, .10),
        'hs_maple': (.70, .20, .03), 'hs_maple_b': (.80, .38, .04), 'hs_pine': (.05, .09, .04), 'hs_bark': (.12, .07, .04),
        'hs_bush': (.055, .11, .03), 'hs_bush_b': (.075, .13, .035), 'hs_azalea': (.55, .10, .16),
        'hs_felt': (.50, .05, .035), 'hs_parasol': (.62, .09, .05), 'hs_red': (.48, .07, .04), 'hs_rock': (.22, .21, .18),
        'hs_bed': (.10, .12, .03), 'hs_yard_earth': (.18, .14, .09), 'hs_lane_earth': (.15, .115, .07),   # Hidamari's hd_yard and garden gravel
        'hs_trim_wood': (.17, .10, .05),     # kawara.KEYS' rafters and fascias (kit/house.py)
    })


# ------------------------------------------------------------------ helpers
def spans(a0, a1, holes):
    return L._spans(a0, a1, holes)


def wall(m, axis, a0, a1, c, thick, z0, z1, holes, key):
    """A wall along `axis` ('x' or 'y') from a0 to a1 at the other coordinate c, between z0 and z1, with rectangular
    holes (h0, h1, hz0, hz1)."""
    cuts = sorted({a0, a1, *[h for q in holes for h in q[:2] if a0 < h < a1]})
    for s0, s1 in zip(cuts, cuts[1:]):
        mid = (s0 + s1) / 2
        blocked = [(q[2], q[3]) for q in holes if q[0] <= mid <= q[1]]
        for zz0, zz1 in spans(z0, z1, blocked):
            if axis == 'x':
                m.box(((s0 + s1) / 2, c, (zz0 + zz1) / 2), (s1 - s0, thick, zz1 - zz0), key)
            else:
                m.box((c, (s0 + s1) / 2, (zz0 + zz1) / 2), (thick, s1 - s0, zz1 - zz0), key)


def battens(m, axis, a0, a1, c, z0, z1, key, step=.55, width=.07, proud=.03):
    """Vertical battens on a board wall's face at c (c already offset to the face)."""
    n = max(1, int((a1 - a0) / step))
    for k in range(n + 1):
        a = a0 + (a1 - a0) * k / n
        if axis == 'x':
            m.box((a, c, (z0 + z1) / 2), (width, proud, z1 - z0), key)
        else:
            m.box((c, a, (z0 + z1) / 2), (proud, width, z1 - z0), key)


def lantern(m, x, y, z, size=.34, key='arc_paper'):
    """A small hanging paper lantern: an 8-sided barrel with dark caps."""
    m.lathe((x, y, z), [(-size * .62, size * .18), (-size * .45, size * .42), (0, size * .5), (size * .45, size * .42),
                        (size * .62, size * .18)], key, 8)
    for dz in (-.62, .62):
        m.lathe((x, y, z + dz * size), [(-.03, size * .2), (.03, size * .2)], 'hs_timber_dark', 8)


def stone_lantern(m, x, y, lod):
    """A stone tōrō: base, post, glowing firebox, pyramid roof and finial (LOD2: two blocks)."""
    if lod == 2:
        m.box((x, y, .55), (.4, .4, 1.1), 'hs_stone'); m.box((x, y, 1.4), (.6, .6, .55), 'hs_stone_dark')
        return
    n = 6 if lod == 0 else 4
    m.box((x, y, .1), (.62, .62, .2), 'hs_stone_dark')
    m.lathe((x, y, 0), [(.2, .14), (.95, .12)], 'hs_stone', n)
    m.box((x, y, 1.05), (.52, .52, .14), 'hs_stone')
    m.box((x, y, 1.3), (.36, .36, .36), 'arc_paper')
    if lod == 0:
        for s in (-1, 1):
            m.box((x + s * .17, y, 1.3), (.06, .40, .38), 'hs_stone'); m.box((x, y + s * .17, 1.3), (.40, .06, .38), 'hs_stone')
    m.lathe((x, y, 1.48), [(0, .48), (.12, .40), (.28, .06)], 'hs_stone_dark', 4)
    m.lathe((x, y, 1.76), [(0, .06), (.08, .09), (.16, 0.)], 'hs_stone', 6)


def tree(m, x, y, kind, scale, lod):
    """A low-poly garden tree: a trunk and leaf blobs (maple) or tiers (pine)."""
    n = (7, 5, 4)[lod]
    h = 4.2 * scale
    m.lathe((x, y, -.1), [(0, .22 * scale), (h * .55, .14 * scale), (h * .7, .1 * scale)], 'hs_bark', n)
    rr = random.Random(int(x * 13 + y * 7))
    if kind == 'pine':
        for k, (z, r) in enumerate([(.45, 1.8), (.62, 1.45), (.78, 1.0), (.92, .55)]):
            m.lathe((x, y, h * z), [(-.35 * scale, .1), (0, r * scale), (.45 * scale, .05)], 'hs_pine', n)
        return
    blobs = [(0, 0, .8, 1.5)] + [(rr.uniform(-.9, .9), rr.uniform(-.9, .9), rr.uniform(.62, .95), rr.uniform(.9, 1.2))
                                  for _ in range((3, 1, 0)[lod])]
    for k, (dx, dy, z, r) in enumerate(blobs):
        r *= scale
        prof = [(-r * .8, r * .3), (-r * .4, r * .9), (0, r), (r * .45, r * .8), (r * .8, r * .25)]
        m.lathe((x + dx * scale, y + dy * scale, h * z), prof, 'hs_maple' if k % 2 == 0 else 'hs_maple_b', n)


# ------------------------------------------------------------------ the barn
def barn(m, lod):
    cx, cy = L.BARN_CENTRE
    X0, X1, Y0, Y1 = L.BARN_X0, L.BARN_X1, L.BARN_Y0, L.BARN_Y1
    F, E, W = L.FLOOR_Z, L.EAVE_Z, L.WALL
    dw, dh = L.AISLE_DOOR
    # plinth and floors
    m.box((cx, cy, (-.4 + F - .01) / 2), (L.BARN_LENGTH, L.BARN_WIDTH, F - .01 + .4), 'hs_stone_dark')
    for side in (-1, 1):
        m.box((cx, cy + side * (L.BARN_WIDTH / 2 + .04), .02), (L.BARN_LENGTH + .16, .12, .44), 'hs_stone')
        m.box((X0 - .04 if side < 0 else X1 + .04, cy, .02), (.12, L.BARN_WIDTH + .16, .44), 'hs_stone')
    m.poly([(X0 + W, L.AISLE_Y0, F), (X1 - W, L.AISLE_Y0, F), (X1 - W, L.AISLE_Y1, F), (X0 + W, L.AISLE_Y1, F)], 'hs_soil')
    for x0 in (X0, X1 - W):    # thresholds under the aisle doors
        m.poly([(x0, cy - dw / 2, F + .002), (x0 + W, cy - dw / 2, F + .002), (x0 + W, cy + dw / 2, F + .002),
                (x0, cy + dw / 2, F + .002)], 'hs_soil')
    for s in L.stalls():
        x0, y0, x1, y1, z = s['box']
        m.poly([(x0, y0, z + .004), (x1, y0, z + .004), (x1, y1, z + .004), (x0, y1, z + .004)], 'hs_straw')
    for r in L.rooms().values():
        x0, y0, x1, y1, z = r['box']
        m.poly([(x0, y0, z + .004), (x1, y0, z + .004), (x1, y1, z + .004), (x0, y1, z + .004)], 'hs_floor')
        if lod == 0:
            for k in range(1, int((y1 - y0) / .3)):
                yy = y0 + k * .3; m.box(((x0 + x1) / 2, yy, z + .006), (x1 - x0, .012, .004), 'hs_timber_dark')

    # outer walls: charred boards below BOARD_Z, plaster above; windows in the plaster
    win_w, wz0, wz1 = 1.1, 2.05, 2.85
    windows = {1: [], -1: []}
    for k in range(0, L.STALLS_PER_SIDE + 1):
        a, b = L.bay_x(k)
        windows[1].append(((a + b) / 2, win_w, wz0, wz1))
        windows[-1].append(((a + b) / 2, 1.4 if k == 0 else win_w, 1.65 if k == 0 else wz0, wz1))   # the office's
    for side in (-1, 1):
        y = cy + side * (L.BARN_WIDTH / 2 - W / 2)
        holes = [(x - w / 2, x + w / 2, z0, z1) for x, w, z0, z1 in windows[side]] if lod < 2 else []
        wall(m, 'x', X0, X1, y, W, F, L.BOARD_Z, [], 'hs_char')
        wall(m, 'x', X0, X1, y, W, L.BOARD_Z, E, holes, 'hs_plaster')
        face = cy + side * (L.BARN_WIDTH / 2 + .015)
        if lod == 0:
            battens(m, 'x', X0 + .1, X1 - .1, face, F, L.BOARD_Z, 'hs_char_light')
        for x, w, z0, z1 in (windows[side] if lod < 2 else []):
            window(m, 'x', x, cy + side * L.BARN_WIDTH / 2, side, w, z0, z1, lod)
    for xw, out in ((X0 + W / 2, -1), (X1 - W / 2, 1)):
        holes = [(cy - dw / 2, cy + dw / 2, F, F + dh)]
        wall(m, 'y', Y0 + W, Y1 - W, xw, W, F, L.BOARD_Z, holes, 'hs_char')
        wall(m, 'y', Y0 + W, Y1 - W, xw, W, L.BOARD_Z, E, holes, 'hs_plaster')
        if lod == 0:
            face = xw + out * (W / 2 + .015)
            for a0, a1 in spans(Y0 + .1, Y1 - .1, [(cy - dw / 2 - .1, cy + dw / 2 + .1)]):
                battens(m, 'y', a0, a1, face, F, L.BOARD_Z, 'hs_char_light')
        gable_wall(m, xw, out, lod)
        aisle_door(m, xw + out * W / 2, out, lod)
    # timber frame on the outside: posts at the corners and bay lines, a rail at BOARD_Z and the wall plate
    if lod <= 1:
        posts = [X0, X1] + [L.bay_x(k)[1] + L.PART / 2 for k in range(0, L.STALLS_PER_SIDE)]
        for side in (-1, 1):
            y = cy + side * (L.BARN_WIDTH / 2 + .05)
            for x in posts:
                m.box((x, y, (F + E) / 2), (.22, .14, E - F), 'hs_timber')
            m.box((cx, y, L.BOARD_Z), (L.BARN_LENGTH + .1, .16, .14), 'hs_timber')
            m.box((cx, y, E - .1), (L.BARN_LENGTH + .1, .18, .22), 'hs_timber')
        for x, out in ((X0 - .05, -1), (X1 + .05, 1)):
            for y in (Y0, Y1):
                m.box((x, y, (F + E) / 2), (.14, .22, E - F), 'hs_timber')
            for a0, a1 in spans(Y0, Y1, [(cy - dw / 2 - .25, cy + dw / 2 + .25)]):
                m.box((x, (a0 + a1) / 2, L.BOARD_Z), (.16, a1 - a0, .14), 'hs_timber')
            m.box((x, cy, E - .1), (.18, L.BARN_WIDTH + .1, .22), 'hs_timber')
    if lod == 0:
        for x in (X0 - .3, X1 + .3):
            for y in (Y0 - .3, Y1 + .3):
                kawara.downpipe(m, (x, y, E - .6), (x + (.2 if x < cx else -.2), y + (.2 if y < cy else -.2)))
    interior(m, lod)
    roof(m, lod)


def window(m, axis, x, y_face, side, w, z0, z1, lod):
    """A barred stall window through the wall at y_face (outer face), side +1 north: frame, bars and a propped shutter."""
    W = L.WALL
    yc = y_face - side * W / 2
    m.box((x, y_face + side * .03, z0 - .06), (w + .3, .1, .1), 'hs_timber')
    m.box((x, y_face + side * .03, z1 + .06), (w + .3, .1, .12), 'hs_timber')
    for s in (-1, 1):
        m.box((x + s * (w / 2 + .05), y_face + side * .03, (z0 + z1) / 2), (.1, .1, z1 - z0 + .2), 'hs_timber')
    bars = 7 if lod == 0 else 3
    for k in range(bars):
        xx = x - w / 2 + w * (k + .5) / bars
        m.box((xx, yc, (z0 + z1) / 2), (.05, W + .04, z1 - z0), 'hs_timber_dark')
    if lod == 0:   # top-hinged board shutter held open on two sticks
        hy, hz = y_face + side * .06, z1 + .14
        a = math.radians(55)
        ty, tz = hy + side * math.sin(a) * .95, hz - math.cos(a) * .95
        half = (w + .2) / 2
        q = [(x - half, hy, hz), (x + half, hy, hz), (x + half, ty, tz), (x - half, ty, tz)]
        kawara.face(m, q, 'hs_char_light', (0, side, 1)); kawara.face(m, q, 'hs_char', (0, -side, -1))
        for s in (-1, 1):
            m.beam((x + s * w * .4, y_face + side * .05, z0 - .05), (x + s * w * .4, ty, tz), .03, .03, 'hs_timber_dark')


def gable_wall(m, xw, out, lod):
    """The plaster triangle over an end wall, a tie beam, a king post with struts and a louvred vent."""
    cy = L.BARN_CENTRE[1]; E, Rz = L.EAVE_Z, L.RIDGE_Z
    hw = L.BARN_WIDTH / 2
    for s, x in ((out, xw + out * L.WALL / 2), (-out, xw - out * L.WALL / 2)):
        pts = [(x, cy - hw, E), (x, cy + hw, E), (x, cy, Rz)]
        m.poly(pts if s > 0 else pts[::-1], 'hs_plaster')
    if lod > 1:
        return
    x = xw + out * (L.WALL / 2 + .06)
    m.box((x, cy, E + .05), (.14, L.BARN_WIDTH + .1, .24), 'hs_timber')
    m.box((x, cy, (E + Rz) / 2), (.14, .2, Rz - E), 'hs_timber')
    for s in (-1, 1):
        m.beam((x, cy + s * hw, E + .1), (x, cy, Rz - .05), .14, .16, 'hs_timber')
        m.beam((x, cy + s * hw * .55, E + .1), (x, cy + s * .1, E + (Rz - E) * .55), .1, .12, 'hs_timber')
    if lod == 0:
        m.box((x, cy - .9, E + .95), (.06, .7, .55), 'hs_timber_dark')
        m.box((x, cy + .9, E + .95), (.06, .7, .55), 'hs_timber_dark')
        for k in range(4):
            for yy in (cy - .9, cy + .9):
                m.box((x + out * .03, yy, E + .75 + k * .13), (.04, .74, .05), 'hs_timber')


def aisle_door(m, xface, out, lod):
    """The aisle doorway: a frame, two board leaves slid open along the outside wall on their rail, a lantern and a
    small tiled pent roof (hisashi)."""
    cy = L.BARN_CENTRE[1]; F = L.FLOOR_Z
    dw, dh = L.AISLE_DOOR
    x = xface + out * .04
    for s in (-1, 1):
        m.box((x, cy + s * (dw / 2 + .08), F + dh / 2), (.16, .16, dh), 'hs_timber')
    m.box((x, cy, F + dh + .1), (.18, dw + .5, .2), 'hs_timber')
    leaf = dw / 2 + .1
    for s in (-1, 1):                          # leaves slid open, each beside the opening
        yc = cy + s * (dw / 2 + .12 + leaf / 2)
        xl = xface + out * .12
        m.box((xl, yc, F + dh / 2 + .02), (.07, leaf, dh), 'hs_char_light')
        if lod == 0:
            battens(m, 'y', yc - leaf / 2 + .05, yc + leaf / 2 - .05, xl + out * .04, F + .05, F + dh, 'hs_timber_dark', .3, .05, .025)
            m.box((xl + out * .05, yc, F + dh * .3), (.03, leaf, .1), 'hs_timber'); m.box((xl + out * .05, yc, F + dh * .7), (.03, leaf, .1), 'hs_timber')
    m.box((xface + out * .12, cy, F + dh + .2), (.06, 2 * dw + .6, .1), 'hs_iron')
    if lod == 0:
        lantern(m, xface + out * .45, cy + dw / 2 + .55, F + dh - .2)
        with m.at((xface, cy, 0), -90 if out < 0 else 90):
            kawara.pent(m, -dw / 2 - .7, dw / 2 + .7, 0, L.EAVE_Z - .1, 1.05, .32)
    elif lod == 1:
        with m.at((xface, cy, 0), -90 if out < 0 else 90):
            z = L.EAVE_Z - .1
            m.poly([(-dw / 2 - .7, -1.05, z - .32), (dw / 2 + .7, -1.05, z - .32), (dw / 2 + .7, 0, z), (-dw / 2 - .7, 0, z)], 'kw_roof_tile')
            m.poly([(-dw / 2 - .7, 0, z - .06), (dw / 2 + .7, 0, z - .06), (dw / 2 + .7, -1.05, z - .38), (-dw / 2 - .7, -1.05, z - .38)], 'wood_dark')


def interior(m, lod):
    if lod == 2:
        return
    cy = L.BARN_CENTRE[1]; F = L.FLOOR_Z
    stalls = L.stalls()
    rx0, rx1 = L.bay_x(0)
    for side in (-1, 1):
        y = cy + side * (L.AISLE / 2 + L.PART / 2)
        mine = [s for s in stalls if s['side'] == side]
        doors = [(s['door']['pivot'][0] - L.STALL_DOOR[0] / 2, s['door']['pivot'][0] + L.STALL_DOOR[0] / 2) for s in mine]
        x0, x1 = rx1 + L.PART, L.BARN_X1 - L.WALL
        # stall fronts: solid boards to 1.3 m, bars above; the door openings to their full height with a header
        holes = [(a, b, F, F + L.STALL_DOOR[1]) for a, b in doors]
        wall(m, 'x', x0, x1, y, L.PART, F, F + 1.3, holes, 'hs_timber_light')
        for a, b in spans(x0, x1, doors):
            m.box(((a + b) / 2, y, F + 1.3 + .05), (b - a, L.PART + .04, .1), 'hs_timber')
            if lod == 0:
                n = int((b - a) / .16)
                for k in range(1, n):
                    m.box((a + (b - a) * k / n, y, (F + 1.35 + L.STALL_FRONT_Z) / 2), (.035, .035, L.STALL_FRONT_Z - F - 1.35), 'hs_iron')
        for a, b in doors:
            m.box(((a + b) / 2, y, (F + L.STALL_DOOR[1] + L.STALL_FRONT_Z) / 2), (b - a, L.PART, L.STALL_FRONT_Z - F - L.STALL_DOOR[1]), 'hs_timber')
            m.box(((a + b) / 2, y - side * (L.PART / 2 + .05), F + L.STALL_DOOR[1] + .06), (b - a + .5, .05, .06), 'hs_iron')   # door rail
        m.box(((x0 + x1) / 2, y, L.STALL_FRONT_Z), (x1 - x0, L.PART + .06, .12), 'hs_timber')
        # partitions between stalls
        yo0, yo1 = sorted((cy + side * (L.AISLE / 2 + L.PART), cy + side * (L.BARN_WIDTH / 2 - L.WALL)))
        for k in range(1, L.STALLS_PER_SIDE):
            xp = L.bay_x(k)[1] + L.PART / 2
            m.box((xp, (yo0 + yo1) / 2, (F + L.STALL_FRONT_Z) / 2), (L.PART, yo1 - yo0, L.STALL_FRONT_Z - F), 'hs_timber_light')
            m.box((xp, (yo0 + yo1) / 2, L.STALL_FRONT_Z), (L.PART + .06, yo1 - yo0, .12), 'hs_timber')
        for s in mine:
            plaque(m, s['plaque'], lod)
            if lod == 0:
                sx0, sy0, sx1, sy1, z = s['box']
                back = sy1 if side > 0 else sy0
                m.box((sx1 - .45, back - side * .3, z + 1.45), (.7, .5, .5), 'hs_timber')        # hay rack
                m.box((sx1 - .45, back - side * .3, z + 1.62), (.62, .42, .2), 'hs_hay')
                m.lathe((sx0 + .4, back - side * .3, z), [(0, .17), (.32, .2), (.33, .2)], 'hs_iron', 8)   # bucket
        # the rooms' fronts, their ceiling and the wall between the rooms and the first stall
        room = L.rooms()['tack' if side > 0 else 'office']
        dx = room['door']['pivot'][0]
        wall(m, 'x', rx0, rx1 + L.PART, y, L.PART, F, L.ROOM_CEIL, [(dx - L.ROOM_DOOR[0] / 2, dx + L.ROOM_DOOR[0] / 2, F, F + L.ROOM_DOOR[1])], 'hs_plaster')
        for xx in (dx - L.ROOM_DOOR[0] / 2 - .05, dx + L.ROOM_DOOR[0] / 2 + .05):
            m.box((xx, y - side * .08, F + L.ROOM_DOOR[1] / 2), (.1, .06, L.ROOM_DOOR[1]), 'hs_timber')
        m.box((dx, y - side * .08, F + L.ROOM_DOOR[1] + .05), (L.ROOM_DOOR[0] + .2, .06, .1), 'hs_timber')
        m.box((rx1 + L.PART / 2, (yo0 + yo1) / 2, (F + L.ROOM_CEIL) / 2), (L.PART, yo1 - yo0, L.ROOM_CEIL - F), 'hs_plaster')
        m.box(((rx0 + rx1 + L.PART) / 2, (yo0 + yo1 - side * L.PART) / 2, L.ROOM_CEIL + .06),
              (rx1 - rx0 + L.PART, yo1 - yo0 + L.PART, .12), 'hs_timber')
    # trusses at every bay line: tie beam, king post, principal rafters
    hw = L.BARN_WIDTH / 2 - L.WALL
    for k in range(0, L.STALLS_PER_SIDE):
        x = L.bay_x(k)[1] + L.PART / 2
        m.box((x, cy, L.EAVE_Z - .15), (.18, 2 * hw, .26), 'hs_timber')
        if lod == 0:
            m.box((x, cy, (L.EAVE_Z + L.RIDGE_Z) / 2 - .1), (.16, .16, L.RIDGE_Z - L.EAVE_Z - .2), 'hs_timber')
            for s in (-1, 1):
                m.beam((x, cy + s * hw, L.EAVE_Z), (x, cy, L.RIDGE_Z - .25), .16, .18, 'hs_timber')
                m.beam((x, cy + s * .1, L.EAVE_Z + .3), (x, cy + s * hw * .5, L.EAVE_Z + (L.RIDGE_Z - L.EAVE_Z) * .45), .1, .12, 'hs_timber')
            lantern(m, x, cy, L.EAVE_Z - .75)
            m.beam((x, cy, L.EAVE_Z - .55), (x, cy, L.EAVE_Z - .28), .02, .02, 'hs_iron')
    m.box((L.BARN_CENTRE[0], cy, L.RIDGE_Z - .3), (L.BARN_LENGTH - .5, .2, .24), 'hs_timber')    # ridge beam
    if lod == 0:
        rooms_props(m)
        hay = [(L.BARN_X0 + .9, L.BARN_Y1 - 1.2), (L.BARN_X0 + 2.1, L.BARN_Y1 - 1.2)]
        for k, (x, y) in enumerate(hay):     # bales stored on the loft over the tack room
            m.box((x, y, L.ROOM_CEIL + .12 + .23), (1.0, .5, .45), 'hs_hay', .03)


def plaque(m, p, lod):
    """A stall's name plate: a dark frame and a blank cream plate, proud of the aisle face."""
    (x, y, z), (nx, ny, _), (w, h) = p['centre'], p['normal'], p['size']
    m.box((x, y - ny * .01, z), (w + .1, .03, h + .1), 'hs_timber_dark')
    m.box((x, y + ny * .012, z), (w, .02, h), 'hs_plate')
    if lod == 0:
        m.box((x, y + ny * .03, z + h / 2 + .09), (w + .18, .08, .04), 'hs_timber')   # a little drip cap


def rooms_props(m):
    F = L.FLOOR_Z
    # tack room: saddle racks and bridle hooks on the north wall, a chest
    x0, y0, x1, y1, z = L.rooms()['tack']['box']
    for k in range(3):
        x = x0 + .7 + k * 1.15
        m.box((x, y1 - .3, F + 1.25), (.12, .6, .1), 'hs_timber')
        m.box((x, y1 - .32, F + 1.38), (.5, .62, .2), 'hs_leather', .06)
        m.box((x, y1 - .32, F + 1.3), (.56, .58, .06), 'hs_pad')
        m.box((x, y1 - .05, F + 1.95), (.06, .1, .06), 'hs_iron')
        m.box((x, y1 - .08, F + 1.7), (.05, .03, .5), 'hs_leather')
    m.box((x0 + .5, (y0 + y1) / 2, F + .3), (.6, 1.2, .6), 'hs_timber', .03)
    m.box((x1 - .25, y1 - 1.0, F + 1.2), (.35, 1.4, .06), 'hs_timber')
    for k in range(3):
        m.lathe((x1 - .25, y1 - 1.5 + k * .45, F + 1.23), [(0, .12), (.25, .15)], 'hs_iron', 8)
    # office: desk and stools, a bench, a shelf of trophies and the transfers board
    x0, y0, x1, y1, z = L.rooms()['office']['box']
    dx, dy = (x0 + x1) / 2 - .3, y0 + .55
    m.box((dx, dy, F + .74), (1.5, .7, .06), 'hs_timber_light')
    for sx in (-1, 1):
        for sy in (-1, 1):
            m.box((dx + sx * .68, dy + sy * .28, F + .36), (.06, .06, .72), 'hs_timber')
    m.box((dx, dy + .1, F + .79), (.4, .3, .02), 'hs_card')
    for x in (dx - .4, dx + .4):
        m.lathe((x, dy + .7, F), [(0, .17), (.44, .17), (.46, .18)], 'hs_timber', 8)
    m.box((x0 + .3, (y0 + y1) / 2 + .5, F + .23), (.4, 1.6, .06), 'hs_timber_light')
    m.box((x0 + .12, (y0 + y1) / 2 + .5, F + 1.6), (.24, 1.6, .05), 'hs_timber')
    for k in range(3):
        y = (y0 + y1) / 2 - .1 + k * .55
        m.lathe((x0 + .14, y, F + 1.63), [(0, .07), (.06, .05), (.14, .03), (.22, .1), (.28, .02)], 'hs_gold', 8)
    nb = L.notice_board()
    (bx, by, bz), (bw, bh) = nb['centre'], nb['size']
    m.box((bx + .01, by, bz), (.04, bw + .12, bh + .12), 'hs_timber')
    m.box((bx - .02, by, bz), (.03, bw, bh), 'hs_cork')
    cards = random.Random(5)
    for k in range(7):
        cyy = by - bw / 2 + .2 + (k % 4) * .4 + cards.uniform(-.04, .04)
        czz = bz + .22 - (k // 4) * .45 + cards.uniform(-.04, .04)
        m.box((bx - .04, cyy, czz), (.01, .26, .32), 'hs_card')
        m.box((bx - .05, cyy, czz + .13), (.02, .03, .03), 'hs_pin')
    lantern(m, (x0 + x1) / 2, (y0 + y1) / 2, L.ROOM_CEIL - .4, .26)
    lantern(m, (x0 + x1) / 2, (L.rooms()['tack']['box'][1] + L.rooms()['tack']['box'][3]) / 2, L.ROOM_CEIL - .4, .26)


def roof(m, lod):
    cx, cy = L.BARN_CENTRE
    ov = L.EAVE_OVERHANG; t = math.tan(math.radians(L.ROOF_PITCH))
    hw = L.BARN_WIDTH / 2
    edge_z = L.EAVE_Z - ov * t
    rise = (hw + ov) * t
    vent = L.VENT
    vlen = L.BARN_LENGTH - 2 * vent['inset']
    if lod == 0:
        with m.at((cx, cy, 0)):
            kawara.gable(m, L.BARN_LENGTH, L.BARN_WIDTH, edge_z, rise, ov)
            # inside: the boarded underside of the slopes between the walls and the ridge
            for s in (-1, 1):
                pts = [(-L.BARN_LENGTH / 2, s * (hw - L.WALL), L.EAVE_Z - .02 + L.WALL * t), (L.BARN_LENGTH / 2, s * (hw - L.WALL), L.EAVE_Z - .02 + L.WALL * t),
                       (L.BARN_LENGTH / 2, 0, L.RIDGE_Z - .04), (-L.BARN_LENGTH / 2, 0, L.RIDGE_Z - .04)]
                kawara.face(m, pts, 'wood_dark', (0, -s * .3, -1))
                for k in range(int(L.BARN_LENGTH / .9) + 1):
                    x = -L.BARN_LENGTH / 2 + .2 + k * (L.BARN_LENGTH - .4) / int(L.BARN_LENGTH / .9)
                    m.beam((x, s * (hw - L.WALL), L.EAVE_Z - .1 + L.WALL * t), (x, s * .1, L.RIDGE_Z - .12), .08, .1, 'hs_timber_dark')
            # a boarded ceiling under the ridge: the vent ventilates the loft, it is not a skylight from the aisle
            cw = vent['width'] + .8
            m.box((0, 0, L.RIDGE_Z - cw / 2 * t - .06), (L.BARN_LENGTH - 2 * L.WALL, cw, .04), 'wood_dark')
            # the raised ridge vent (koshi-yane): louvred side walls and its own small tiled gable
            vz0, vz1 = L.RIDGE_Z - vent['width'] / 2 * t - .05, L.RIDGE_Z + vent['height']
            for s in (-1, 1):
                y = s * vent['width'] / 2
                m.box((0, y, (vz0 + vz1) / 2), (vlen, .1, vz1 - vz0), 'hs_timber_dark')
                for k in range(4):
                    m.box((0, y + s * .06, L.RIDGE_Z + .15 + k * .22), (vlen, .05, .07), 'hs_timber')
                for x in np.linspace(-vlen / 2, vlen / 2, 9):
                    m.box((float(x), y + s * .07, (vz0 + vz1) / 2), (.1, .06, vz1 - vz0), 'hs_timber')
            vt = math.tan(math.radians(30)); vov = .45
            for s in (-1, 1):
                pts = [(s * vlen / 2, -vent['width'] / 2, vz1), (s * vlen / 2, vent['width'] / 2, vz1), (s * vlen / 2, 0, vz1 + vent['width'] / 2 * vt)]
                m.poly(pts if s > 0 else pts[::-1], 'hs_plaster')
                m.box((s * vlen / 2, 0, (vz0 + vz1) / 2), (.1, vent['width'], vz1 - vz0), 'hs_timber_dark')
            kawara.gable(m, vlen, vent['width'], vz1 - vov * vt, (vent['width'] / 2 + vov) * vt, vov, gutters=False, courses=2)
        return
    # LOD1/LOD2: plain tiled planes with their thickness, the ridge and the vent as simple blocks
    key = 'kw_roof_tile'
    W_ = L.BARN_LENGTH + 2 * ov
    for s in (-1, 1):
        a = (cx - W_ / 2, cy + s * (hw + ov), edge_z); b = (cx + W_ / 2, cy + s * (hw + ov), edge_z)
        c = (cx + W_ / 2, cy, L.RIDGE_Z + .1); d = (cx - W_ / 2, cy, L.RIDGE_Z + .1)
        kawara.face(m, [a, b, c, d], key, (0, s, 1))
        kawara.face(m, [(a[0], a[1], a[2] - .12), (b[0], b[1], b[2] - .12), (c[0], c[1], c[2] - .12), (d[0], d[1], d[2] - .12)], 'wood_dark', (0, -s * .3, -1))
        kawara.face(m, [a, b, (b[0], b[1], b[2] - .12), (a[0], a[1], a[2] - .12)], 'kw_roof_ridge', (0, s, 0))
        for x in (cx - W_ / 2, cx + W_ / 2):
            kawara.face(m, [(x, a[1], a[2]), (x, cy, L.RIDGE_Z + .1), (x, cy, L.RIDGE_Z - .02), (x, a[1], a[2] - .12)], 'kw_roof_ridge', (x - cx, 0, 0))
    m.box((cx, cy, L.RIDGE_Z + .2), (W_, .4, .3), 'kw_roof_ridge')
    vz1 = L.RIDGE_Z + vent['height']
    m.box((cx, cy, (L.RIDGE_Z + vz1) / 2), (vlen, vent['width'], vz1 - L.RIDGE_Z), 'hs_timber_dark')
    for s in (-1, 1):
        kawara.face(m, [(cx - vlen / 2 - .4, cy + s * (vent['width'] / 2 + .45), vz1), (cx + vlen / 2 + .4, cy + s * (vent['width'] / 2 + .45), vz1),
                        (cx + vlen / 2 + .4, cy, vz1 + .7), (cx - vlen / 2 - .4, cy, vz1 + .7)], key, (0, s, 1))
        pts = [(cx + s * (vlen / 2 + .4), cy - vent['width'] / 2 - .45, vz1), (cx + s * (vlen / 2 + .4), cy + vent['width'] / 2 + .45, vz1),
               (cx + s * (vlen / 2 + .4), cy, vz1 + .7)]
        kawara.face(m, pts, 'kw_roof_ridge', (s, 0, 0))
    if lod == 1:
        for s in (-1, 1):
            kawara.face(m, [(cx - W_ / 2, cy + s * (hw + ov), edge_z - .12), (cx + W_ / 2, cy + s * (hw + ov), edge_z - .12),
                            (cx + W_ / 2, cy + s * hw, L.EAVE_Z - .12), (cx - W_ / 2, cy + s * hw, L.EAVE_Z - .12)], 'wood_dark', (0, 0, -1))


# ------------------------------------------------------------------ gate, yard, paddock
def gate(m, lod):
    gx, gy = L.GATE['at']; o = L.GATE['opening'] / 2; p = L.GATE['post']; h = L.GATE['height']
    for s in (-1, 1):
        y = gy + s * (o + p / 2)
        m.box((gx, y, .1), (p + .2, p + .2, .2), 'hs_stone')
        m.box((gx, y, h / 2), (p, p, h), 'hs_timber')
        if lod <= 1:
            m.box((gx + .55, y, 1.0), (.16, .16, 2.0), 'hs_timber')               # back strut posts
            m.beam((gx, y, 1.9), (gx + .55, y, 1.6), .1, .12, 'hs_timber')
    m.box((gx, gy, h - .25), (.24, 2 * (o + p) + .6, .28), 'hs_timber')            # tie beam
    m.box((gx, gy, h + .08), (.3, 2 * (o + p) + 1.2, .22), 'hs_timber_dark')       # kasagi
    if lod == 0:
        with m.at((gx, gy, 0), 90):
            kawara.gable(m, 2 * (o + p) + .9, .9, h + .22, .55, .45, gutters=False, courses=2)
    else:
        for s in (-1, 1):
            kawara.face(m, [(gx + s * .95, gy - o - p - .9, h + .22), (gx + s * .95, gy + o + p + .9, h + .22),
                            (gx, gy + o + p + .9, h + .8), (gx, gy - o - p - .9, h + .8)], 'kw_roof_tile', (s, 0, 1))
            kawara.face(m, [(gx, gy + s * (o + p + .9), h + .8), (gx + .95, gy + s * (o + p + .9), h + .22), (gx - .95, gy + s * (o + p + .9), h + .22)],
                        'kw_roof_ridge', (0, s, 0))
    # the name plate, hung under the tie beam on the outside (west) face
    (sx, sy, sz), (sw, sh) = L.SIGN['centre'], L.SIGN['size']
    m.box((sx + .04, sy, sz), (.08, sw + .14, sh + .14), 'hs_timber')
    m.box((sx - .01, sy, sz), (.04, sw, sh), 'hs_sign')
    if lod <= 1:
        for s in (-1, 1):
            m.beam((sx + .04, sy + s * (sw / 2 - .15), sz + sh / 2), (gx, sy + s * (sw / 2 - .15), h - .4), .03, .03, 'hs_iron')
        with m.at((sx - .035, sy, sz), -90):
            raised_text(m, L.NAME, (0, 0, -L.SIGN['text'] * .25), L.SIGN['text'], 'hs_letter', .006, .015)
    # bamboo fences either side of the gate
    for s in ((-1, 1) if lod == 2 else ()):
        m.box((gx, gy + s * (o + p + L.fence_run(s) / 2), .62), (.12, L.fence_run(s), 1.25), 'hs_bamboo')
    for s in ((-1, 1) if lod < 2 else ()):
        run = L.fence_run(s)
        y0 = gy + s * (o + p); y1 = gy + s * (o + p + run)
        n = int(run / 1.75)
        for k in range(n + 1):
            y = y0 + (y1 - y0) * k / n
            m.box((gx, y, .62), (.11, .11, 1.25), 'hs_timber')
        for z in (.35, .75, 1.12):
            m.box((gx + .07, (y0 + y1) / 2, z), (.05, abs(y1 - y0), .05), 'hs_bamboo')
        if lod == 0:
            for k in range(int(run / .3)):
                y = min(y0, y1) + .15 + k * .3
                m.box((gx - .07, y, .6), (.045, .045, 1.15), 'hs_bamboo')
    for x, y in L.LANTERNS:
        stone_lantern(m, x, y, lod)


def yard(m, lod):
    tx, ty = L.TROUGH['at']; tw, td, th = L.TROUGH['size']
    m.box((tx, ty, .08), (tw, td, .16), 'hs_stone_dark')
    for s in (-1, 1):
        m.box((tx, ty + s * (td / 2 - .07), th / 2), (tw, .14, th), 'hs_stone', .02 if lod == 0 else 0)
        m.box((tx + s * (tw / 2 - .07), ty, th / 2), (.14, td - .28, th), 'hs_stone', .02 if lod == 0 else 0)
    m.box((tx, ty, th * .6), (tw - .28, td - .28, th * 1.2 - .25), 'hs_stone_dark')
    m.poly([(tx - tw / 2 + .14, ty - td / 2 + .14, th - .1), (tx + tw / 2 - .14, ty - td / 2 + .14, th - .1),
            (tx + tw / 2 - .14, ty + td / 2 - .14, th - .1), (tx - tw / 2 + .14, ty + td / 2 - .14, th - .1)], 'hs_water')
    if lod <= 1:    # a bamboo spout (kakehi) on a post behind the trough
        m.box((tx + tw / 2 - .3, ty + td / 2 + .25, .65), (.14, .14, 1.3), 'hs_timber')
        m.beam((tx + tw / 2 - .3, ty + td / 2 + .25, 1.2), (tx + .4, ty, th + .35), .09, .09, 'hs_bamboo')
    hx, hy = L.HITCH['at']; hl, hh = L.HITCH['length'], L.HITCH['height']
    for s in (-1, 1):
        m.box((hx + s * hl / 2, hy, (hh + .1) / 2), (.18, .18, hh + .1), 'hs_timber')
    m.box((hx, hy, hh), (hl + .3, .14, .12), 'hs_timber_light')
    if lod == 0:
        for k in (-1, 0, 1):
            m.lathe((hx + k * 1.3, hy - .09, hh - .16), [(-.06, .02), (0, .07), (.06, .02)], 'hs_iron', 6)
        m.beam((hx + 1.3, hy - .1, hh - .2), (hx + 1.5, hy - .3, .6), .03, .03, 'hs_rope')
        for k, (x, y, z) in enumerate([(L.BARN_X0 - 1.4, L.BARN_Y1 - .8, .23), (L.BARN_X0 - 1.4, L.BARN_Y1 - 1.35, .23),
                                       (L.BARN_X0 - 1.4, L.BARN_Y1 - 1.07, .68), (L.BARN_X0 - 2.45, L.BARN_Y1 - 1.0, .23)]):
            m.box((x, y, z), (1.0, .5, .45), 'hs_hay', .03)
        for x, y in ((L.BARN_X0 - 1.0, L.BARN_Y0 + 1.2), (tx - tw / 2 - .5, ty - .1)):
            m.lathe((x, y, 0), [(0, .17), (.32, .2), (.33, .2)], 'hs_timber_light', 8)
    for x, y, kind, sc in L.TREES:
        tree(m, x, y, kind, sc, lod)
    dressing(m, lod)


def dressing(m, lod):
    """The yard's life: hay shed, handcart, barrels, planted tubs, tea bench and parasol, shrubs, rocks, fire buckets
    and the low fence round it."""
    hay_shed(m, lod); cart(m, lod)
    for x, y in L.BARRELS:
        barrel(m, x, y, lod)
    for k, (x, y) in enumerate(L.TUBS):
        tub(m, x, y, lod, flowers=k % 2 == 1)
    bench(m, lod)
    for k, (x, y, r) in enumerate(L.SHRUBS):
        shrub(m, x, y, r, lod, 'hs_azalea' if k % 4 == 2 else None)
    for x, y, r in L.ROCKS:
        m.lathe((x, y, -.1), [(0, r), (r * .5, r * .9), (r * .9, r * .45), (r * 1.05, 0.)], 'hs_rock', 5 if lod < 2 else 4)
    if lod <= 1:
        fx, fy = L.FIRE_BUCKETS
        m.box((fx, fy, .2), (.9, .45, .4), 'hs_timber')
        for row, count in enumerate((3, 2, 1)):
            for k in range(count):
                x = fx + (k - (count - 1) / 2) * .29
                m.lathe((x, fy, .4 + row * .25), [(0, .1), (.24, .13)], 'hs_red', 8 if lod == 0 else 6)
    f = L.YARD_FENCE; gx = L.GATE['at'][0]
    for y, x1 in ((f['y1'], f['x_north']), (f['y0'], f['x_south'])):
        if lod == 2:
            m.box(((gx + x1) / 2, y, f['height'] / 2), (x1 - gx, .08, f['height']), 'hs_timber')
            continue
        n = int((x1 - gx) / 1.8)
        for k in range(n + 1):
            m.box((gx + (x1 - gx) * k / n, y, f['height'] / 2), (.1, .1, f['height']), 'hs_timber')
        for z in (.35, f['height'] - .1):
            m.box(((gx + x1) / 2, y + .06, z), (x1 - gx, .05, .07), 'hs_bamboo')
        if lod == 0:
            for k in range(int((x1 - gx) / .3)):
                m.box((gx + .15 + k * .3, y - .05, f['height'] * .45), (.04, .04, f['height'] * .9 - .05), 'hs_bamboo')


def hay_shed(m, lod):
    """An open hay shed (naya): posts, a charred-board back and half sides, a tiled gable and stacked bales."""
    (sx, sy), (sw, sd), e = L.HAY_SHED['at'], L.HAY_SHED['size'], L.HAY_SHED['eave']
    t = math.tan(math.radians(28)); ov = .5
    for x in (sx - sw / 2, sx, sx + sw / 2):
        for y in (sy - sd / 2, sy + sd / 2):
            m.box((x, y, e / 2), (.18, .18, e), 'hs_timber')
        m.box((x, sy - sd / 2 + .02, .06), (.3, .3, .12), 'hs_stone')
    m.box((sx, sy + sd / 2 - .06, e / 2), (sw, .1, e), 'hs_char')
    for s in (-1, 1):
        m.box((sx + s * sw / 2, sy, .65), (.1, sd, 1.3), 'hs_char')
    m.box((sx, sy - sd / 2, e - .1), (sw + .2, .18, .2), 'hs_timber')
    m.box((sx, sy + sd / 2, e - .1), (sw + .2, .18, .2), 'hs_timber')
    if lod == 0:
        with m.at((sx, sy, 0)):
            kawara.gable(m, sw, sd, e - ov * t, (sd / 2 + ov) * t, ov, gutters=False, courses=2)
            for s in (-1, 1):
                pts = [(s * sw / 2, -sd / 2, e), (s * sw / 2, sd / 2, e), (s * sw / 2, 0, e + sd / 2 * t)]
                kawara.face(m, pts, 'hs_char', (s, 0, 0))
        for layer in range(3):
            for row in range(2):
                for k in range(6 - layer):
                    m.box((sx - sw / 2 + .75 + k * 1.05 + layer * .5, sy + .45 + row * .62, .23 + layer * .45), (1.0, .55, .44),
                          v.color_variant('hs_hay', .06), .03)
        m.beam((sx + sw / 2 - .4, sy - sd / 2 + .3, 0.), (sx + sw / 2 - .25, sy - sd / 2 + .5, 1.7), .04, .04, 'hs_timber_light')
        m.box((sx + sw / 2 - .25, sy - sd / 2 + .5, 1.72), (.35, .05, .08), 'hs_iron')
    else:
        W_, D_ = sw + 2 * ov, sd + 2 * ov
        for s in (-1, 1):
            kawara.face(m, [(sx - W_ / 2, sy + s * D_ / 2, e - ov * t), (sx + W_ / 2, sy + s * D_ / 2, e - ov * t),
                            (sx + W_ / 2, sy, e + sd / 2 * t), (sx - W_ / 2, sy, e + sd / 2 * t)], 'kw_roof_tile', (0, s, 1))
            kawara.face(m, [(sx + s * W_ / 2, sy - D_ / 2, e - ov * t), (sx + s * W_ / 2, sy + D_ / 2, e - ov * t),
                            (sx + s * W_ / 2, sy, e + sd / 2 * t)], 'hs_char', (s, 0, 0))
        m.box((sx, sy + .75, .7), (sw - .4, 1.3, 1.4), 'hs_hay')


def cart(m, lod):
    """A two-wheeled wooden handcart (niguruma) resting on its shafts, loaded with bales and a barrel."""
    (cx, cy), (cw, cl) = L.CART['at'], L.CART['size']
    with m.at((cx, cy, 0), L.CART['yaw']):
        z = .78
        if lod == 2:
            m.box((0, 0, z), (cl, cw, .3), 'hs_timber_light'); m.box((0, 0, z + .4), (1.2, .8, .5), 'hs_hay')
            return
        m.box((0, 0, z), (cl, cw, .07), 'hs_timber_light')
        for s in (-1, 1):
            m.box((0, s * (cw / 2 - .03), z + .12), (cl, .06, .18), 'hs_timber')
            m.beam((cl / 2 - .1, s * (cw / 2 - .1), z - .04), (cl / 2 + 1.5, s * (cw / 2 - .25), .42), .07, .08, 'hs_timber')
            m.box((cl / 2 + 1.55, s * (cw / 2 - .25), .2), (.08, .08, .42), 'hs_timber_dark')       # the shafts' rest
            # a wheel in the x-z plane at the axle
            y = s * (cw / 2 + .1); r = .6; n = 12 if lod == 0 else 8
            pts = [(r * math.cos(2 * math.pi * k / n), y, r + r * math.sin(2 * math.pi * k / n) - .02) for k in range(n)]
            for a, b in zip(pts, pts[1:] + pts[:1]):
                m.beam(a, b, .09, .07, 'hs_timber_dark')
            if lod == 0:
                for k in range(0, n, 2):
                    m.beam((0, y, r - .02), pts[k], .04, .04, 'hs_timber')
            m.box((0, y, r - .02), (.16, .14, .16), 'hs_iron')
        m.beam((cl / 2 + 1.5, -(cw / 2 - .25), .45), (cl / 2 + 1.5, cw / 2 - .25, .45), .07, .07, 'hs_timber')
        m.box((0, 0, .58), (.1, cw + .2, .1), 'hs_iron')                                      # axle
        for x in (-.55, .5):
            m.box((x, 0, z + .3), (.95, .52, .44), 'hs_hay', .03 if lod == 0 else 0)
        m.box((-.05, 0, z + .74), (.95, .52, .44), 'hs_hay', .03 if lod == 0 else 0)
        barrel(m, .7, .25, lod, z0=z + .04, scale=.7)


def barrel(m, x, y, lod, z0=0., scale=1.):
    """A wooden barrel (taru) with dark hoops."""
    n = 10 if lod == 0 else 6
    h, r = .9 * scale, .3 * scale
    m.lathe((x, y, z0), [(0, r * .86), (h * .5, r), (h, r * .86)], 'hs_timber_light', n)
    m.poly([(x + r * .86 * math.cos(2 * math.pi * k / n), y + r * .86 * math.sin(2 * math.pi * k / n), z0 + h) for k in range(n)], 'hs_timber')
    if lod == 0:
        for zz in (.15, .85):
            m.lathe((x, y, z0 + zz * h), [(-.03, r * .92 + .012), (.03, r * .92 + .012)], 'hs_timber_dark', n)


def tub(m, x, y, lod, flowers=False):
    """A planted wooden tub: a low clipped shrub, flowering every other one."""
    n = 8 if lod == 0 else 6
    m.lathe((x, y, 0), [(0, .3), (.45, .34)], 'hs_timber_light', n)
    if lod == 0:
        m.lathe((x, y, .3), [(-.03, .35), (.03, .35)], 'hs_timber_dark', n)
    shrub(m, x, y, .42, lod, 'hs_azalea' if flowers else None, z0=.38)


def shrub(m, x, y, r, lod, bloom=None, z0=0.):
    """A clipped round shrub (tamamono), with blossoms on top when bloom is a colour key."""
    n = 7 if lod == 0 else 5
    key = 'hs_bush' if int(x * 7 + y * 3) % 2 else 'hs_bush_b'
    m.lathe((x, y, z0), [(0, r * .7), (r * .45, r), (r * .9, r * .75), (r * 1.15, 0.)], key, n)
    if bloom and lod == 0:
        m.lathe((x, y, z0 + r * .55), [(0, r * .78), (r * .3, r * .62), (r * .62, 0.)], bloom, n)


def bench(m, lod):
    """A tea-house bench (shōgi) with red felt under a red parasol (nodate-gasa)."""
    (bx, by), bl = L.BENCH['at'], L.BENCH['length']
    m.box((bx, by, .43), (bl, .6, .07), 'hs_timber_light')
    for sx in (-1, 1):
        for sy in (-1, 1):
            m.box((bx + sx * (bl / 2 - .1), by + sy * .22, .2), (.07, .07, .4), 'hs_timber')
    m.box((bx, by, .475), (bl - .2, .5, .02), 'hs_felt')
    px, py = bx, by - .55
    m.box((px, py, 1.15), (.05, .05, 2.3), 'hs_timber_dark')
    r = L.BENCH['parasol']; n = 12 if lod == 0 else 8
    m.lathe((px, py + .3, 2.15), [(0, r), (.32, r * .55), (.5, .04)], 'hs_parasol', n)
    if lod == 0:
        m.lathe((px, py + .3, 2.1), [(0, r * .98), (.05, r * .98)], 'hs_timber_dark', n)


def paddock(m, lod):
    x0, y0, x1, y1 = L.PADDOCK
    g0, g1 = L.PADDOCK_GATE['x'] - L.PADDOCK_GATE['width'] / 2, L.PADDOCK_GATE['x'] + L.PADDOCK_GATE['width'] / 2
    h = L.FENCE_HEIGHT
    runs = [('x', a, c, y1) for a, c in spans(x0, x1, [(g0, g1)])] + [('x', x0, x1, y0), ('y', y0, y1, x0), ('y', y0, y1, x1)]
    step = L.FENCE_POST_STEP * (1, 2, 4)[lod]
    for axis, a, c, at in runs:
        n = max(1, int(round((c - a) / step)))
        for k in range(n + 1):
            q = a + (c - a) * k / n
            pos = (q, at) if axis == 'x' else (at, q)
            m.box((*pos, (h + .1) / 2 - .05), (.14, .14, h + .1), 'hs_timber')
        for z in ((.55, h - .1) if lod <= 1 else (h - .1,)):
            mid = (a + c) / 2
            size = (c - a, .07, .13) if axis == 'x' else (.07, c - a, .13)
            m.box(((mid, at + .08, z) if axis == 'x' else (at + .08, mid, z)), size, 'hs_timber_light')
    for x in (g0, g1):
        m.box((x, y1, (h + .5) / 2), (.2, .2, h + .5), 'hs_timber')


# ------------------------------------------------------------------ doors
def stall_door(lod):
    m = v.Mesh(f'SM_HS_StallDoor_LOD{lod}')
    w, h, t = L.STALL_DOOR[0], L.STALL_DOOR[1], L.DOOR_LEAF
    for s in (-1, 1):
        m.box((s * (w / 2 - .05), 0, h / 2), (.1, t, h), 'hs_timber')
    m.box((0, 0, h - .05), (w, t, .1), 'hs_timber')
    m.box((0, 0, .65), (w - .2, t * .7, 1.2), 'hs_timber_light')
    m.box((0, 0, 1.3), (w, t, .12), 'hs_timber')
    if lod <= 1:
        for side in (-1, 1):
            m.beam((-w / 2 + .1, side * t * .4, .1), (w / 2 - .1, side * t * .4, 1.2), .06, .03, 'hs_timber')   # the Z brace
    bars = 8 if lod == 0 else (4 if lod == 1 else 0)
    for k in range(bars):
        m.box((-w / 2 + .1 + (w - .2) * (k + .5) / bars, 0, (1.36 + h - .1) / 2), (.035, .035, h - 1.46), 'hs_iron')
    if lod == 2:
        m.box((0, 0, (1.36 + h - .1) / 2), (w - .2, .01, h - 1.46), 'hs_timber_dark')
    if lod == 0:
        for side in (-1, 1):
            m.box((w / 2 - .25, side * (t / 2 + .02), 1.0), (.05, .04, .25), 'hs_iron')
        m.box((0, 0, h + .02), (w * .9, .03, .05), 'hs_iron')
    return m


def room_door(lod):
    m = v.Mesh(f'SM_HS_RoomDoor_LOD{lod}')
    w, h, t = L.ROOM_DOOR[0], L.ROOM_DOOR[1], L.DOOR_LEAF
    for s in (-1, 1):
        m.box((s * (w / 2 - .04), 0, h / 2), (.08, t, h), 'hs_timber')
    for z in (.04, h - .04, .9):
        m.box((0, 0, z), (w, t, .08), 'hs_timber')
    m.box((0, 0, .47), (w - .1, t * .6, .82), 'hs_timber_light')
    m.box((0, 0, (h + .9) / 2), (w - .1, t * .3, h - .98), 'hs_card')
    if lod == 0:
        for k in range(1, 4):
            m.box((-w / 2 + w * k / 4, 0, (h + .9) / 2), (.03, t * .8, h - .98), 'hs_timber')
        for k in range(1, 4):
            m.box((0, 0, .9 + (h - .98) * k / 4), (w - .1, t * .8, .03), 'hs_timber')
    return m


# ------------------------------------------------------------------ ground and road
def ground(pad_z):
    """The yard, the paddock and the inner paths as overlays on the graded ground (Hidamari's terrain, flat at PAD_Z)."""
    m = v.Mesh('SM_HS_Ground')
    x0, y0, x1, y1 = L.COMPOUND

    def rect(a, b, c, d, z, key):
        m.poly([(a, b, z), (c, b, z), (c, d, z), (a, d, z)], key)
    rect(*L.YARD, .015, 'hs_yard_earth')
    rect(*L.GARDEN, .02, 'hs_bed')
    rect(L.YARD[2], L.PADDOCK[3] + .2, L.PADDOCK_GATE['x'] + L.PADDOCK_GATE['width'] / 2 + .3, L.BARN_Y0 - .3, .016, 'hs_yard_earth')
    rect(L.BARN_X1, L.BARN_CENTRE[1] - 2., L.BARN_X1 + 4., L.BARN_CENTRE[1] + 2., .015, 'hs_yard_earth')
    px0, py0, px1, py1 = L.PADDOCK
    rect(px0 + .2, py0 + .2, px1 - .2, py1 - .2, .015, 'hs_soil')
    gy = L.GATE['at'][1]
    rect(x0, gy - L.ROAD_WIDTH / 2, L.YARD[0], gy + L.ROAD_WIDTH / 2, .02, 'hs_gravel')
    rect(L.YARD[0], gy - 1.2, L.BARN_X0, gy + 1.2, .025, 'hs_gravel')
    return m


def road(pad_z):
    """The dirt lane from the end of Hidamari's street to the gate (L.ROAD_CONTROL): a ribbon draped on the graded
    ground, easing onto the pad's height over its last L.ROAD_BLEND metres, with short banks down to the ground on both
    sides. Unreal draws it with Hidamari's earth (MI_HD_earth, the colour of its yards)."""
    m = v.Mesh('SM_HS_Road')
    pts = L.road_points(2.)
    half = L.ROAD_WIDTH / 2
    gz = lambda x, y: float(H.north_height(np.array([x + L.SITE[0]]), np.array([y + L.SITE[1]]))[0]) - pad_z   # graded
    s = [0.]
    for a, b in zip(pts, pts[1:]):
        s.append(s[-1] + math.dist(a, b))
    x0, y0, x1, y1 = L.COMPOUND
    on_pad = lambda x, y: x0 - 1e-6 <= x <= x1 and y0 <= y <= y1
    edge = next(s[k] for k, (x, y) in enumerate(pts) if on_pad(x, y))   # where the lane meets the pad

    def z(x, y, sk):
        if on_pad(x, y):
            return 0.
        lift = .02 + .06 * min(1., sk / 6.)                                    # flush with the street at its end
        t = min(1., max(0., (sk - (edge - L.ROAD_BLEND)) / L.ROAD_BLEND))
        t = t * t * (3 - 2 * t)
        return (gz(x, y) + lift) * (1 - t)
    rows = []
    for k, (x, y) in enumerate(pts):
        a, b = pts[max(k - 1, 0)], pts[min(k + 1, len(pts) - 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]; n = math.hypot(dx, dy)
        nx, ny = -dy / n, dx / n
        row = []
        for side in (-1, 1):
            ex, ey = x + side * nx * half, y + side * ny * half
            ez = z(ex, ey, s[k])
            bx, by = x + side * nx * (half + 1.2), y + side * ny * (half + 1.2)
            row.append(((ex, ey, ez), (bx, by, min(gz(bx, by) - .4, ez - .05))))
        rows.append(row)
    for k in range(len(rows) - 1):
        (r, rb), (l, lb) = rows[k]              # right (side -1) and left edges with their banks, facing the gate
        (r2, rb2), (l2, lb2) = rows[k + 1]
        m.poly([r, r2, l2, l], 'hs_lane_earth')
        m.poly([rb, rb2, r2, r], 'hs_lane_earth')
        m.poly([l, l2, lb2, lb], 'hs_lane_earth')
    zs = [(rows[k][0][0][2] + rows[k][1][0][2]) / 2 for k in range(len(rows))]
    return m, zs


def road_sign(pad_z):
    """Where the road leaves the street: a pair of stone lanterns and a plank sign 陽だまり厩舎 facing the city."""
    m = v.Mesh('SM_HS_RoadSign')
    gz = lambda x, y: float(H.north_height(np.array([x + L.SITE[0]]), np.array([y + L.SITE[1]]))[0]) - pad_z
    sx, sy = L.STREET_END[0] - L.SITE[0], L.STREET_END[1] - L.SITE[1]
    for side in (-1, 1):
        x, y = sx + side * (L.ROAD_WIDTH / 2 + 1.6), sy + 9.
        with m.at((0, 0, gz(x, y) - .05)):
            stone_lantern(m, x, y, 0)
    x, y = sx + L.ROAD_WIDTH / 2 + 6.5, sy + 4.
    with m.at((x, y, gz(x, y) - .1)):
        w = L.SIGN['size'][0] * .85
        for side in (-1, 1):
            m.box((side * (w / 2 - .12), 0, 1.2), (.14, .14, 2.4), 'hs_timber_dark')
        m.box((0, 0, 2.47), (w + .5, .2, .1), 'hs_timber_dark')
        m.box((0, 0, 1.75), (w, .06, .5), 'hs_trim_wood')
        with m.at((0, -.035, 1.75)):
            raised_text(m, L.NAME, (0, 0, -.32 * .25), .32, 'hs_letter', .006, .015)
    return m


# ------------------------------------------------------------------ export
def material(name=MATERIAL):
    mat = bpy.data.materials.new(name); mat.use_nodes = True
    nodes = mat.node_tree.nodes; bsdf = nodes['Principled BSDF']
    col = nodes.new('ShaderNodeVertexColor'); col.layer_name = 'Color'
    mat.node_tree.links.new(col.outputs['Color'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = .85
    return mat


CITY_SLOTS = {}     # mesh name -> its HDS_<slug> material slots, in slot order (placements, the importer)


def city_object(m, coll):
    """The ground meshes in Hidamari's own surfaces: one material slot HDS_<slug> per surface (hidamari/surfaces.py),
    UVs in metres, so Unreal draws them with the city's MI_HD_<slug> like Hidamari's yards, lanes and gravel."""
    per_face = surfaces.slugs(m); used = sorted(set(per_face)); index = {k: i for i, k in enumerate(used)}
    obj = make(m, surfaces.material(used[0]), coll)
    for k in used[1:]:
        obj.data.materials.append(surfaces.material(k))
    obj.data.polygons.foreach_set('material_index', [index[k] for k in per_face])
    CITY_SLOTS[m.name] = used
    return obj


def make(m, mat, coll):
    obj = m.object(mat)
    for c in obj.users_collection:
        c.objects.unlink(obj)
    coll.objects.link(obj)
    return obj


def tris(m):
    return sum(len(f) - 2 for f in m.faces)


def export_glb(path, objs):
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.hide_set(False); o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    kw = dict(filepath=str(path), export_format='GLB', use_selection=True, export_yup=True, export_apply=True,
              export_extras=True, export_materials='EXPORT', export_cameras=False, export_lights=False, export_animations=False)
    try:
        bpy.ops.export_scene.gltf(**kw, export_vertex_color='ACTIVE')
    except TypeError:
        bpy.ops.export_scene.gltf(**kw)
    bpy.ops.object.select_all(action='DESELECT')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collision(coll):
    objs = []
    for i, b in enumerate(L.collision_boxes()):
        me = bpy.data.meshes.new(f'UCX_SM_HS_Stable_{i:02d}')
        sx, sy, sz = (s / 2 for s in b['size'])
        vs = [(dx * sx, dy * sy, dz * sz) for dx in (-1, 1) for dy in (-1, 1) for dz in (-1, 1)]
        fs = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
        me.from_pydata(vs, [], fs); me.update()
        o = bpy.data.objects.new(me.name, me); coll.objects.link(o)
        o.location = b['centre']; o.rotation_euler = tuple(math.radians(a) for a in b['rot'])
        o['part'] = b['name']
        objs.append(o)
    return objs


def anchors(coll, data):
    """Empties for the anchors, so the .blend shows them."""
    def empty(name, at, kind='PLAIN_AXES', size=.3):
        o = bpy.data.objects.new(name, None); o.empty_display_type = kind; o.empty_display_size = size
        o.location = at; coll.objects.link(o)
    for s in data['stalls']:
        empty(f'DOOR_{s["id"]}', s['door']['pivot'], 'ARROWS'); empty(f'PLAQUE_{s["id"]}', s['plaque']['centre'], 'CUBE', .15)
        empty(f'HORSE_{s["id"]}', s['horse']['at'], 'SINGLE_ARROW', .8)
    empty('SIGN', data['sign']['centre'], 'CUBE', .3); empty('NOTICE_BOARD', data['notice_board']['centre'], 'CUBE', .3)
    for kind in ('npc', 'horse'):
        for p in data['spots'][kind]:
            empty(f'{kind.upper()}_{p["id"]}', p['at'], 'SINGLE_ARROW', .6)


def main():
    palette()
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    OUT.mkdir(parents=True, exist_ok=True); GLB.mkdir(parents=True, exist_ok=True)
    pad_z = L.PAD_Z
    platform_z = HL.platform_height(H.north_height)
    print(f'HIDAMARI STABLE: pad {pad_z} m at {L.SITE}, hippodrome platform {platform_z} m', flush=True)
    mat = material()
    scene = bpy.context.scene
    meshes, counts, files = {}, {}, {}

    hide = []

    def collection(name, hidden=False):
        c = bpy.data.collections.new(name); scene.collection.children.link(c)
        if hidden:
            hide.append(c)
        return c

    for lod in (0, 1, 2):
        coll = collection(f'LOD{lod}', hidden=lod > 0)
        m = v.Mesh(f'SM_HS_Stable_LOD{lod}')
        barn(m, lod); gate(m, lod); yard(m, lod); paddock(m, lod)
        counts[m.name] = tris(m)
        obj = make(m, mat, coll)
        doors = []
        for name, build_door in (('StallDoor', stall_door), ('RoomDoor', room_door)):
            d = build_door(lod)
            counts[d.name] = tris(d)
            dobj = make(d, mat, coll)
            doors.append(dobj)
            meshes[d.name] = dobj
        meshes[m.name] = obj
        print(f'HIDAMARI STABLE LOD{lod}: {counts[m.name]} triangles', flush=True)
    coll = collection('Ground')
    g = ground(pad_z); counts[g.name] = tris(g); meshes[g.name] = city_object(g, coll)
    r, road_z = road(pad_z); counts[r.name] = tris(r); meshes[r.name] = city_object(r, coll)
    rs = road_sign(pad_z); counts[rs.name] = tris(rs); meshes[rs.name] = make(rs, mat, coll)
    ccoll = collection('Collision', hidden=True)
    ucx = collision(ccoll)

    # door instances in the LOD collections, so the .blend and the renders show them closed in place
    data = placements(pad_z, platform_z, road_z)
    for lod in (0, 1, 2):
        coll = bpy.data.collections[f'LOD{lod}']
        for inst in data['doors']:
            src = meshes[f'SM_HS_{inst["mesh"]}_LOD{lod}']
            o = bpy.data.objects.new(f'{inst["id"]}_LOD{lod}', src.data); coll.objects.link(o)
            o.location = inst['pivot']; o.rotation_euler = (0, 0, math.radians(inst['yaw']))
            o['instance'] = True
    acoll = collection('Anchors', hidden=True)
    anchors(acoll, data)

    for name, obj in meshes.items():
        path_ = GLB / f'{name}.glb'
        export_glb(path_, [obj]); files[name] = path_
    path_ = GLB / 'SM_HS_Stable_Collision.glb'
    export_glb(path_, ucx); files['SM_HS_Stable_Collision'] = path_
    (OUT / 'placements.json').write_text(json.dumps(data, indent=1, ensure_ascii=False))
    for c in hide:
        c.hide_render = True; c.hide_viewport = True
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'hidamari-stable.blend'))

    budgets = L.BUDGETS
    checks = []
    for lod in (0, 1, 2):
        n = counts[f'SM_HS_Stable_LOD{lod}']
        if n > budgets[f'LOD{lod}']:
            checks.append(f'SM_HS_Stable_LOD{lod}: {n} triangles over {budgets[f"LOD{lod}"]}')
    if counts['SM_HS_Stable_LOD1'] >= counts['SM_HS_Stable_LOD0'] or counts['SM_HS_Stable_LOD2'] >= counts['SM_HS_Stable_LOD1']:
        checks.append('LODs do not decrease')
    if counts['SM_HS_StallDoor_LOD0'] > budgets['door_LOD0']:
        checks.append('stall door over budget')
    if len(ucx) > budgets['collision_boxes']:
        checks.append('too many collision boxes')
    manifest = dict(
        step='world.hidamari_stable', name=L.NAME,
        units='metres in the .blend and placements; GLBs are standard glTF (Y-up) exported by Blender',
        site=data['site'], budgets=budgets, triangles=counts, collision_boxes=len(ucx),
        files={k: dict(path=str(f.relative_to(OUT)), sha256=sha(f), bytes=f.stat().st_size) for k, f in files.items()},
        checks=checks)
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    print('HIDAMARI STABLE triangles:', json.dumps(counts), flush=True)
    if checks:
        raise SystemExit('HIDAMARI STABLE checks failed: ' + '; '.join(checks))
    print('HIDAMARI STABLE COMPLETE', flush=True)


def placements(pad_z, platform_z, road_z):
    stalls = L.stalls(); rooms = L.rooms()
    doors = [dict(id=f'door_{s["id"]}', mesh='StallDoor', pivot=s['door']['pivot'], yaw=0., slide=s['door']['slide'],
                  travel=s['door']['travel'], stall=s['id']) for s in stalls]
    doors += [dict(id=f'door_{k}', mesh='RoomDoor', pivot=r['door']['pivot'], yaw=0., slide=r['door']['slide'],
                   travel=r['door']['travel'], room=k) for k, r in rooms.items()]
    lods = lambda base: [f'glb/{base}_LOD{k}.glb' for k in (0, 1, 2)]
    return dict(
        version=1, name=L.NAME,
        frame='stable frame: Blender metres, x east, y north, z up; origin on the pad top at site.origin; yaw 0. '
              'Island = site.origin + p; Unreal centimetres = (100 x, -100 y, 100 z). Yaw degrees counter-clockwise from +x.',
        site=dict(origin=[L.SITE[0], L.SITE[1], pad_z], yaw_deg=L.YAW, pad=list(L.COMPOUND), grade=dict(slope=L.GRADE_SLOPE, reach=L.GRADE_REACH),
                  hippodrome_platform_z=platform_z,
                  unreal_origin_cm=[L.SITE[0] * 100, -L.SITE[1] * 100, pad_z * 100]),
        meshes=[
            dict(name='SM_HS_Stable', lods=lods('SM_HS_Stable'), lod_screen_sizes=list(L.LOD_SCREEN_SIZES),
                 collision='glb/SM_HS_Stable_Collision.glb', at=[0, 0, 0], yaw=0., blocks=True),
            dict(name='SM_HS_Ground', file='glb/SM_HS_Ground.glb', at=[0, 0, 0], yaw=0., blocks=True, collision='complex',
                 slots=CITY_SLOTS['SM_HS_Ground']),
            dict(name='SM_HS_Road', file='glb/SM_HS_Road.glb', at=[0, 0, 0], yaw=0., blocks=True, collision='complex',
                 slots=CITY_SLOTS['SM_HS_Road']),
            dict(name='SM_HS_RoadSign', file='glb/SM_HS_RoadSign.glb', at=[0, 0, 0], yaw=0., blocks=True, collision='complex'),
            dict(name='SM_HS_StallDoor', lods=lods('SM_HS_StallDoor'), instances='doors[mesh=StallDoor]', collision='box'),
            dict(name='SM_HS_RoomDoor', lods=lods('SM_HS_RoomDoor'), instances='doors[mesh=RoomDoor]', collision='box'),
        ],
        barn=dict(centre=list(L.BARN_CENTRE), length=L.BARN_LENGTH, width=L.BARN_WIDTH, floor_z=L.FLOOR_Z,
                  eave_z=L.EAVE_Z, ridge_z=round(L.RIDGE_Z, 3), aisle=[L.AISLE_Y0, L.AISLE_Y1], aisle_door=list(L.AISLE_DOOR),
                  doorways=[[L.BARN_X0, L.BARN_CENTRE[1]], [L.BARN_X1, L.BARN_CENTRE[1]]]),
        stalls=[dict(id=s['id'], box=list(s['box']), door=s['door'], plaque=s['plaque'], horse=s['horse']) for s in stalls],
        rooms={k: dict(box=list(r['box']), door=r['door']) for k, r in rooms.items()},
        doors=doors,
        sign=dict(text=L.NAME, centre=L.SIGN['centre'], normal=L.SIGN['normal'], size=L.SIGN['size'], gate=list(L.GATE['at'])),
        notice_board=dict(**L.notice_board(), use='transfers'),
        spots=L.spots(),
        yard=dict(rect=list(L.YARD), trough=L.TROUGH, hitch=L.HITCH, lanterns=L.LANTERNS),
        paddock=dict(rect=list(L.PADDOCK), gate=L.PADDOCK_GATE),
        road=dict(width=L.ROAD_WIDTH, street_end=list(L.STREET_END),
                  points=[[round(x, 3), round(y, 3), round(z, 3)] for (x, y), z in zip(L.road_points(2.), road_z)]),
        clearance=L.clearance(),
        collision=[dict(name=b['name'], box=list(b['box'])) for b in L.aabb_boxes()],
    )


if __name__ == '__main__':
    main()
