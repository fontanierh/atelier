"""The four kei cars parked in the Mega Park car park (docs/MEGAPARK.md, "Restyle").

After the Sunburst sheet assets/megapark/concepts/kei-sheet.jpg: a sage kei pickup with a crate and a skateboard in
its bed, an ochre-and-cream wagon, a vermilion retro car with round lamps and a cream roof, and an indigo microvan with
a cream waist and two skateboards on its roof rack. Flat-shaded vertex colours on M_Village, like the village props.

Metres; +X is the nose, the ground is z = 0 under the middle of the car, +Y its left. Each car has box collision
(UCX) from the ground up, so Cairo walks round them and the board stops against them.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402,F401
import json
import math

import bpy
from mathutils import Vector
from village import build as v

OUT = yori.OUT / 'kei'; v.OUT = OUT
LENGTH, WIDTH = 3.39, 1.47          # the kei class's outer limits

CREAM = (.62, .57, .45); TYRE = (.016, .016, .018); HUB = (.55, .50, .40); GLASS = (.022, .027, .042)
DARK = (.028, .028, .03); PLATE = (.72, .46, .03); LAMP = (.80, .76, .64); AMBER = (.72, .26, .02)
RED = (.46, .03, .02); CHROME = (.34, .34, .32); CRATE = (.30, .14, .045); SLAT = (.17, .075, .022)
SAGE = (.17, .27, .15); OCHRE = (.56, .31, .045); VERMILION = (.62, .11, .05); INDIGO = (.05, .085, .30)
NAVY = (.03, .04, .11); TEAL = (.04, .17, .12); BRICK = (.30, .07, .025); WHEEL = (.70, .45, .03)


def shade(color, f):
    return tuple(c * f for c in color)


def face(m, points, color, out):
    """A planar polygon whose front faces along out."""
    p = [Vector(q) for q in points]
    normal = Vector((0, 0, 0))
    for a, b in zip(p, p[1:] + p[:1]):
        normal += Vector(((a.y - b.y) * (a.z + b.z), (a.z - b.z) * (a.x + b.x), (a.x - b.x) * (a.y + b.y)))
    m.poly(points if normal.dot(Vector(out)) >= 0 else points[::-1], color)


class Prism:
    """A side profile [(x, z)] (convex) extruded across the car, `bottom` wide at its lowest point and `top` at its
    highest: the glasshouse leans in as it rises."""

    def __init__(self, m, profile, bottom, top, color):
        self.profile = profile; self.bottom = bottom; self.top = top
        zs = [z for _, z in profile]; self.low, self.high = min(zs), max(zs)
        self.centre = (sum(x for x, _ in profile) / len(profile), sum(zs) / len(profile))
        left = [(x, self.half(z), z) for x, z in profile]; right = [(x, -self.half(z), z) for x, z in profile]
        face(m, left, color, (0, 1, 0)); face(m, right, color, (0, -1, 0))
        for k in range(len(profile)):
            j = (k + 1) % len(profile)
            out = self.outward(profile[k], profile[j])
            face(m, [left[k], left[j], right[j], right[k]], color, (out[0], 0, out[1]))

    def half(self, z, inset=0.):
        t = (z - self.low) / (self.high - self.low)
        return (self.bottom + (self.top - self.bottom) * t) / 2 - inset

    def outward(self, a, b):
        n = (b[1] - a[1], a[0] - b[0]); length = math.hypot(*n); n = (n[0] / length, n[1] / length)
        mid = ((a[0] + b[0]) / 2 - self.centre[0], (a[1] + b[1]) / 2 - self.centre[1])
        return n if n[0] * mid[0] + n[1] * mid[1] > 0 else (-n[0], -n[1])

    def side(self, m, points, color):
        """A panel [(x, z)] on both flanks (side windows, a stripe)."""
        for s in (1, -1):
            face(m, [(x, s * (self.half(z) + .006), z) for x, z in points], color, (0, s, 0))

    def edge(self, m, k, color, t=(.1, .9), inset=.1):
        """A panel on the face between profile points k and k + 1 (windscreen, back window), inset from its sides."""
        a, b = self.profile[k], self.profile[(k + 1) % len(self.profile)]
        out = self.outward(a, b)
        corners = []
        for u, s in ((t[0], 1), (t[1], 1), (t[1], -1), (t[0], -1)):
            x = a[0] + (b[0] - a[0]) * u + out[0] * .006; z = a[1] + (b[1] - a[1]) * u + out[1] * .006
            corners.append((x, s * self.half(z, inset), z))
        face(m, corners, color, (out[0], 0, out[1]))


def disc(m, centre, radius, axis, color, n=16):
    """A flat round facing along axis ('x' or 'y', signed by its sign: '+x', '-y')."""
    sign = 1 if axis[0] == '+' else -1; x, y, z = centre
    if axis[1] == 'x':
        points = [(x, y + radius * math.cos(a), z + radius * math.sin(a)) for a in (2 * math.pi * k / n for k in range(n))]
        face(m, points, color, (sign, 0, 0))
    else:
        points = [(x + radius * math.cos(a), y, z + radius * math.sin(a)) for a in (2 * math.pi * k / n for k in range(n))]
        face(m, points, color, (0, sign, 0))


def wheel(m, x, s, radius=.27, width=.165, body=.38, n=16):
    """A tyre with a cream hub on side s (+1 left), its outer face just inside the body, and the dark wheel arch on
    the body's flank above it (the body's bottom is at height `body`)."""
    y = s * (WIDTH / 2 - width / 2 - .006)
    rings = [[(x + radius * math.cos(a), y + s * w, radius + radius * math.sin(a)) for a in (2 * math.pi * k / n for k in range(n))]
             for w in (width / 2, -width / 2)]
    face(m, rings[0], TYRE, (0, s, 0)); face(m, rings[1], TYRE, (0, -s, 0))
    for k in range(n):
        a = 2 * math.pi * (k + .5) / n
        face(m, [rings[0][k], rings[0][(k + 1) % n], rings[1][(k + 1) % n], rings[1][k]], TYRE, (math.cos(a), 0, math.sin(a)))
    disc(m, (x, y + s * (width / 2 + .004), radius), radius * .56, '+y' if s > 0 else '-y', HUB, n=12)
    disc(m, (x, y + s * (width / 2 + .007), radius), radius * .16, '+y' if s > 0 else '-y', shade(HUB, .55), n=8)
    arch = radius + .06
    if body < radius + arch:
        start = math.asin(max(-1., min(1., (body - radius) / arch)))
        angles = [start + (math.pi - 2 * start) * k / 10 for k in range(11)]
        face(m, [(x + arch * math.cos(a), s * (WIDTH / 2 + .004), radius + arch * math.sin(a)) for a in angles], DARK, (0, s, 0))


def skateboard(m, a, b, deck, up=(0, 0, 1)):
    """A board from a to b (deck centre line) with its wheels on the `up` side."""
    a, b, up = Vector(a), Vector(b), Vector(up).normalized()
    m.beam(tuple(a), tuple(b), .21, .022, deck)
    along = (b - a).normalized(); across = along.cross(up).normalized()
    for t in (.17, .83):
        for s in (1, -1):
            c = a + (b - a) * t + across * s * .075 + up * .045
            m.box(tuple(c), (.05, .05, .04), WHEEL)
        c = a + (b - a) * t + up * .025
        m.box(tuple(c), (.05, .15, .025), CHROME)


def face_details(m, front, lamp_z, plate_z=.50, bumper=DARK, bumper_z=.45, round_lamps=False):
    """Headlamps, indicators, a grille, bumper and the yellow kei plate on the nose at x = front."""
    if round_lamps:
        for s in (1, -1):
            disc(m, (front + .004, s * .47, lamp_z), .115, '+x', CHROME)
            disc(m, (front + .009, s * .47, lamp_z), .085, '+x', LAMP)
        m.box((front + .004, 0, lamp_z - .02), (.01, .36, .035), DARK)
    else:
        for s in (1, -1):
            m.box((front + .006, s * .52, lamp_z), (.012, .22, .14), LAMP)
            m.box((front + .006, s * .66, lamp_z - .12), (.012, .07, .06), AMBER)
        for dz in (-.03, .03):
            m.box((front + .006, 0, lamp_z + dz - .02), (.012, .5, .025), DARK)
    m.box((front - .02, 0, bumper_z), (.12, WIDTH + .01, .13), bumper, bevel=.03)
    m.box((front + .045, 0, plate_z), (.012, .33, .165), PLATE)


def tail_details(m, back, z, height=.22):
    for s in (1, -1):
        m.box((back - .006, s * .62, z), (.012, .12, height), RED)
    m.box((back + .02, 0, .45), (.12, WIDTH + .01, .13), DARK, bevel=.03)
    m.box((back - .045, 0, .52), (.012, .33, .165), PLATE)


def mirrors(m, x, z):
    for s in (1, -1):
        m.beam((x, s * .70, z - .05), (x + .03, s * .80, z), .03, .03, DARK)
        m.box((x + .03, s * .82, z + .04), (.05, .05, .14), DARK)


def underbody(m, length, body):
    m.box((0, 0, (body + .2) / 2), (length - .5, WIDTH - .3, body - .2), DARK)


def pickup():
    m = v.Mesh('SM_Kei_Pickup')
    front, back, body = LENGTH / 2, -LENGTH / 2, .40
    for x, bottom in ((1.02, body), (-1.04, .54)):             # the rear wheels stand clear under the bed
        for s in (1, -1):
            wheel(m, x, s, body=bottom)
    underbody(m, LENGTH, body)
    m.box((1.15, 0, .71), (1.08, WIDTH, .62), SAGE, bevel=.07)                     # the cab, over the front wheels
    cab = Prism(m, [(.64, 1.02), (front - .03, 1.02), (1.60, 1.56), (.70, 1.58)], 1.43, 1.32, SAGE)
    cab.edge(m, 1, GLASS, t=(.08, .9), inset=.09)
    cab.edge(m, 3, GLASS, t=(.15, .85), inset=.2)
    cab.side(m, [(.80, 1.08), (1.52, 1.08), (1.46, 1.48), (.82, 1.50)], GLASS)
    m.box((1.15, 0, 1.60), (1.06, 1.36, .09), CREAM, bevel=.035)
    m.box((front + .004, 0, .90), (.01, .9, .05), shade(SAGE, .7))
    face_details(m, front, .78)
    mirrors(m, 1.50, 1.18)
    for s in (1, -1):
        m.box((1.0, s * (WIDTH / 2 + .005), .80), (.12, .01, .03), DARK)            # door handles
    # The bed: floor, drop sides and tailgate with their ribs, and the guard behind the cab.
    bed = SAGE
    m.box((-.55, 0, .58), (2.24, WIDTH, .08), shade(bed, .7))
    for s in (1, -1):
        m.box((-.55, s * (WIDTH / 2 - .025), .79), (2.24, .05, .36), bed, bevel=.012)
        m.box((-.55, s * (WIDTH / 2 + .002), .86), (2.2, .01, .03), shade(bed, .72))
    m.box((back + .025, 0, .79), (.05, WIDTH, .36), bed, bevel=.012)
    m.box((back - .002, 0, .86), (.01, 1.4, .03), shade(bed, .72))
    for s in (1, -1):
        m.box((.585, s * .66, 1.12), (.05, .06, .72), shade(bed, .55))
    for z in (.98, 1.3, 1.46):
        m.box((.585, 0, z), (.05, 1.38, .04), shade(bed, .55))
    for s in (1, -1):
        m.box((back - .006, s * .6, .72), (.012, .12, .14), RED)
    m.box((back - .045, 0, .52), (.012, .33, .165), PLATE)
    # A crate and a board leaning on the guard.
    m.box((-.30, .28, .80), (.56, .46, .36), CRATE, bevel=.015)
    for z in (.70, .86):
        for s in (1, -1):
            m.box((-.30, .28 + s * .233, z), (.5, .01, .05), SLAT)
            m.box((-.30 + s * .283, .28, z), (.01, .4, .05), SLAT)
    skateboard(m, (.10, -.35, .66), (.48, -.35, 1.42), NAVY, up=(-1, 0, .5))
    m.collider((1.15, 0, .82), (1.08, WIDTH, 1.64))
    m.collider((-.55, 0, .49), (2.26, WIDTH, .98))
    return m


def wagon():
    m = v.Mesh('SM_Kei_Wagon')
    front, back, body = LENGTH / 2, -LENGTH / 2, .38
    for x in (1.13, -1.12):
        for s in (1, -1):
            wheel(m, x, s, body=body)
    underbody(m, LENGTH, body)
    m.box((0, 0, .69), (LENGTH, WIDTH, .62), OCHRE, bevel=.09)
    top = Prism(m, [(back + .02, 1.0), (front - .06, 1.0), (1.22, 1.76), (back + .05, 1.79)], 1.45, 1.33, CREAM)
    top.edge(m, 1, GLASS, t=(.1, .9), inset=.1)
    top.edge(m, 3, GLASS, t=(.12, .82), inset=.14)
    nose = lambda z: front - .06 - (z - 1.0) * (front - .06 - 1.22) / .76
    top.side(m, [(.56, 1.07), (nose(1.07) - .1, 1.07), (nose(1.66) - .1, 1.66), (.56, 1.68)], GLASS)
    top.side(m, [(-.42, 1.07), (.44, 1.07), (.44, 1.68), (-.42, 1.69)], GLASS)
    top.side(m, [(back + .2, 1.07), (-.54, 1.07), (-.54, 1.69), (back + .22, 1.70)], GLASS)
    m.box((-.15, 0, 1.79), (2.9, 1.3, .05), shade(CREAM, .9), bevel=.02)
    for x in (.45, -.5):
        for s in (1, -1):
            m.box((x, s * (WIDTH / 2 + .003), .70), (.012, .006, .6), shade(OCHRE, .6))
            m.box((x - .14, s * (WIDTH / 2 + .006), .88), (.12, .01, .03), DARK)
    face_details(m, front, .84, bumper=shade(OCHRE, .75))
    tail_details(m, back, .78, height=.26)
    mirrors(m, 1.30, 1.10)
    m.collider((0, 0, .9), (LENGTH, WIDTH, 1.8))
    return m


def retro():
    m = v.Mesh('SM_Kei_Retro')
    length = 3.30; front, back, body = length / 2, -length / 2, .36
    for x in (1.08, -1.06):
        for s in (1, -1):
            wheel(m, x, s, radius=.26, body=body)
    underbody(m, length, body)
    m.box((0, 0, .63), (length - .04, WIDTH, .54), VERMILION, bevel=.15)
    cabin = Prism(m, [(back + .12, .88), (.78, .88), (.32, 1.38), (back + .26, 1.41)], 1.40, 1.24, VERMILION)
    cabin.edge(m, 1, GLASS, t=(.12, .9), inset=.1)
    cabin.edge(m, 3, GLASS, t=(.12, .88), inset=.14)
    nose = lambda z: .78 - (z - .88) * (.78 - .32) / .5
    cabin.side(m, [(-.12, .95), (nose(.95) - .08, .95), (nose(1.33) - .08, 1.33), (-.12, 1.34)], GLASS)
    cabin.side(m, [(back + .32, .95), (-.24, .95), (-.24, 1.34), (back + .38, 1.35)], GLASS)
    m.box((-.55, 0, 1.415), (1.86, 1.27, .07), CREAM, bevel=.03)
    face_details(m, front - .02, .62, bumper=CREAM, bumper_z=.42, plate_z=.44, round_lamps=True)
    for s in (1, -1):
        m.box((.12, s * (WIDTH / 2 + .006), .80), (.13, .01, .03), CHROME)
        m.box((back + .014, s * .55, .70), (.012, .12, .12), RED)
    m.box((back + .03, 0, .42), (.14, WIDTH + .02, .12), CREAM, bevel=.04)
    m.box((back + .005, 0, .52), (.012, .33, .165), PLATE)
    mirrors(m, .66, .98)
    m.collider((0, 0, .72), (length, WIDTH, 1.44))
    return m


def microvan():
    m = v.Mesh('SM_Kei_Microvan')
    front, back, body = LENGTH / 2, -LENGTH / 2, .38
    for x in (1.13, -1.13):
        for s in (1, -1):
            wheel(m, x, s, body=body)
    underbody(m, LENGTH, body)
    m.box((0, 0, .68), (LENGTH, WIDTH, .60), INDIGO, bevel=.08)
    m.box((0, 0, 1.06), (LENGTH - .02, WIDTH - .01, .16), CREAM)
    top = Prism(m, [(back + .02, 1.14), (front - .03, 1.14), (1.44, 1.84), (back + .03, 1.88)], 1.45, 1.36, INDIGO)
    top.edge(m, 1, GLASS, t=(.08, .9), inset=.1)
    top.edge(m, 3, GLASS, t=(.1, .8), inset=.14)
    nose = lambda z: front - .03 - (z - 1.14) * (front - .03 - 1.44) / .7
    top.side(m, [(.66, 1.2), (nose(1.2) - .1, 1.2), (nose(1.74) - .1, 1.74), (.66, 1.76)], GLASS)
    top.side(m, [(-.38, 1.2), (.54, 1.2), (.54, 1.76), (-.38, 1.77)], GLASS)
    top.side(m, [(back + .18, 1.2), (-.5, 1.2), (-.5, 1.77), (back + .2, 1.78)], GLASS)
    for x in (.6, -.44):
        for s in (1, -1):
            m.box((x - .14, s * (WIDTH / 2 + .006), .9), (.12, .01, .03), DARK)
    face_details(m, front, .84, bumper=shade(INDIGO, .7))
    tail_details(m, back, .74, height=.24)
    mirrors(m, 1.38, 1.24)
    # The roof rack, and two boards on it wheels up.
    for x in (.55, -.85):
        for s in (1, -1):
            m.box((x, s * .62, 1.905), (.05, .05, .05), DARK)
        m.box((x, 0, 1.95), (.07, 1.38, .045), (.10, .05, .02), bevel=.01)
    for s in (1, -1):
        m.box((-.15, s * .66, 1.985), (1.62, .04, .03), (.10, .05, .02))
    skateboard(m, (-.55, .25, 2.012), (.28, .30, 2.012), BRICK)
    skateboard(m, (-.62, -.24, 2.012), (.22, -.27, 2.012), TEAL)
    m.collider((0, 0, .95), (LENGTH, WIDTH, 1.9))
    return m


def main():
    OUT.mkdir(parents=True, exist_ok=True); (OUT / 'assets').mkdir(exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mat = bpy.data.materials.new('KeiPalette'); mat.use_nodes = True
    vc = mat.node_tree.nodes.new('ShaderNodeVertexColor'); vc.layer_name = 'Color'
    mat.node_tree.links.new(vc.outputs['Color'], mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
    manifest = {}
    for make in (pickup, wagon, retro, microvan):
        m = make(); ob, report = v.export(m, mat); manifest[m.name] = report
        bpy.data.objects.remove(ob, do_unlink=True)
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('KEI BUILD COMPLETE', sum(a['triangles'] for a in manifest.values()), 'triangles')


if __name__ == '__main__':
    main()
