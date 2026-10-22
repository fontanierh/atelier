"""Reusable Brinecove pieces: houses, taverns, wharf furniture, ships, palms and landmarks."""
import math
import random
from foliage_roles import SurfaceKey
from brinecove.geom import Builder
from brinecove.foliage_atlas import LEAF_CELLS, PALM_CELLS, cell_uvs

TAU = math.pi * 2


def local(cx, cy, yaw, lx, ly):
    a = math.radians(yaw)
    return cx + lx * math.cos(a) - ly * math.sin(a), cy + lx * math.sin(a) + ly * math.cos(a)


SHUTTER_COLORS = ('shutter_teal', 'shutter_blue', 'shutter_green', 'shutter_red', 'wood_dark')


def shutter_color(cx, cy, lx):
    return SHUTTER_COLORS[int(abs(cx * 3.1 + cy * 7.3 + lx * 11.7)) % len(SHUTTER_COLORS)]


def window(b, cx, cy, yaw, lx, ly, z, w=1.3, h=1.6, shutters=True, warm=False, shutter=None, trim='cream',
           lintel=False):
    x, y = local(cx, cy, yaw, lx, ly)
    # Dark glass set back behind a deep architrave, so the opening reads as a reveal rather than a decal.
    b.box((x, y, z + h / 2), (w, 0.12, h), 'glass_warm' if warm else 'glass', yaw)
    for side in (-1, 1):
        jx, jy = local(cx, cy, yaw, lx + side * (w / 2 + 0.10), ly - 0.08)
        b.box((jx, jy, z + h / 2 + 0.05), (0.22, 0.30, h + 0.22), trim, yaw)
    hx, hy = local(cx, cy, yaw, lx, ly - 0.08)
    b.box((hx, hy, z + h / 2), (w, 0.08, 0.10), trim, yaw)
    b.box((hx, hy, z + h / 2), (0.09, 0.08, h), trim, yaw)
    if lintel:
        # A dressed stone lintel with a proud keystone over the better rooms.
        b.box((hx, hy, z + h + 0.17), (w + 0.70, 0.32, 0.30), 'stone_light', yaw)
        kx, ky = local(cx, cy, yaw, lx, ly - 0.12)
        b.box((kx, ky, z + h + 0.20), (0.34, 0.38, 0.46), 'stone_light', yaw, top=1.25)
    else:
        b.box((hx, hy, z + h + 0.12), (w + 0.44, 0.30, 0.22), trim, yaw)
    sx, sy = local(cx, cy, yaw, lx, ly - 0.10)
    b.box((sx, sy, z - 0.06), (w + 0.66, 0.38, 0.14), 'stone_light', yaw)
    b.box((sx, sy, z - 0.22), (w + 0.36, 0.22, 0.18), 'stone_light', yaw, top=1.2)
    if shutters:
        mat = shutter or shutter_color(cx, cy, lx)
        for side in (-1, 1):
            slx = lx + side * (w / 2 + 0.42)
            sx, sy = local(cx, cy, yaw, slx, ly)
            b.box((sx, sy, z + h / 2), (0.36, 0.12, h + 0.16), mat, yaw)
            a0, a1 = local(cx, cy, yaw, slx - 0.13, ly - 0.08), local(cx, cy, yaw, slx + 0.13, ly - 0.08)
            for i in range(4):
                zz = z + 0.18 + i * (h - 0.10) / 4
                b.beam((a0[0], a0[1], zz), (a1[0], a1[1], zz), 0.05, 'wood_dark')


def side_window(b, cx, cy, yaw, lx, ly, z, w=1.15, h=1.45, shutters=True, warm=False, trim='cream'):
    """A window on a wall whose normal runs along local X (outward is the sign of lx)."""
    o = 1.0 if lx >= 0 else -1.0
    x, y = local(cx, cy, yaw, lx, ly)
    b.box((x, y, z + h / 2), (0.12, w, h), 'glass_warm' if warm else 'glass', yaw)
    for side in (-1, 1):
        jx, jy = local(cx, cy, yaw, lx + o * 0.07, ly + side * (w / 2 + 0.10))
        b.box((jx, jy, z + h / 2 + 0.05), (0.26, 0.20, h + 0.20), trim, yaw)
    fx, fy = local(cx, cy, yaw, lx + o * 0.07, ly)
    b.box((fx, fy, z + h / 2), (0.08, w, 0.10), trim, yaw)
    b.box((fx, fy, z + h / 2), (0.08, 0.09, h), trim, yaw)
    b.box((fx, fy, z + h + 0.11), (0.28, w + 0.40, 0.20), trim, yaw)
    sx, sy = local(cx, cy, yaw, lx + o * 0.10, ly)
    b.box((sx, sy, z - 0.06), (0.34, w + 0.62, 0.13), 'stone_light', yaw)
    if shutters:
        mat = shutter_color(cx, cy, lx)
        for side in (-1, 1):
            sy = ly + side * (w / 2 + 0.38)
            sx, syy = local(cx, cy, yaw, lx + o * 0.02, sy)
            b.box((sx, syy, z + h / 2), (0.12, 0.34, h + 0.16), mat, yaw)
            for i in range(4):
                b.box((sx, syy, z + 0.18 + i * (h - 0.10) / 4), (0.13, 0.27, 0.045), 'wood_dark', yaw)


def dormer(b, cx, cy, yaw, lx, ly, z, roof='roof_terra'):
    x, y = local(cx, cy, yaw, lx, ly)
    b.box((x, y, z + 1.15), (2.8, 2.5, 2.3), 'cream', yaw)
    b.gable_roof((x, y, z + 2.3), 2.8, 2.5, z + 2.3, 1.25, roof, yaw, ridge='y', overhang=0.35, gable='cream')
    window(b, x, y, yaw, 0, -1.3, z + 0.35, 1.05, 1.35, False, rng_bool(cx, cy, lx))


def rng_bool(x, y, seed=0):
    return ((int(x * 17 + y * 31 + seed * 13) & 7) == 3)


def flower_box(b, cx, cy, yaw, lx, ly, z):
    x, y = local(cx, cy, yaw, lx, ly)
    b.box((x, y, z), (1.35, 0.34, 0.30), 'wood_dark', yaw)
    for i in range(2):
        px, py = local(cx, cy, yaw, lx - 0.3 + i * 0.6, ly - 0.08)
        b.sphere((px, py, z + 0.24), 0.26, SurfaceKey('jungle' if i else 'jungle_light','leaf'),
                 (1.4, 0.9, 0.8), subdiv=0)
    for i in range(6):
        px, py = local(cx, cy, yaw, lx - 0.5 + i * 0.2, ly - 0.16)
        b.sphere((px, py, z + 0.36 + 0.05 * (i % 2)), 0.15,
                 SurfaceKey(('blossom','coral','gold','blossom_pale','cream','blossom')[i % 6],'flower'),
                 (1.0, 0.9, 0.9), subdiv=0)


def arcade(b, cx, cy, yaw, width, z, depth=2.0, columns=4):
    """A shallow stone arcade in front of a shop: depth and shadow at street level."""
    for i in range(columns + 1):
        lx = -width / 2 + width * i / columns
        px, py = local(cx, cy, yaw, lx, -depth)
        b.cylinder((px, py, z), (px, py, z + 3.05), 0.24, 'stone_light', 8)
        b.box((px, py, z + 0.2), (0.75, 0.75, 0.35), 'stone', yaw)
        b.box((px, py, z + 3.2), (0.75, 0.75, 0.3), 'stone', yaw)
    px, py = local(cx, cy, yaw, 0, -depth)
    b.box((px, py, z + 3.5), (width + 0.8, depth + 0.5, 0.5), 'stone_light', yaw)
    b.box((px, py, z + 3.85), (width + 1.0, depth + 0.7, 0.22), 'stone_dark', yaw)
    # A dark recess behind the columns keeps the arcade from reading as a fence.
    rx, ry = local(cx, cy, yaw, 0, -depth * 0.15)
    b.box((rx, ry, z + 1.55), (width - 2.5, 0.14, 3.0), 'wood_dark', yaw)


def door(b, cx, cy, yaw, lx, ly, z, w=1.6, h=2.6, surround=False):
    x, y = local(cx, cy, yaw, lx, ly)
    leaf = ('wood_dark', 'shutter_blue', 'shutter_teal', 'shutter_red', 'wood')[int(abs(cx * 2.3 + cy * 5.1)) % 5]
    b.box((x, y, z + h / 2), (w, 0.16, h), leaf, yaw)
    # Vertical boards and two iron straps on the leaf.
    for k in (-1, 1):
        px, py = local(cx, cy, yaw, lx + k * w / 6, ly - 0.09)
        b.box((px, py, z + h / 2), (0.05, 0.03, h - 0.1), 'wood_dark', yaw)
    for zz in (0.35, h - 0.45):
        px, py = local(cx, cy, yaw, lx, ly - 0.10)
        b.box((px, py, z + zz), (w - 0.1, 0.03, 0.09), 'metal', yaw)
    b.box((x, y, z - 0.06), (w + 0.55, 0.42, 0.14), 'stone_light', yaw)
    if surround:
        # Dressed stone jambs and a lintel with keystone frame the doors of the masonry houses.
        for side in (-1, 1):
            sx, sy = local(cx, cy, yaw, lx + side * (w / 2 + 0.22), ly - 0.06)
            b.box((sx, sy, z + h / 2 + 0.1), (0.42, 0.34, h + 0.2), 'stone_light', yaw)
            for k in range(3):
                bx, by = local(cx, cy, yaw, lx + side * (w / 2 + 0.30), ly - 0.08)
                b.box((bx, by, z + 0.45 + k * h * 0.34), (0.58, 0.36, 0.32), 'stone_light', yaw)
        px, py = local(cx, cy, yaw, lx, ly - 0.06)
        b.box((px, py, z + h + 0.28), (w + 1.1, 0.36, 0.40), 'stone_light', yaw)
        kx, ky = local(cx, cy, yaw, lx, ly - 0.10)
        b.box((kx, ky, z + h + 0.30), (0.40, 0.42, 0.56), 'stone_light', yaw, top=1.25)
    else:
        b.box((x, y, z + h + 0.12), (w + 0.35, 0.24, 0.22), 'wood', yaw)
        for side in (-1, 1):
            sx, sy = local(cx, cy, yaw, lx + side * (w / 2 + 0.14), ly)
            b.box((sx, sy, z + h / 2), (0.18, 0.20, h + 0.16), 'wood', yaw)
    hx, hy = local(cx, cy, yaw, lx + w * 0.3, ly - 0.10)
    b.box((hx, hy, z + h * 0.5), (0.09, 0.06, 0.09), 'gold', yaw)


def awning(b, cx, cy, yaw, width, z, depth=2.3, colors=('canvas', 'canvas_red'), poles=True):
    # Narrow alternating panels read as bold stripes from the street and the
    # harbor, which is the strongest single cue in the painted references.
    n = max(4, round(width / 1.7))
    for i in range(n):
        x0 = -width / 2 + width * i / n
        x1 = -width / 2 + width * (i + 1) / n
        a = local(cx, cy, yaw, x0, -1.0)
        c = local(cx, cy, yaw, x1, -1.0)
        d = local(cx, cy, yaw, x1, -depth)
        e = local(cx, cy, yaw, x0, -depth)
        mat = colors[i % len(colors)]
        b.panel((a[0], a[1], z), (c[0], c[1], z),
                (d[0], d[1], z - 0.55), (e[0], e[1], z - 0.55), mat, thick=0.04)
        # Hanging valance, striped to match.
        b.panel((e[0], e[1], z - 0.55), (d[0], d[1], z - 0.55),
                (d[0], d[1], z - 0.98), (e[0], e[1], z - 0.98), mat, thick=0.04)
    if poles:
        for side in (-1, 1):
            p = local(cx, cy, yaw, side * width * 0.46, -depth)
            b.beam((p[0], p[1], groundless(z)), (p[0], p[1], z - 0.45), 0.12, 'wood_dark')


def groundless(z):
    """A safety floor for awning poles: the caller has already placed the building on its pad."""
    return max(0.0, z - 3.0)


def balcony(b, cx, cy, yaw, width, z, depth=1.8):
    # Deck, brackets, rail.
    x, y = local(cx, cy, yaw, 0, -depth / 2 - 0.2)
    b.box((x, y, z), (width, depth, 0.24), 'wood', yaw)
    for side in (-1, 1):
        px, py = local(cx, cy, yaw, side * width * 0.42, -0.35)
        b.beam((px, py, z - 1.8), (px, py, z), 0.20, 'wood_dark')
    for i in range(7):
        lx = -width / 2 + width * i / 6
        px, py = local(cx, cy, yaw, lx, -depth + 0.05)
        b.beam((px, py, z), (px, py, z + 1.1), 0.10, 'wood')
    px, py = local(cx, cy, yaw, 0, -depth + 0.05)
    b.beam((px - width / 2, py, z + 1.05), (px + width / 2, py, z + 1.05), 0.14, 'wood')
    # A couple of hanging lanterns under the balcony.
    for lx in (-width * 0.3, width * 0.3):
        px, py = local(cx, cy, yaw, lx, -depth + 0.05)
        b.beam((px, py, z), (px, py, z - 0.42), 0.04, 'metal')
        b.box((px, py, z - 0.62), (0.28, 0.28, 0.38), 'lantern', yaw)
    seed = int(abs(cx * 5.7 + cy * 9.1))
    # Laundry and potted plants turn the galleries into lived-in rooms.
    if seed % 3 != 0:
        a = local(cx, cy, yaw, -width * 0.38, -depth * 0.55)
        c = local(cx, cy, yaw, width * 0.38, -depth * 0.55)
        laundry_line(b, (a[0], a[1], z + 1.25), (c[0], c[1], z + 1.25), 0.35,
                     ('canvas_red', 'canvas_teal', 'canvas'))
    if seed % 2 == 0:
        for side in (-1, 1):
            px, py = local(cx, cy, yaw, side * width * 0.40, -depth * 0.60)
            potted_plant(b, px, py, z + 0.14, 0.42)


def sign(b, cx, cy, yaw, z, side=1, icon='fish'):
    """A hanging tavern sign; the painted icon is simplified to a few readable shapes."""
    ax, ay = local(cx, cy, yaw, side * 0.4, -0.2)
    bx, by = local(cx, cy, yaw, side * (0.4 + 2.0), -0.2)
    b.beam((ax, ay, z + 1.7), (bx, by, z + 1.7), 0.11, 'wood_dark')
    b.beam((bx, by, z + 1.7), (bx, by, z + 0.4), 0.06, 'metal')
    hx, hy = local(cx, cy, yaw, side * (0.4 + 1.5), -0.2)
    b.box((hx, hy, z + 0.6), (0.95, 0.12, 1.15), 'wood_dark', yaw)
    if icon == 'fish':
        b.sphere((hx, hy - 0.09, z + 0.66), 0.34, 'cream', (1.5, 0.25, 0.72))
        b.tri((hx + 0.46, hy - 0.10, z + 0.66), (hx + 0.78, hy - 0.10, z + 0.92),
              (hx + 0.78, hy - 0.10, z + 0.40), 'cream')
    elif icon == 'mug':
        b.cylinder((hx, hy - 0.10, z + 0.35), (hx, hy - 0.10, z + 0.92), 0.26, 'gold', 8)
        b.ring((hx + 0.27, hy - 0.10, z + 0.63), 0.19, 0.05, 'gold', axis='x', sides=8)
    else:
        b.sphere((hx, hy - 0.10, z + 0.68), 0.33, 'cream', (1.0, 0.25, 1.0))


def timber_frame(b, x, y, z, w, d, h, yaw, floors):
    # Front and back posts, floor bands and corner braces.
    for yy in (-d / 2 + 0.10, d / 2 - 0.10):
        n = max(3, round(w / 4.2))
        for i in range(n + 1):
            lx = -w / 2 + w * i / n
            px, py = local(x, y, yaw, lx, yy)
            b.beam((px, py, z + 1.1), (px, py, z + h - 0.45), 0.18, 'wood_dark')
        for f in range(1, floors + 1):
            zz = z + h * f / (floors + 0.2)
            px, py = local(x, y, yaw, 0, yy)
            b.beam((px - w / 2, py, zz), (px + w / 2, py, zz), 0.16, 'wood')
        for side in (-1, 1):
            px, py = local(x, y, yaw, side * (w / 2 - 0.12), yy)
            b.beam((px, py, z + 1.1), (px, py, z + h - 0.4), 0.20, 'wood_dark')
            qx, qy = local(x, y, yaw, side * (w / 2 - 2.2), yy)
            b.beam((qx, qy, z + 1.2), (px, py, z + 4.0), 0.14, 'wood_dark')


def shack_building(b, spec, rng):
    """A cluster of small stilt cabins on one lot, stepped and joined by plank walks.

    The lots are 18-28 m wide; one cabin that size reads as a barn. The paintings show huddles of cabins a few metres
    across, each with its own roof, paint and stilts, so the lot is split into two to four of them.
    """
    key, x, y, z, w, d, h, floors, style, yaw, roof = spec
    count = max(1, min(4, round(w / 7.5)))
    slot = w / count
    walls = ('planks', 'planks', 'wood_light', 'wood', 'teal_wall', 'plaster', 'sage_wall')
    roofs = ('roof_straw', 'roof_terra', 'roof_straw', 'roof_teal', 'roof_slate', 'roof_terra_light')
    previous = None
    for i in range(count):
        cw = slot * rng.uniform(0.62, 0.82)
        cd = min(d * rng.uniform(0.5, 0.72), cw * rng.uniform(0.85, 1.25))
        storeys = 2 if (floors > 1 and rng.random() < 0.6) else 1
        ch = 3.1 * storeys + rng.uniform(-0.2, 0.5)
        lx = -w / 2 + slot * (i + 0.5) + rng.uniform(-0.12, 0.12) * slot
        ly = rng.uniform(-0.18, 0.18) * d
        lift = rng.uniform(-0.6, 1.6)
        cx, cy = local(x, y, yaw, lx, ly)
        cyaw = yaw + rng.uniform(-9, 9)
        wall = walls[rng.randrange(len(walls))] if i else 'planks'
        r = roof if i == 0 else roofs[rng.randrange(len(roofs))]
        _cabin(b, (key + str(i), cx, cy, z + lift, cw, cd, ch, storeys, 'shack', cyaw, r), rng, wall,
               stilts=3.4 + lift)
        here = local(x, y, yaw, lx, ly - cd / 2 - 1.2)
        if previous is not None:
            # A plank walk with rope rails ties each cabin's porch to the next.
            a = (previous[0], previous[1], previous[2] + 0.12)
            c = (here[0], here[1], z + lift + 0.12)
            b.beam(a, c, 1.1, 'wood_light', depth=0.16)
            for side in (-0.55, 0.55):
                ra = (a[0], a[1] + side, a[2] + 1.0)
                rc = (c[0], c[1] + side, c[2] + 1.0)
                b.rope(ra, rc, sag=0.25, radius=0.04, segments=5)
        previous = (here[0], here[1], z + lift)


def _cabin(b, spec, rng, wall='planks', stilts=3.4):
    """A lived-in stilt cabin: planked walls, porch, ladder and patched roof."""
    key, x, y, z, w, d, h, floors, style, yaw, roof = spec

    def P(lx, ly, lz):
        px, py = local(x, y, yaw, lx, ly)
        return (px, py, z + lz)

    # Stilts, cross braces and the main deck.
    for sx in (-w / 2 + 0.4, 0.0, w / 2 - 0.4):
        for sy in (-d / 2 + 0.4, d / 2 - 0.4):
            b.beam(P(sx, sy, -stilts), P(sx, sy, 0.0), 0.24, 'wood_dark')
            if sy < 0:
                b.beam(P(sx, sy, -stilts * 0.8), P(sx, 0, -0.5), 0.11, 'wood_dark')
    b.box(P(0, 0, 0.08), (w + 0.5, d + 0.5, 0.28), 'wood_light', yaw)
    b.box(P(0, 0, 0.24 + h / 2), (w, d, h), wall, yaw)
    # Corner posts, a belt rail and vertical battens read as plank walls.
    for sx in (-1, 1):
        for sy in (-1, 1):
            b.box(P(sx * (w / 2 - 0.10), sy * (d / 2 - 0.10), 0.28 + h / 2),
                  (0.26, 0.26, h), 'wood_dark', yaw)
    for wall_y in (-d / 2 - 0.06, d / 2 + 0.06):
        for i in range(max(3, int(w / 1.1))):
            lx = -w / 2 + 0.55 + i * (w - 1.1) / max(1, int(w / 1.1) - 1)
            b.box(P(lx, wall_y, 0.28 + h / 2), (0.12, 0.13, h), 'wood_dark', yaw)
        b.box(P(0, wall_y, 1.35), (w, 0.16, 0.18), 'wood_dark', yaw)
    for wall_x in (-w / 2 - 0.06, w / 2 + 0.06):
        for i in range(max(2, int(d / 1.2))):
            ly = -d / 2 + 0.55 + i * (d - 1.1) / max(1, int(d / 1.2) - 1)
            b.box(P(wall_x, ly, 0.28 + h / 2), (0.13, 0.12, h), 'wood_dark', yaw)
    door(b, x, y, yaw, 0.0, -d / 2 - 0.10, z + 0.30, w=1.3, h=2.2)
    for side in (-1, 1):
        window(b, x, y, yaw, side * w * 0.30, -d / 2 - 0.06, z + 2.1,
               1.05, 1.25, shutters=True)
    # Porch deck, posts, rail and a lean-to roof.
    b.box(P(0, -d / 2 - 1.25, 0.10), (w * 0.92, 2.6, 0.24), 'wood_light', yaw)
    for side in (-1, 1):
        b.beam(P(side * w * 0.40, -d / 2 - 2.35, 0.1), P(side * w * 0.40, -d / 2 - 2.35, 2.9),
               0.14, 'wood_dark')
        b.beam(P(side * w * 0.40, -d / 2 - 0.2, 1.25), P(side * w * 0.40, -d / 2 - 2.35, 1.25),
               0.08, 'wood')
        for k in range(3):
            b.beam(P(side * w * 0.40, -d / 2 - 0.6 - k * 0.75, 1.25),
                   P(side * w * 0.40, -d / 2 - 0.6 - k * 0.75, 0.25), 0.06, 'wood')
    a0 = P(-w * 0.46, -d / 2 - 2.5, 2.85)
    a1 = P(w * 0.46, -d / 2 - 2.5, 2.85)
    c0 = P(-w * 0.46, -d / 2 + 0.1, 3.55)
    c1 = P(w * 0.46, -d / 2 + 0.1, 3.55)
    b.panel(a0, a1, c1, c0, rng.choice(('roof_straw', 'canvas_teal', 'canvas_red', 'roof_terra', 'canvas')), 'wood')
    # The roof sits on the wall plate, its gables boarded in the wall's own planks, with a stove pipe.
    b.gable_roof((x, y, z + h + 0.24), w, d, z + h + 0.24, max(1.4, min(w, d) * 0.36), roof, yaw,
                 ridge='y' if rng.random() < 0.6 else 'x', overhang=0.7, gable=wall)
    b.cylinder(P(w * 0.26, d * 0.18, h + 0.4), P(w * 0.26, d * 0.18, h + 2.3),
               0.16, 'metal', 7)
    # Ladder down from the porch, a lantern, laundry, crates and a pot.
    for side in (-1, 1):
        b.beam(P(side * 0.55, -d / 2 - 2.45, 0.2), P(side * 0.55, -d / 2 - 2.45, -stilts + 0.2),
               0.09, 'wood')
    for k in range(max(2, int(stilts / 0.42))):
        b.beam(P(-0.55, -d / 2 - 2.45, -0.2 - k * 0.42),
               P(0.55, -d / 2 - 2.45, -0.2 - k * 0.42), 0.07, 'wood_light')
    b.beam(P(-w * 0.34, -d / 2 - 0.25, 2.7), P(-w * 0.34, -d / 2 - 0.25, 2.25), 0.04, 'metal')
    b.box(P(-w * 0.34, -d / 2 - 0.25, 2.1), (0.28, 0.28, 0.36), 'lantern', yaw)
    a = P(-w * 0.35, -d / 2 - 1.6, 2.45)
    c = P(w * 0.35, -d / 2 - 1.6, 2.45)
    laundry_line(b, a, c, 0.22, ('canvas_red', 'canvas_teal', 'canvas'))
    for side in (-1, 1):
        crate(b, *P(side * w * 0.36, -d / 2 - 1.7, 0.30), 0.75, rng.uniform(0, 90))
        barrel(b, *P(side * w * 0.36 - 0.8, -d / 2 - 2.0, 0.25), 0.7)
    # A fish-drying rack, buoys and a rope coil finish the working porch.
    rack_y = -d / 2 - 2.15
    for side in (-1, 1):
        b.beam(P(side * w * 0.24, rack_y, 0.28), P(side * w * 0.24, rack_y, 2.15), 0.08, 'wood')
    b.beam(P(-w * 0.24, rack_y, 2.10), P(w * 0.24, rack_y, 2.10), 0.07, 'wood')
    for i in range(4):
        lx = -w * 0.19 + i * w * 0.125
        b.sphere(P(lx, rack_y, 1.88), 0.12, 'sail', (1.7, 0.5, 0.5), subdiv=0)
    b.sphere(P(w * 0.42, -d / 2 - 2.35, 0.7), 0.22, 'coral', subdiv=0)
    b.sphere(P(w * 0.42, -d / 2 - 2.35, 1.1), 0.18, 'gold', subdiv=0)
    b.ring(P(0, -d / 2 - 1.55, 0.30), 0.36, 0.05, 'rope', sides=10)
    potted_plant(b, *P(w * 0.42, -d / 2 - 0.4, 0.25), 0.45, rng)


def building(b, spec, rng):
    key, x, y, z, w, d, h, floors, style, yaw, roof = spec
    if style == 'shack':
        return shack_building(b, spec, rng)
    walls = {
        # The paintings' walls are warm washes over stone; teal and green belong to roofs and shutters.
        'tavern': ['cream', 'ochre', 'coral', 'plaster', 'peach_wall', 'yellow_wall'],
        'house': ['plaster', 'cream', 'peach_wall', 'ochre', 'rose_wall', 'yellow_wall', 'cream', 'sage_wall',
                  'peach_wall', 'coral'],
        'shop': ['ochre', 'coral', 'cream', 'peach_wall', 'rose_wall', 'yellow_wall', 'plaster'],
        'warehouse': ['wood_light', 'wood', 'stone_light'],
        'shack': ['wood_light', 'wood', 'plaster'],
    }[style]
    wall = walls[sum(map(ord, key)) % len(walls)]
    # Trim decisions draw from their own stream so the rest of the facade keeps its layout.
    detail = random.Random(key)
    trim = 'stone_light' if wall in ('cream', 'plaster') else 'cream'
    lintels = style in ('house', 'shop', 'tavern') and detail.random() < 0.55
    if style == 'warehouse':
        b.box((x, y, z + h / 2), (w, d, h), wall, yaw)
        b.box((x, y, z + 1.0), (w + 0.5, d + 0.5, 2.0), 'stone', yaw)
        b.box((x, y, z + h - 0.2), (w + 0.4, d + 0.4, 0.45), 'wood_dark', yaw)
        for i in range(4):
            px, py = local(x, y, yaw, -w / 2 + 0.5 + i * (w - 1) / 3, -d / 2 - 0.04)
            b.beam((px, py, z + 2.0), (px, py, z + h - 0.4), 0.22, 'wood_dark')
        # Big loading doors and a hoist beam.
        b.box((x, y - d / 2 - 0.06, z + 2.4), (w * 0.46, 0.14, 4.2), 'wood', yaw)
        b.box((x, y, z + h + 0.15), (w * 0.18, 0.25, 0.4), 'wood_dark', yaw)
        bx, by = local(x, y, yaw, 0, -d / 2 - 2.8)
        b.beam((x, y, z + h + 0.15), (bx, by, z + h + 0.15), 0.22, 'wood_dark')
        b.rope((bx, by, z + h + 0.1), (bx, by, z + 4.2), sag=0.0, radius=0.05)
    else:
        b.box((x, y, z + h / 2), (w, d, h), wall, yaw)
        b.box((x, y, z + 0.65), (w + 0.4, d + 0.4, 1.3), 'stone', yaw)
        # Timber framing only on taverns; posts on every plaster house drew a grid over the whole town.
        if style == 'tavern' and rng.random() < 0.6:
            timber_frame(b, x, y, z, w, d, h, yaw, floors)
        elif style in ('house', 'shop'):
            # A painted string course at each floor and plain pilaster strips at the corners.
            for f in range(1, floors):
                zz = z + 2.0 + f * (h - 2.2) / max(1, floors) - 0.35
                b.box((x, y, zz), (w + 0.28, d + 0.28, 0.24), 'stone_light' if wall != 'cream' else 'ochre', yaw)
        has_arcade = style in ('tavern', 'shop') and w >= 9.0 and rng.random() < 0.55
        if has_arcade:
            arcade(b, x, y, yaw, w * 0.74, z + 0.15, 2.0, max(2, int(w / 6)))
        if style == 'tavern':
            b.box((x, y, z + h - 0.18), (w + 0.5, d + 0.5, 0.5), 'wood_dark', yaw)
        else:
            # A stepped plaster cornice under the eaves.
            b.box((x, y, z + h - 0.30), (w + 0.30, d + 0.30, 0.28), 'cream' if wall != 'cream' else 'stone_light', yaw)
            b.box((x, y, z + h - 0.08), (w + 0.55, d + 0.55, 0.22), 'stone_light', yaw)
        # Jettied upper floors on timber brackets, as on the paintings' rum row.
        jet = 0.0
        if style in ('house', 'tavern', 'shop') and floors >= 2 and rng.random() < 0.42:
            jet = rng.uniform(0.55, 0.9)
            z1 = z + 2.0 + (h - 2.2) / max(1, floors) - 0.55
            jx, jy = local(x, y, yaw, 0, -d / 2 - jet / 2)
            b.box((jx, jy, (z1 + z + h - 0.3) / 2), (w + 0.1, jet + 0.02, z + h - 0.3 - z1), wall, yaw)
            b.box((jx, jy, z1 - 0.12), (w + 0.3, jet + 0.3, 0.26), 'wood_dark', yaw)
            for k in range(max(3, int(w / 2.6)) + 1):
                lx = -w / 2 + 0.3 + (w - 0.6) * k / max(3, int(w / 2.6))
                a0 = local(x, y, yaw, lx, -d / 2 - 0.02)
                a1 = local(x, y, yaw, lx, -d / 2 - jet + 0.1)
                b.beam((a0[0], a0[1], z1 - 1.1), (a1[0], a1[1], z1 - 0.2), 0.14, 'wood_dark')
        # Patches where the plaster has fallen away show the rubble stone underneath.
        if style in ('house', 'tavern', 'shop') and rng.random() < 0.5:
            for _ in range(rng.randint(1, 3)):
                lx = rng.uniform(-w * 0.4, w * 0.4)
                pz = z + rng.uniform(1.4, max(1.6, h - 2.5))
                pw, ph = rng.uniform(0.9, 2.2), rng.uniform(0.6, 1.5)
                ly = -d / 2 - (jet if pz > z + 2.0 + (h - 2.2) / max(1, floors) - 0.55 else 0.0) - 0.04
                px, py = local(x, y, yaw, lx, ly)
                b.box((px, py, pz), (pw, 0.06, ph), 'stone', yaw)
        # An outside stone stair up the side wall to a first-floor door.
        if style == 'house' and floors >= 2 and rng.random() < 0.3:
            side = rng.choice((-1, 1))
            top_z = z + 2.0 + (h - 2.2) / max(1, floors) - 0.4
            steps = int((top_z - z) / 0.28)
            for k in range(steps):
                ly = -d / 2 + 0.6 + k * min(0.34, (d - 1.2) / steps)
                px, py = local(x, y, yaw, side * (w / 2 + 0.75), ly)
                rise = (k + 1) * (top_z - z) / steps
                b.box((px, py, z + rise / 2), (1.4, 0.4, rise), 'stone_light', yaw)
            px, py = local(x, y, yaw, side * (w / 2 + 0.06), -d / 2 + 0.6 + steps * min(0.34, (d - 1.2) / steps))
            b.box((px, py, top_z + 1.1), (0.16, 1.1, 2.1), 'shutter_teal', yaw)
        # Front door, windows, awnings and gallery.
        door(b, x, y, yaw, rng.choice((-w * 0.28, 0.0, w * 0.28)), -d / 2 - 0.10, z + 0.02,
             w=1.5 if style != 'shack' else 1.2, h=2.4 if style != 'shack' else 2.1,
             surround=style in ('house', 'shop') and detail.random() < 0.6)
        if style != 'shack' and rng.random() < 0.55:
            plx = rng.choice((-w * 0.36, w * 0.36))
            px, py = local(x, y, yaw, plx, -d / 2 - 0.75)
            potted_plant(b, px, py, z + 0.05, rng.uniform(0.45, 0.70))
        if style == 'tavern' and rng.random() < 0.5:
            px, py = local(x, y, yaw, rng.uniform(-w * 0.3, w * 0.3), -d / 2 - 1.7)
            bench(b, px, py, z + 0.05, yaw)
        face_x, face_y = local(x, y, yaw, 0, -d / 2)
        cols = max(2, int(w / 4.4))
        for f in range(floors):
            zz = z + 2.0 + f * (h - 2.2) / max(1, floors)
            for i in range(cols):
                lx = -w / 2 + w * (i + 0.5) / cols
                if f == 0 and abs(lx) < 2.2:
                    continue
                fj = jet if f > 0 else 0.0
                window(b, x, y, yaw, lx, -d / 2 - 0.05 - fj, zz, 1.1, 1.8 if f else 1.6,
                       shutters=style != 'shack', warm=(rng.random() < 0.18), trim=trim,
                       lintel=lintels and f > 0)
                if f > 0 and rng.random() < 0.42:
                    flower_box(b, x, y, yaw, lx, -d / 2 - 0.42 - fj, zz - 0.18)
                elif f == 0 and style in ('shop', 'tavern') and rng.random() < 0.30:
                    flower_box(b, x, y, yaw, lx, -d / 2 - 0.42, zz - 0.18)
                if f > 0 and rng.random() < 0.24:
                    pair = (('canvas', 'canvas_red'), ('canvas', 'canvas_teal'),
                            ('canvas_red', 'canvas'), ('canvas_teal', 'canvas'))
                    awning(b, *local(x, y, yaw, lx, -d / 2 - fj + 1.0), yaw, 2.4, zz + 1.85, 1.95,
                           pair[int(abs(lx)) % len(pair)], poles=False)
            for side in (-1, 1):
                side_window(b, x, y, yaw, side * (w / 2 + 0.04), -d * 0.24, zz,
                            1.05, 1.35, shutters=style != 'shack', warm=(rng.random() < 0.14), trim=trim)
                if d > 19.0:
                    side_window(b, x, y, yaw, side * (w / 2 + 0.04), d * 0.22, zz,
                                1.05, 1.35, shutters=style != 'shack', warm=(rng.random() < 0.14), trim=trim)
            if f == 1 and style in ('tavern', 'shop', 'house') and (style == 'tavern' or rng.random() < 0.70):
                by = z + min(h - 1.2, max(5.0, h * 0.52))
                balcony(b, face_x, face_y, yaw, w * 0.78, by)
                if rng.random() < 0.6:
                    for k in range(3):
                        px, py = local(x, y, yaw, -w * 0.22 + k * w * 0.2, -d / 2 - 2.25)
                        b.panel((px - 0.55, py, by - 0.25), (px + 0.55, py, by - 0.25),
                                (px + 0.55, py + 0.04, by - 2.4), (px - 0.55, py + 0.04, by - 2.4),
                                ('canvas', 'canvas_red', 'canvas_teal')[k], thick=0.04)
            if f == 0 and style in ('shop', 'tavern', 'house') and not has_arcade and rng.random() < 0.82:
                pair = (('canvas', 'canvas_red'), ('canvas', 'canvas_teal'),
                        ('canvas_red', 'canvas'), ('canvas_teal', 'canvas'))
                awning(b, face_x, face_y, yaw, w * 0.78, z + 3.3, 2.2,
                       pair[int(abs(x + y)) % len(pair)])
        # Dressed stone quoins on the street corners.
        if style in ('tavern', 'house', 'shop'):
            for side in (-1, 1):
                for k in range(int((h - 1.4) / 0.85)):
                    long = k % 2 == 0
                    qz = z + 1.75 + k * 0.85
                    qx, qy = local(x, y, yaw, side * (w / 2 - (0.3 if long else 0.2)), -d / 2 - 0.04)
                    b.box((qx, qy, qz), (0.7 if long else 0.45, 0.14, 0.62), 'stone_light', yaw)
                    # The returning face round the street corner, alternating long and short with the front.
                    qx, qy = local(x, y, yaw, side * (w / 2 + 0.04), -d / 2 + (0.2 if long else 0.3))
                    b.box((qx, qy, qz), (0.14, 0.45 if long else 0.7, 0.62), 'stone_light', yaw)
        if rng.random() < 0.42:
            lx = rng.choice((-1, 1)) * rng.uniform(w * 0.18, w * 0.42)
            bougainvillea(b, x, y, yaw, lx, -d / 2 - 0.2, z + 1.2, z + h - 0.3, rng)
        # Bougainvillea and creepers break up the flat plaster and tie the
        # dressed waterfront to the jungle above it.
        if rng.random() < 0.34:
            for _ in range(rng.randint(1, 2)):
                lx = rng.uniform(-w * 0.44, w * 0.44)
                px, py = local(x, y, yaw, lx, -d / 2 - 0.16)
                vine(b, px, py, z + h - 0.4, rng.uniform(2.4, 6.2), rng)
    # A lookout tower (mirador) on some tall houses and taverns breaks the roofline, as in the paintings.
    if style in ('house', 'tavern') and h > 8.0 and w >= 9.0 and rng.random() < 0.24:
        side = rng.choice((-1, 1))
        tw = min(4.2, w * 0.32)
        tx, ty = local(x, y, yaw, side * (w / 2 - tw / 2 - 0.2), d * 0.12)
        th = h + rng.uniform(3.2, 4.8)
        twall = rng.choice(('cream', 'ochre', 'yellow_wall', 'rose_wall', wall))
        b.box((tx, ty, z + th / 2), (tw, tw, th), twall, yaw)
        b.box((tx, ty, z + th - 0.1), (tw + 0.45, tw + 0.45, 0.24), 'stone_light', yaw)
        for k in range(3):
            # Arched openings of the belvedere: dark voids with cream frames.
            ox, oy = local(tx, ty, yaw, (k - 1) * tw * 0.3, -tw / 2 - 0.04)
            b.box((ox, oy, z + th - 1.5), (tw * 0.2, 0.1, 1.7), 'glass', yaw)
            b.box((ox, oy, z + th - 0.6), (tw * 0.26, 0.12, 0.18), 'cream', yaw)
        b.hip_roof((tx, ty, z + th), tw, tw, z + th, tw * 0.5, roof, yaw, overhang=0.6)
    # Roof chooses a flat terrace, gable or hip silhouette.
    flat_roof = style not in ('warehouse', 'shack') and h > 9.0 and rng.random() < 0.14
    if flat_roof:
        b.box((x, y, z + h + 0.28), (w + 0.55, d + 0.55, 0.55), 'stone', yaw)
        for sx in (-1, 1):
            px, py = local(x, y, yaw, sx * (w / 2 + 0.1), 0)
            b.box((px, py, z + h + 0.95), (0.45, d + 0.5, 0.9), 'stone_light', yaw)
        for sy in (-1, 1):
            px, py = local(x, y, yaw, 0, sy * (d / 2 + 0.1))
            b.box((px, py, z + h + 0.95), (w + 0.5, 0.45, 0.9), 'stone_light', yaw)
        for k in range(2):
            px, py = local(x, y, yaw, -w * 0.25 + k * w * 0.5, -d * 0.18)
            b.cylinder((px, py, z + h + 0.6), (px, py, z + h + 1.4), 0.55, 'clay', 8, radius_b=0.45)
            palm(b, px, py, z + h + 1.3, 0, 0.30, rng)
    elif style == 'warehouse':
        b.gable_roof((x, y, z + h), w, d, z + h, min(4.2, w * 0.13), roof, yaw, ridge='x', overhang=1.0, gable=wall)
    elif style == 'shack':
        b.gable_roof((x, y, z + h), w, d, z + h, 2.4, roof, yaw, ridge='y', overhang=0.9, gable=wall)
    elif rng.random() < 0.45:
        # About 30 degrees across the short span, with deep eaves, as in the paintings.
        ridge = 'y' if rng.random() < 0.5 else 'x'
        span = (w if ridge == 'y' else d) / 2
        rise = min(6.5, max(2.6, span * 0.58))
        b.gable_roof((x, y, z + h), w, d, z + h, rise, roof, yaw, ridge=ridge, overhang=1.2, gable=wall)
        rafter_tails(b, x, y, yaw, w, d, z + h, 'x' if ridge == 'x' else 'y', b.roof_pitch(w, d, rise, 1.2, ridge))
    else:
        rise = min(6.0, max(2.6, min(w, d) * 0.29))
        b.hip_roof((x, y, z + h), w, d, z + h, rise, roof, yaw, overhang=1.2)
        pitch = b.roof_pitch(w, d, rise, 1.2, hip=True)
        rafter_tails(b, x, y, yaw, w, d, z + h, 'x', pitch)
        rafter_tails(b, x, y, yaw, w, d, z + h, 'y', pitch)
    if not flat_roof and style != 'warehouse' and h > 9.5 and rng.random() < 0.72:
        dormer(b, x, y, yaw, rng.choice((-w * 0.22, 0.0, w * 0.22)), -d * 0.10,
               z + h + 0.35, roof)
    # Chimneys, roof vents, and a bracket sign on roughly every third building.
    if style != 'warehouse' and rng.random() < 0.75:
        side = rng.choice((-1, 1))
        px, py = local(x, y, yaw, side * w * 0.25, d * 0.10)
        b.box((px, py, z + h + 2.1), (0.9, 0.9, 2.8), 'stone', yaw)
        b.box((px, py, z + h + 3.55), (1.2, 1.2, 0.25), 'stone_dark', yaw)
        for off in ((0.0,), (-0.21, 0.21), (-0.21, 0.21))[detail.randrange(3)]:
            ox, oy = local(px, py, yaw, off, 0.0)
            b.cylinder((ox, oy, z + h + 3.66), (ox, oy, z + h + 4.25), 0.17, 'clay', 6, radius_b=0.13)
    if style in ('tavern', 'shop') and rng.random() < 0.9:
        sign(b, face_x, face_y, yaw, z + 2.8, side=rng.choice((-1, 1)),
             icon=rng.choice(('fish', 'mug', 'wheel', 'fish')))
    if style in ('tavern', 'shop', 'house') and rng.random() < 0.45:
        lx = rng.choice((-w * 0.38, w * 0.38))
        px, py = local(x, y, yaw, lx, -d / 2 - 0.35)
        b.beam((px, py, z + 4.05), (px, py, z + 3.65), 0.05, 'metal')
        b.box((px, py, z + 3.48), (0.36, 0.36, 0.48), 'lantern', yaw)
    # Barrels and crates against the facade make the street feel occupied.
    if style in ('tavern', 'shop', 'house') and rng.random() < 0.55:
        for _ in range(rng.randint(1, 3)):
            lx = rng.uniform(-w * 0.42, w * 0.42)
            px, py = local(x, y, yaw, lx, -d / 2 - rng.uniform(0.8, 1.8))
            barrel(b, px, py, z, rng.uniform(0.75, 1.0))


def rafter_tails(b, x, y, yaw, w, d, top, eaves, pitch=0.0):
    """Exposed rafter ends under a deep eave: 'x' runs them along the front and back walls, 'y' along the sides.

    They hang just under the soffit and fall with the roof's pitch, so none pokes through the slope.
    """
    length = w if eaves == 'x' else d
    half = (d if eaves == 'x' else w) / 2
    n = max(3, int(length / 1.3))
    for face in (-1, 1):
        for k in range(n + 1):
            t = -length / 2 + 0.25 + (length - 0.5) * k / n
            if eaves == 'x':
                a, c = local(x, y, yaw, t, face * (half - 0.1)), local(x, y, yaw, t, face * (half + 1.05))
            else:
                a, c = local(x, y, yaw, face * (half - 0.1), t), local(x, y, yaw, face * (half + 1.05), t)
            b.beam((a[0], a[1], top - 0.09 + pitch * 0.1), (c[0], c[1], top - 0.09 - pitch * 1.05), 0.12, 'wood_dark', 0.18)


def bougainvillea(b, x, y, yaw, lx, ly, z0, z1, rng):
    """A flowering creeper falling from the eaves: leaf cards flat to the wall and clusters of pink bracts."""
    height = z1 - z0
    for _ in range(int(10 + height * 2.2)):
        t = rng.random() ** 0.6
        spread = 0.6 + 1.6 * (1 - t)
        px, py = local(x, y, yaw, lx + rng.uniform(-spread, spread), ly - rng.uniform(0.0, 0.35))
        pz = z1 - height * (1 - t) * rng.uniform(0.6, 1.0)
        nx, ny = local(0, 0, yaw, rng.uniform(-0.3, 0.3), -1.0)
        size = rng.uniform(0.8, 1.3)
        b.card((px, py, pz), (nx, ny, rng.uniform(-0.2, 0.5)), size, size,
               ('leaf_mid', 'leaf_light', 'leaf_deep')[rng.randrange(3)], cell_uvs(rng.randrange(4)))
        if rng.random() < 0.7:
            # Bracts sit on their leaf card, just proud of it along its normal; a fixed -y offset floated them off
            # every wall not facing -y (playtest note 14).
            ox, oy = local(0, 0, yaw, rng.uniform(-0.25, 0.25), 0.0)
            b.sphere((px + ox + nx * 0.1, py + oy + ny * 0.1, pz + rng.uniform(-0.25, 0.25)), rng.uniform(0.16, 0.26),
                     SurfaceKey(('blossom','blossom_pale','blossom')[rng.randrange(3)],'flower'), (1.0, 0.6, 1.0), subdiv=1)


def barrel(b, x, y, z, s=1.0):
    b.cylinder((x, y, z), (x, y, z + 1.05 * s), 0.42 * s, 'wood', 9, radius_b=0.36 * s)
    for zz in (0.18, 0.55, 0.9):
        b.cylinder((x, y, z + zz * s), (x, y, z + (zz + 0.04) * s), 0.44 * s, 'metal', 9)


def crate(b, x, y, z, size=0.9, yaw=0.0):
    b.box((x, y, z + size / 2), (size, size * 0.9, size), 'wood_light', yaw)
    for dz in (0.16, size - 0.16):
        b.box((x, y, z + dz), (size + 0.04, size * 0.9 + 0.04, 0.08), 'wood_dark', yaw)


def lantern_post(b, x, y, z, height=3.2, yaw=0.0):
    b.cylinder((x, y, z), (x, y, z + height), 0.09, 'metal', 6)
    b.box((x, y, z + height + 0.28), (0.46, 0.46, 0.56), 'lantern', yaw)
    b.box((x, y, z + height + 0.62), (0.58, 0.58, 0.10), 'metal', yaw)


def bollard(b, x, y, z):
    b.cylinder((x, y, z), (x, y, z + 0.9), 0.28, 'metal', 8, radius_b=0.22)
    b.cylinder((x, y, z + 0.88), (x, y, z + 1.02), 0.38, 'metal', 8)


def rng_choice_stripe(x, y):
    return ('canvas_red', 'canvas_teal', 'canvas_gold', 'canvas_blue')[int(abs(x * 1.7 + y * 2.9)) % 4]


def market_stall(b, x, y, z, w=10, d=6, cloth='canvas', yaw=0.0):
    """A working market stall after the Sunburst stall concept (references/redesign/market-stall.jpg).

    Rope-bound posts carry plates front and back and a mono-pitch of rafters; the striped canvas is a two-sided
    sheet on the rafters with a scalloped valance, so it reads solid from underneath (playtest note 10). Every ware
    rests on the counter, a back-wall shelf or the ground, or hangs from the front plate on a cord, so nothing
    floats (note 9).
    """
    def P(lx, ly, lz):
        px, py = local(x, y, yaw, lx, ly)
        return (px, py, z + lz)

    rng = random.Random(int(x * 31 + y * 17))
    stripe = 'canvas' if cloth != 'canvas' else rng_choice_stripe(x, y)
    hx, hy = w / 2 - 0.2, d / 2 - 0.2
    front, back = 2.95, 3.4

    def eave(ly):
        # Underside height of the mono-pitch canopy across the stall.
        return front + (back - front) * (ly + hy) / (2 * hy)

    # Frame: rope-bound posts on stone pads, plates front and back, side ties, rafters and corner braces.
    for sx in (-hx, hx):
        for sy in (-hy, hy):
            top = eave(sy)
            b.beam(P(sx, sy, 0), P(sx, sy, top + 0.1), 0.2, 'wood_dark')
            b.box(P(sx, sy, 0.06), (0.36, 0.36, 0.12), 'stone', yaw)
            for rz in (0.95, top - 0.75):
                b.cylinder(P(sx, sy, rz), P(sx, sy, rz + 0.16), 0.15, 'rope', 8)
            b.beam(P(sx, sy, top - 0.7), P(sx - math.copysign(0.7, sx), sy, top), 0.1, 'wood_dark')
        b.beam(P(sx, -hy, front), P(sx, hy, back), 0.18, 'wood_dark')
    for sy in (-hy, hy):
        b.beam(P(-hx - 0.3, sy, eave(sy) + 0.04), P(hx + 0.3, sy, eave(sy) + 0.04), 0.2, 'wood_dark')
    bays = max(3, round(w / 1.4))
    run = 0.6
    for i in range(bays + 1):
        lx = -hx + 2 * hx * i / bays
        b.beam(P(lx, hy + run, eave(hy + run) + 0.12), P(lx, -hy - run, eave(-hy - run) + 0.12), 0.09, 'wood', 0.12)
    # Canopy: striped two-sided cloth on the rafters, a scalloped valance on the front and both sides.
    lo, hi = eave(-hy - run) + 0.24, eave(hy + run) + 0.24
    strips = max(6, round(w / 1.1))
    for i in range(strips):
        x0 = -hx - 0.45 + (2 * hx + 0.9) * i / strips
        x1 = -hx - 0.45 + (2 * hx + 0.9) * (i + 1) / strips
        mat = cloth if i % 2 == 0 else stripe
        b.panel(P(x0, -hy - run, lo), P(x1, -hy - run, lo), P(x1, hy + run, hi), P(x0, hy + run, hi), mat, thick=0.05)
        for k, (u0, u1) in enumerate(((0.0, 0.5), (0.5, 1.0))):
            xa, xb = x0 + (x1 - x0) * u0, x0 + (x1 - x0) * u1
            drop = 0.5 if k == 0 else 0.36
            b.panel(P(xa, -hy - run, lo), P(xb, -hy - run, lo), P(xb, -hy - run, lo - drop),
                    P(xa, -hy - run, lo - drop), mat, thick=0.04)
    for sx in (-1, 1):
        sides = max(4, round(2 * (hy + run) / 0.6))
        for k in range(sides):
            y0 = -hy - run + 2 * (hy + run) * k / sides
            y1 = -hy - run + 2 * (hy + run) * (k + 1) / sides
            z0, z1 = eave(y0) + 0.24, eave(y1) + 0.24
            drop = 0.42 if k % 2 == 0 else 0.3
            b.panel(P(sx * (hx + 0.45), y0, z0), P(sx * (hx + 0.45), y1, z1), P(sx * (hx + 0.45), y1, z1 - drop),
                    P(sx * (hx + 0.45), y0, z0 - drop), cloth if k % 2 == 0 else stripe, thick=0.04)
    # A planked back wall with two shelves.
    b.box(P(0, hy - 0.02, eave(hy) / 2), (2 * hx - 0.2, 0.1, eave(hy)), 'planks', yaw)
    shelves = (1.55, 2.25)
    for sz in shelves:
        b.box(P(0, hy - 0.27, sz - 0.03), (2 * hx - 0.4, 0.42, 0.06), 'wood_light', yaw)
        for lx in (-hx + 0.5, hx - 0.5):
            b.beam(P(lx, hy - 0.07, sz - 0.4), P(lx, hy - 0.4, sz - 0.07), 0.06, 'wood_dark')
    # Counter with front boards and a lower shelf, and a stepped display behind it.
    top = 0.95
    b.box(P(0, -hy + 0.75, top - 0.06), (w - 0.5, 1.3, 0.12), 'wood_light', yaw)
    b.box(P(0, -hy + 0.16, (top - 0.12) / 2), (w - 0.6, 0.12, top - 0.12), 'planks', yaw)
    b.box(P(0, -hy + 0.16 - 0.07, 0.5), (w - 0.8, 0.04, 0.5), cloth, yaw)
    b.box(P(0, -hy + 0.8, 0.3), (w - 0.8, 1.0, 0.08), 'wood', yaw)
    for lx in (-hx + 0.4, 0.0, hx - 0.4):
        b.box(P(lx, -hy + 0.75, (top - 0.12) / 2), (0.14, 1.1, top - 0.12), 'wood', yaw)
    # Wares: crates of fruit, a basket of fish and jars on the counter; bottles and cloth bolts on the steps.
    n = max(3, int(w / 1.5))
    for i in range(n):
        lx = -hx + 0.8 + (2 * hx - 1.6) * i / max(1, n - 1)
        kind = (i + int(abs(x))) % 4
        cx, cy, cz = P(lx, -hy + 0.75, top)
        if kind == 0:
            crate(b, cx, cy, cz, 0.6, yaw + rng.uniform(-6, 6))
            fruit = rng.choice(('gold', 'coral', SurfaceKey('leaf_sun','rigid'), 'shutter_red', 'ochre'))
            for k in range(5):
                px, py = local(cx, cy, yaw, (k % 3 - 1) * 0.17, (k // 3 - 0.5) * 0.18)
                b.sphere((px, py, cz + 0.6 + 0.05), 0.1, fruit, subdiv=1)
        elif kind == 1:
            b.cylinder((cx, cy, cz), (cx, cy, cz + 0.22), 0.3, 'wood_light', 10, radius_b=0.38)
            for k in range(4):
                px, py = local(cx, cy, yaw, -0.2 + k * 0.13, 0)
                b.sphere((px, py, cz + 0.22 + 0.05), 0.11, 'sail', (1.8, 0.5, 0.45), subdiv=1)
        elif kind == 2:
            for k in range(3):
                px, py = local(cx, cy, yaw, (k - 1) * 0.32, 0)
                h = 0.38 + 0.1 * (k % 2)
                b.cylinder((px, py, cz), (px, py, cz + h * 0.65), 0.1, 'clay', 8, radius_b=0.15)
                b.cylinder((px, py, cz + h * 0.65), (px, py, cz + h), 0.15, 'clay', 8, radius_b=0.06)
        else:
            b.box((cx, cy, cz + 0.14), (0.7, 0.45, 0.28), 'wood_light', yaw)
            for k in range(3):
                px, py = local(cx, cy, yaw, (k - 1) * 0.2, 0)
                b.sphere((px, py, cz + 0.28 + 0.08), 0.1, rng.choice(('sage_wall', 'gold', 'coral')), subdiv=1)
    for j, sz in enumerate(shelves):
        for i in range(n + 1):
            lx = -hx + 0.6 + (2 * hx - 1.2) * i / max(1, n)
            px, py, pz = P(lx, hy - 0.27, sz)
            kind = (i + j) % 3
            if kind == 0:
                b.cylinder((px, py, pz), (px, py, pz + 0.3), 0.08, ('glass_warm', 'teal_wall', 'clay')[i % 3], 7,
                           radius_b=0.05)
            elif kind == 1:
                b.cylinder((px, py, pz), (px, py, pz + 0.22), 0.16, 'wood_light', 9, radius_b=0.2)
            else:
                b.box((px, py, pz + 0.12), (0.42, 0.3, 0.24), 'wood', yaw)
    # Hung from the front plate on cords: strings of dried fish and garlic, and a lantern at each front post.
    plate = eave(-hy) - 0.06
    for i in range(4):
        lx = -hx + 0.7 + (2 * hx - 1.4) * i / 3
        cord = 0.3 + 0.1 * (i % 2)
        b.beam(P(lx, -hy, plate), P(lx, -hy, plate - cord), 0.025, 'rope')
        if i % 2:
            for k in range(3):
                b.sphere(P(lx, -hy, plate - cord - 0.11 - k * 0.2), 0.11, 'cream', (0.9, 0.9, 1.1), subdiv=1)
        else:
            b.sphere(P(lx, -hy, plate - cord - 0.28), 0.28, 'sail', (0.45, 0.25, 1.0), subdiv=1)
    for sx in (-1, 1):
        b.beam(P(sx * hx, -hy, plate - 0.25), P(sx * (hx + 0.45), -hy, plate - 0.25), 0.06, 'metal')
        b.beam(P(sx * (hx + 0.45), -hy, plate - 0.25), P(sx * (hx + 0.45), -hy, plate - 0.45), 0.03, 'metal')
        b.box(P(sx * (hx + 0.45), -hy, plate - 0.66), (0.3, 0.3, 0.42), 'lantern', yaw)
    # On the ground: crates, a fish crate, sacks and a barrel at the ends.
    px, py, pz = P(-hx + 0.6, -hy - 0.7, 0)
    fish_crate(b, px, py, pz, yaw + 6, 0.9)
    px, py, pz = P(hx - 0.5, -hy - 0.6, 0)
    crate(b, px, py, pz, 0.75, yaw - 8)
    crate(b, px, py, pz + 0.75, 0.6, yaw + 14)
    px, py, pz = P(-hx - 0.6, 0.4, 0)
    sack(b, px, py, pz, 0.8)
    px, py, pz = P(hx + 0.65, 0.6, 0)
    barrel(b, px, py, pz, 0.8)


def parasol(b, x, y, z, radius=2.6, colors=('canvas', 'canvas_red'), rng=None):
    """A market parasol: a pole and an eight-panel cone in alternating cloth, with a little table under it."""
    top = z + 3.1
    b.beam((x, y, z), (x, y, top + 0.5), 0.09, 'wood_dark')
    panels = 8
    for i in range(panels):
        a0 = TAU * i / panels
        a1 = TAU * (i + 1) / panels
        p0 = (x + math.cos(a0) * radius, y + math.sin(a0) * radius, top - 0.45)
        p1 = (x + math.cos(a1) * radius, y + math.sin(a1) * radius, top - 0.45)
        b.tri(p0, p1, (x, y, top + 0.45), colors[i % len(colors)])
        b.tri(p1, p0, (x, y, top + 0.45), colors[i % len(colors)])
    b.cylinder((x, y, z + 0.75), (x, y, z + 0.82), 0.7, 'wood_light', 8)


def goods(b, x, y, z, yaw=0.0, rng=None):
    """A vendor's spread: produce in crates, clay jars, a rope coil or a stack of fish, at counter height or below."""
    rng = rng or random.Random(int(x * 13 + y * 7))
    kind = rng.random()
    if kind < 0.35:
        for k in range(rng.randint(2, 4)):
            lx = (k - 1.5) * 0.8
            px, py = local(x, y, yaw, lx, rng.uniform(-0.2, 0.2))
            crate(b, px, py, z, 0.7, yaw + rng.uniform(-8, 8))
            fruit = rng.choice(('gold', 'coral', SurfaceKey('leaf_sun','rigid'), 'shutter_red', 'ochre', 'cream'))
            for _ in range(5):
                b.sphere((px + rng.uniform(-0.22, 0.22), py + rng.uniform(-0.22, 0.22), z + 0.72),
                         rng.uniform(0.1, 0.15), fruit, subdiv=0)
    elif kind < 0.6:
        for _ in range(rng.randint(3, 6)):
            px, py = x + rng.uniform(-1.2, 1.2), y + rng.uniform(-0.8, 0.8)
            h = rng.uniform(0.45, 0.8)
            r = h * rng.uniform(0.35, 0.5)
            b.cylinder((px, py, z), (px, py, z + h * 0.65), r * 0.7, 'clay', 8, radius_b=r)
            b.cylinder((px, py, z + h * 0.65), (px, py, z + h), r, 'clay', 8, radius_b=r * 0.45)
    elif kind < 0.78:
        b.ring((x, y, z + 0.1), 0.45, 0.09, 'rope', sides=10)
        b.ring((x, y, z + 0.24), 0.38, 0.09, 'rope', sides=10)
        barrel(b, x + 1.0, y + 0.3, z, 0.7)
        sack(b, x - 1.0, y + 0.2, z, 0.8)
    else:
        fish_crate(b, x, y, z, yaw, 1.0)
        sack(b, x + 1.1, y + 0.4, z, 0.8)
        barrel(b, x - 1.1, y + 0.2, z, 0.7)


def laundry_line(b, a, c, sag=0.35, colors=('canvas', 'canvas_red', 'canvas_teal')):
    """A rope with three flat cloth panels; cheap and reads at street distance."""
    b.rope(a, c, sag, 0.03, segments=6)
    for i in range(3):
        t = (i + 0.5) / 3
        px = a[0] + (c[0] - a[0]) * t
        py = a[1] + (c[1] - a[1]) * t
        pz = a[2] + (c[2] - a[2]) * t - sag * math.sin(math.pi * t)
        b.box((px, py, pz - 0.48), (0.62 + 0.10 * (i % 2), 0.035, 0.95 + 0.15 * (i % 2)),
              colors[i % len(colors)])


def pennants(b, a, c, sag=0.5, count=9, colors=('flag_red', 'cream', 'canvas_teal', 'gold')):
    """A sagging rope of small square flags across a street or the market."""
    b.rope(a, c, sag, 0.035, segments=8)
    for i in range(count):
        t = (i + 0.5) / count
        px = a[0] + (c[0] - a[0]) * t
        py = a[1] + (c[1] - a[1]) * t
        pz = a[2] + (c[2] - a[2]) * t - sag * math.sin(math.pi * t)
        b.box((px, py, pz - 0.24), (0.42, 0.03, 0.46), colors[i % len(colors)])


def fish_crate(b, x, y, z, yaw=0.0, scale=1.0):
    b.box((x, y, z + 0.24 * scale), (1.35 * scale, 0.85 * scale, 0.48 * scale),
          'wood_light', yaw)
    for i in range(4):
        px, py = local(x, y, yaw, -0.42 * scale + i * 0.28 * scale, 0)
        b.sphere((px, py, z + 0.54 * scale), 0.16 * scale, 'sail',
                 (1.9, 0.55, 0.45), subdiv=0)


def rowboat(b, x, y, z, yaw=0.0, scale=1.0):
    def P(lx, ly, lz):
        px, py = local(x, y, yaw, lx * scale, ly * scale)
        return (px, py, z + lz * scale)

    b.panel(P(-0.75, -2.4, 0.12), P(0.75, -2.4, 0.12), P(0.75, 2.4, 0.12), P(-0.75, 2.4, 0.12),
            'wood_dark', thick=0.04)
    b.panel(P(-0.75, -2.4, 0.12), P(-0.75, 2.4, 0.12), P(-1.05, 2.6, 0.55), P(-1.05, -2.6, 0.55),
            'wood', thick=0.04)
    b.panel(P(0.75, -2.4, 0.12), P(1.05, -2.6, 0.55), P(1.05, 2.6, 0.55), P(0.75, 2.4, 0.12),
            'wood', thick=0.04)
    b.tri(P(-0.75, 2.4, 0.12), P(0.75, 2.4, 0.12), P(0, 3.0, 0.55), 'wood_light')
    b.tri(P(-0.75, -2.4, 0.12), P(0, -3.0, 0.55), P(0.75, -2.4, 0.12), 'wood_light')
    for side in (-1, 1):
        b.beam(P(side * 1.05, -2.6, 0.55), P(side * 1.05, 2.6, 0.55), 0.08, 'wood_dark')
    for ly in (-1.0, 0.6):
        b.beam(P(-1.0, ly, 0.50), P(1.0, ly, 0.50), 0.10, 'wood_light')
    b.beam(P(-0.6, 0.2, 0.62), P(-1.8, -1.4, 0.20), 0.05, 'wood_light')
    b.beam(P(0.6, 0.2, 0.62), P(1.8, -1.4, 0.20), 0.05, 'wood_light')


def sack(b, x, y, z, scale=1.0):
    b.sphere((x, y, z + 0.44 * scale), 0.52 * scale, 'canvas', (0.85, 0.85, 1.15), subdiv=0)
    b.cylinder((x, y, z + 0.85 * scale), (x, y, z + 1.0 * scale), 0.13 * scale, 'cream', 6)


def potted_plant(b, x, y, z, scale=1.0, rng=None):
    b.cylinder((x, y, z), (x, y, z + 0.55 * scale), 0.44 * scale, 'clay', 8,
               radius_b=0.32 * scale)
    bush(b, x, y, z + 0.52 * scale, 0.0, 0.62 * scale, rng)


def bench(b, x, y, z, yaw=0.0):
    b.box((x, y, z + 0.46), (2.1, 0.60, 0.13), 'wood_light', yaw)
    for side in (-1, 1):
        px, py = local(x, y, yaw, side * 0.82, 0)
        b.beam((px, py, z), (px, py, z + 0.46), 0.13, 'wood_dark')
        px, py = local(x, y, yaw, side * 0.82, 0.24)
        b.beam((px, py, z + 0.46), (px, py, z + 0.95), 0.11, 'wood_dark')
    b.box((x, y, z + 0.88), (2.1, 0.12, 0.34), 'wood', yaw)



def leaf_canopy(b, center, radii, count, size, rng, warm=0.15):
    """A cloud of small alpha leaf cards, dense on the shell and darker inside."""
    cx, cy, cz = center
    rx, ry, rz = radii
    for _ in range(count):
        while True:
            p = (rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))
            length = math.sqrt(p[0] * p[0] + p[1] * p[1] + p[2] * p[2])
            if length <= 1.0:
                break
        if length < 0.55 and rng.random() < 0.45:
            scale = rng.uniform(0.62, 1.0) / max(length, 1e-3)
            p = (p[0] * scale, p[1] * scale, p[2] * scale)
            length = 1.0
        pos = (cx + p[0] * rx, cy + p[1] * ry, cz + p[2] * rz)
        normal = (p[0] + rng.uniform(-0.45, 0.45),
                  p[1] + rng.uniform(-0.45, 0.45),
                  p[2] * 0.75 + rng.uniform(-0.25, 0.85))
        if rng.random() < warm:
            mat = 'leaf_warm'
        elif length < 0.45:
            mat = 'leaf_deep'
        elif length < 0.78:
            mat = 'leaf_mid'
        else:
            mat = 'leaf_light'
        card = size * rng.uniform(0.72, 1.28)
        b.card(pos, normal, card, card * rng.uniform(0.82, 1.05), mat,
               cell_uvs(rng.randrange(4)))


def palm(b, x, y, z, yaw=0.0, scale=1.0, rng=None):
    rng = rng or random.Random(int(x * 13 + y))
    height = (8.0 + rng.random() * 4.0) * scale
    lean = rng.uniform(-1.6, 1.6) * scale
    drift = rng.uniform(-0.8, 0.8) * scale
    top = (x + lean, y + drift, z + height)
    segs = 7
    for i in range(segs):
        t0, t1 = i / segs, (i + 1) / segs
        p0 = (x + lean * t0 ** 1.7, y + drift * t0 * t0, z + height * t0)
        p1 = (x + lean * t1 ** 1.7, y + drift * t1 * t1, z + height * t1)
        b.cylinder(p0, p1, (0.36 - 0.19 * t0) * scale, 'wood', 7,
                   radius_b=(0.36 - 0.19 * t1) * scale, caps=False)
    for i in range(11):
        ang = yaw + i * TAU / 11 + rng.uniform(-0.12, 0.12)
        length = (4.6 + rng.random() * 2.4) * scale
        droop = (1.2 + rng.random() * 0.9) * scale
        direction = (math.cos(ang), math.sin(ang), -droop / length)
        centre = (top[0] + direction[0] * length * 0.52,
                  top[1] + direction[1] * length * 0.52,
                  top[2] + direction[2] * length * 0.52)
        normal = (-math.sin(ang), math.cos(ang), 0.22)
        b.card(centre, normal, 2.6 * scale, length, 'palm_frond',
               cell_uvs(PALM_CELLS[i % len(PALM_CELLS)]), up_hint=direction)
    # A shorter upright crown ring closes the silhouette seen from below.
    for i in range(4):
        ang = yaw + i * TAU / 4 + 0.6
        length = (2.4 + rng.random() * 0.9) * scale
        direction = (math.cos(ang) * 0.55, math.sin(ang) * 0.55, 0.85)
        centre = (top[0] + direction[0] * length * 0.5,
                  top[1] + direction[1] * length * 0.5,
                  top[2] + direction[2] * length * 0.5)
        normal = (-math.sin(ang), math.cos(ang), 0.15)
        b.card(centre, normal, 1.9 * scale, length, 'palm_frond',
               cell_uvs(PALM_CELLS[i % len(PALM_CELLS)]), up_hint=direction)
    for i in range(4):
        a = yaw + i * TAU / 4
        b.sphere((top[0] + math.cos(a) * 0.42, top[1] + math.sin(a) * 0.42, top[2] - 0.18),
                 0.26 * scale, ('wood_dark', 'autumn_olive')[i % 2], subdiv=0)


def jungle_tree(b, x, y, z, yaw=0.0, scale=1.0, rng=None):
    rng = rng or random.Random(int(x * 7 + y * 3))
    height = (6.2 + rng.random() * 5.0) * scale
    lean = rng.uniform(-0.7, 0.7) * scale
    drift = rng.uniform(-0.35, 0.35) * scale
    mid = (x + lean * 0.40, y + drift * 0.35, z + height * 0.55)
    top = (x + lean, y + drift, z + height)
    b.cylinder((x, y, z), mid, 0.52 * scale, 'wood_dark', 8, radius_b=0.36 * scale)
    b.cylinder(mid, top, 0.36 * scale, 'wood_dark', 7, radius_b=0.18 * scale)
    if scale > 1.10:
        for i in range(4):
            ang = yaw + i * TAU / 4 + 0.3
            ex, ey = x + math.cos(ang) * 1.05 * scale, y + math.sin(ang) * 1.05 * scale
            b.beam((x, y, z + 0.18 * scale), (ex, ey, z + 0.02), 0.17 * scale, 'wood_dark')
    fork = (x + lean * 0.32, y + drift * 0.28, z + height * 0.44)
    lobes = []
    for i in range(4):
        ang = yaw + i * TAU / 4 + rng.uniform(-0.22, 0.22)
        length = (3.0 + rng.random() * 2.0) * scale
        end = (x + lean * 0.72 + math.cos(ang) * length,
               y + drift * 0.72 + math.sin(ang) * length,
               z + height * (0.58 + 0.08 * i))
        b.cylinder(fork, end, 0.26 * scale, 'wood_dark', 6,
                   radius_b=0.09 * scale, caps=False)
        radius = (2.25 + rng.random() * 1.0) * scale
        lobes.append(((end[0], end[1], end[2] + 0.55 * scale), radius))
        # A couple of twigs give the canopy a broken edge.
        for k in range(1):
            twig_ang = ang + rng.uniform(-0.9, 0.9)
            twig_len = (1.3 + rng.random() * 0.9) * scale
            twig_end = (end[0] + math.cos(twig_ang) * twig_len,
                        end[1] + math.sin(twig_ang) * twig_len,
                        end[2] + rng.uniform(0.2, 0.9) * scale)
            b.cylinder(end, twig_end, 0.08 * scale, 'wood_dark', 5,
                       radius_b=0.03 * scale, caps=False)
            lobes.append(((twig_end[0], twig_end[1], twig_end[2] + 0.3 * scale),
                          (0.95 + rng.random() * 0.55) * scale))
    lobes.append(((top[0], top[1], top[2] - 0.25 * scale), (2.7 + rng.random() * 0.7) * scale))
    lobes.append(((top[0] - 1.5 * scale, top[1] + 1.05 * scale, top[2] - 0.95 * scale),
                  (1.9 + rng.random() * 0.5) * scale))
    for centre, radius in lobes:
        volume = radius * radius
        count = max(20, int(volume * 3.6))
        leaf_canopy(b, centre, (radius, radius, radius * 0.76), count,
                    (1.00 + rng.random() * 0.35) * scale, rng)
    if scale > 1.25 and rng.random() < 0.28:
        a = rng.uniform(0, TAU)
        vx = top[0] + math.cos(a) * 2.3 * scale
        vy = top[1] + math.sin(a) * 2.3 * scale
        vine(b, vx, vy, top[2] - 0.5 * scale, rng.uniform(1.8, 3.8) * scale, rng)


def bush(b, x, y, z, yaw=0.0, scale=1.0, rng=None):
    rng = rng or random.Random(int(x * 11 + y * 5))
    leaf_canopy(b, (x, y, z + 0.58 * scale), (0.92 * scale, 0.92 * scale, 0.62 * scale),
                max(24, int(42 * scale)), 0.58 * scale, rng, warm=0.10)
    if rng.random() < 0.20:
        for i in range(3):
            b.sphere((x + rng.uniform(-0.5, 0.5) * scale, y + rng.uniform(-0.5, 0.5) * scale,
                      z + (0.75 + rng.uniform(0, 0.3)) * scale), 0.16 * scale,
                     SurfaceKey(('blossom','coral','gold')[i % 3],'flower'), subdiv=0)


def fern(b, x, y, z, yaw=0.0, scale=1.0, rng=None):
    rng = rng or random.Random(int(x * 17 + y * 3))
    for i in range(7):
        ang = yaw + i * TAU / 7 + rng.uniform(-0.2, 0.2)
        length = (1.3 + rng.random() * 1.0) * scale
        tip = (x + math.cos(ang) * length, y + math.sin(ang) * length,
               z + (0.65 + rng.uniform(0, 0.35)) * scale)
        side = (math.cos(ang + math.pi / 2) * 0.22 * scale,
                math.sin(ang + math.pi / 2) * 0.22 * scale, 0)
        b.quad((x, y, z + 0.05), (tip[0] + side[0], tip[1] + side[1], tip[2]),
               tip, (tip[0] - side[0], tip[1] - side[1], tip[2]),
               'cover_fern_light' if i % 2 else 'cover_fern')


def banana(b, x, y, z, yaw=0.0, scale=1.0, rng=None):
    rng = rng or random.Random(int(x * 23 + y * 5))
    height = (1.5 + rng.random() * 0.8) * scale
    top = (x + rng.uniform(-0.2, 0.2), y + rng.uniform(-0.2, 0.2), z + height)
    b.cylinder((x, y, z), top, 0.16 * scale, 'jungle', 6, radius_b=0.11 * scale)
    for i in range(6):
        ang = yaw + i * TAU / 6 + rng.uniform(-0.2, 0.2)
        length = (1.5 + rng.random() * 0.6) * scale
        mid = (top[0] + math.cos(ang) * length * 0.55, top[1] + math.sin(ang) * length * 0.55,
               top[2] + 0.55 * scale)
        tip = (top[0] + math.cos(ang) * length, top[1] + math.sin(ang) * length,
               top[2] + 0.10 * scale)
        side = (math.cos(ang + math.pi / 2) * 0.42 * scale,
                math.sin(ang + math.pi / 2) * 0.42 * scale, 0)
        b.quad(top, (mid[0] + side[0], mid[1] + side[1], mid[2]),
               (tip[0] + side[0] * 0.5, tip[1] + side[1] * 0.5, tip[2]), tip, SurfaceKey('jungle_light','groundcover_leaf'))
        b.quad(top, tip, (tip[0] - side[0] * 0.5, tip[1] - side[1] * 0.5, tip[2]),
               (mid[0] - side[0], mid[1] - side[1], mid[2]), SurfaceKey('jungle','groundcover_leaf'))


def grass_tuft(b, x, y, z, yaw=0.0, scale=1.0, rng=None):
    rng = rng or random.Random(int(x * 31 + y * 7))
    for i in range(3):
        ang = yaw + i * TAU / 3 + rng.uniform(-0.3, 0.3)
        h = (0.55 + rng.random() * 0.45) * scale
        w = 0.28 * scale
        dx, dy = math.cos(ang) * w, math.sin(ang) * w
        b.quad((x - dx, y - dy, z), (x + dx, y + dy, z),
               (x + dx * 0.3, y + dy * 0.3, z + h), (x - dx * 0.3, y - dy * 0.3, z + h),
               'cover_grass_dry' if i % 2 else 'cover_grass')


def person(b, x, y, z, yaw=0.0, scale=1.0, rng=None):
    """A low-poly pirate-town local: legs, a tapered coat or shirt, sash, arms and a hat that reads at distance."""
    rng = rng or random.Random(int(x * 17 + y * 3))
    if rng.random() < 0.10:
        scale *= 0.68
    s = scale
    shirt = rng.choice(('cream', 'canvas', 'cream', 'teal_wall', 'sage_wall', 'azure_wall'))
    coat = rng.choice((None, None, 'flag_black', 'shutter_blue', 'wood_dark', 'shutter_red', 'shutter_teal'))
    trousers = rng.choice(('wood_dark', 'roof_slate', 'stone_dark', 'canvas', 'ochre'))
    sash = rng.choice(('flag_red', 'flag_red', 'gold', 'canvas_teal', 'coral'))
    skirt = rng.random() < 0.3

    def P(lx, ly, lz):
        px, py = local(x, y, yaw, lx * s, ly * s)
        return (px, py, z + lz * s)

    if skirt:
        b.cylinder(P(0, 0, 0.05), P(0, 0, 0.95), 0.36 * s, rng.choice(('shutter_blue', 'coral', 'sage_wall',
                                                                        'wood')), 7, radius_b=0.22 * s)
    else:
        for side in (-1, 1):
            b.beam(P(side * 0.11, 0, 0.0), P(side * 0.12, 0, 0.92), 0.15 * s, trousers)
            b.box(P(side * 0.11, -0.05, 0.05), (0.15 * s, 0.26 * s, 0.1 * s), 'wood_dark', yaw)
    body = coat or shirt
    b.cylinder(P(0, 0, 0.88), P(0, 0, 1.42), 0.25 * s, body, 6, radius_b=0.29 * s)
    if coat and rng.random() < 0.7:
        # Coat tails below the sash.
        b.cylinder(P(0, 0, 0.55), P(0, 0, 0.9), 0.3 * s, coat, 6, radius_b=0.26 * s, caps=False)
        b.box(P(0, -0.22, 1.18), (0.18 * s, 0.06 * s, 0.4 * s), shirt, yaw)
    b.cylinder(P(0, 0, 0.9), P(0, 0, 1.02), 0.275 * s, sash, 6)
    b.box(P(0.18, -0.16, 0.86), (0.08 * s, 0.05 * s, 0.24 * s), sash, yaw)
    reach = rng.random()
    for side in (-1, 1):
        shoulder = P(side * 0.31, 0, 1.36)
        if reach < 0.25 and side > 0:
            hand = P(side * 0.42, -0.25, 1.75)  # waving or hailing a ship
        elif reach < 0.5:
            hand = P(side * 0.24, -0.28, 1.02)  # carrying something in front
        else:
            hand = P(side * 0.36, 0.02, 0.86)
        b.beam(shoulder, hand, 0.1 * s, coat or shirt)
        b.sphere(hand, 0.06 * s, 'skin', subdiv=0)
    b.cylinder(P(0, 0, 1.4), P(0, 0, 1.47), 0.08 * s, 'skin', 5)
    b.sphere(P(0, 0, 1.6), 0.15 * s, 'skin', (1.0, 0.95, 1.1), subdiv=1)
    hat = rng.random()
    if hat < 0.35:
        # Tricorn: a low crown and three upturned brims.
        b.cylinder(P(0, 0, 1.68), P(0, 0, 1.82), 0.16 * s, 'flag_black', 7)
        for k in range(3):
            a = k * TAU / 3 + math.radians(yaw) - math.pi / 2
            ox, oy = math.cos(a) * 0.17 * s, math.sin(a) * 0.17 * s
            c = (P(0, 0, 0)[0] + ox, P(0, 0, 0)[1] + oy, z + 1.73 * s)
            b.quad((c[0] - oy * 1.2, c[1] + ox * 1.2, c[2] - 0.02 * s),
                   (c[0] + oy * 1.2, c[1] - ox * 1.2, c[2] - 0.02 * s),
                   (c[0] + oy * 1.2 + ox * 0.5, c[1] - ox * 1.2 + oy * 0.5, c[2] + 0.12 * s),
                   (c[0] - oy * 1.2 + ox * 0.5, c[1] + ox * 1.2 + oy * 0.5, c[2] + 0.12 * s), 'flag_black')
    elif hat < 0.6:
        b.sphere(P(0, 0, 1.68), 0.16 * s, rng.choice(('flag_red', 'canvas_red', 'canvas_teal', 'gold')),
                 (1.05, 1.05, 0.7), subdiv=0)
        b.beam(P(0, 0.14, 1.66), P(0.05, 0.3, 1.5), 0.06 * s, 'flag_red')
    elif hat < 0.8:
        b.cylinder(P(0, 0, 1.69), P(0, 0, 1.72), 0.34 * s, 'roof_straw', 8)
        b.cylinder(P(0, 0, 1.72), P(0, 0, 1.86), 0.15 * s, 'roof_straw', 7, radius_b=0.12 * s)
    else:
        b.sphere(P(0, 0.02, 1.66), 0.16 * s, rng.choice(('wood_dark', 'stone_dark', 'ochre')), (1.0, 1.05, 0.8),
                 subdiv=0)
    if reach < 0.5 and reach >= 0.25:
        b.box(P(0, -0.4, 1.05), (0.5 * s, 0.34 * s, 0.32 * s), rng.choice(('wood_light', 'wood', 'canvas')), yaw)
    if rng.random() < 0.2:
        b.cylinder(P(0, 0, 1.86), P(0, 0, 2.04), 0.24 * s, 'wood_light', 7)
        b.sphere(P(0, 0, 2.06), 0.2 * s, rng.choice(('gold', 'coral', 'sail')), (1.2, 0.8, 0.7), subdiv=0)


def vine(b, x, y, z, length=8.0, rng=None):
    rng = rng or random.Random(int(x * 3 + y * 7))
    segs = max(3, int(length / 1.5))
    prev = (x, y, z)
    for i in range(1, segs + 1):
        t = i / segs
        p = (x + math.sin(t * 5 + x) * 0.35, y + rng.uniform(-0.2, 0.2), z - length * t)
        b.beam(prev, p, 0.07, 'jungle_light')
        prev = p
    for _ in range(3):
        t = rng.uniform(0.2, 0.9)
        px = x + math.sin(t * 5 + x) * 0.4
        b.sphere((px, y - 0.05, z - length * t), 0.20, SurfaceKey('jungle','groundcover_leaf'), (1.3, 0.4, 0.7), subdiv=0)
    if rng.random() < 0.40:
        for i in range(3):
            t = rng.uniform(0.25, 0.85)
            px = x + math.sin(t * 5 + x) * 0.45
            b.sphere((px, y - 0.12, z - length * t), 0.13,
                     SurfaceKey(('blossom','blossom_pale','coral')[i % 3],'flower'), subdiv=0)
