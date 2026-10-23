"""One Brinecove constructor or shared geometry primitive; no sibling generation."""
from brinecove import layout as L
from brinecove.geom import Builder
from brinecove.kit import building
from brinecove.kit import fish_crate
from brinecove.kit import local
from brinecove.kit import pennants
from brinecove.kit import potted_plant
from brinecove.kit import sack
from brinecove.procedural.geometry_policy import LOWER_BANDS
from brinecove.procedural.geometry_policy import LOWER_ROADS
from brinecove.procedural.pave_band import pave_band
from brinecove.procedural.paving import paving
from brinecove.procedural.random_state import RNG
from brinecove.procedural.split_lot import split_lot


def lower_town():
    b = Builder('03_town_lower')
    # Street surfaces, edges and lanes.
    for x, y, w, d in LOWER_ROADS:
        paving(b, x - w / 2, x + w / 2, y - d / 2, y + d / 2, kerbs=(False, False), seed=int(x))
    for y0, y1 in LOWER_BANDS:
        pave_band(b, y0, y1)
    # Lower quay houses and the two lanes behind them.
    for spec in L.DENSE_LOTS:
        if spec[2] < 280:
            if spec[0].startswith(('slope-', 'ridge-')):
                b.box((spec[1], spec[2], spec[3] - 2.1), (spec[4] + 1.0, spec[5] + 1.0, 4.2),
                      'stone', spec[9])
            if spec[0].startswith('slope-') and sum(map(ord, spec[0])) % 3 == 0:
                lx, ly = local(spec[1], spec[2], spec[9], -spec[4] / 2 - 0.7, spec[5] * 0.22)
                for dz in (0.0, 1.0):
                    b.beam((lx + dz, ly, spec[3]), (lx + dz, ly, spec[3] + 5.2), 0.10, 'wood_dark')
                for r in range(6):
                    b.beam((lx, ly, spec[3] + 0.8 + r * 0.75), (lx + 1.0, ly, spec[3] + 0.8 + r * 0.75),
                           0.06, 'wood')
            if spec[8] == 'shack':
                spec = (*spec[:3], L.ground(spec[1], spec[2]) + 0.1, *spec[4:])
            for sub in split_lot(spec, RNG):
                building(b, sub, RNG)
    # Stilt houses on the headland shores.
    for spec in L.SHORE_BUILDINGS:
        key, x, y, _, w, d, h, floors, style, yaw, roof = spec
        z = L.height(x, y) + 1.2
        b.box((x, y, z - 2.0), (w + 3.0, d + 3.0, 4.0), 'stone', yaw)
        for side in (-1, 1):
            px, py = local(x, y, yaw, side * (w * 0.36), 0)
            b.cylinder((px, py, z - 6.0), (px, py, z - 1.0), 0.35, 'wood_dark', 6)
        building(b, (key, x, y, z, w, d, h, floors, style, yaw, roof), RNG)
    # Timber walkways link the stilt houses along each headland.
    for side in (-1, 1):
        specs = sorted([s for s in L.SHORE_BUILDINGS if s[1] * side > 0], key=lambda s: s[2])
        for a, c in zip(specs, specs[1:]):
            ax, ay, az = a[1], a[2], L.height(a[1], a[2]) + 2.2
            cx, cy, cz = c[1], c[2], L.height(c[1], c[2]) + 2.2
            b.beam((ax, ay, az), (cx, cy, cz), 0.8, 'wood_light')
            for off in (-0.6, 0.6):
                b.rope((ax, ay + off, az + 1.0), (cx, cy + off, cz + 1.0), 1.4, 0.06)
    # Low garden walls, cisterns and a few steps at the terrace foot.
    for x in range(-360, 370, 46):
        y = 236
        if abs(x) < 30:
            continue
        b.box((x, y, L.ground(x, y) + 0.65), (34, 1.0, 1.3), 'stone')
        if x % 3 == 0:
            b.sphere((x + RNG.uniform(-8, 8), y + 3.5, L.ground(x, y) + 0.5), 1.1, 'jungle', (1.2, 1, 0.8), subdiv=0)
    # Bunting and working clutter along the waterfront lane: short local spans between pairs of posts, never one
    # line along the whole front (playtest note 14).
    for x in (-300, -150, 0, 150, 300):
        for k, run in enumerate((14.0, 11.0)):
            x0 = x - 16 + k * 22
            for xx in (x0, x0 + run):
                b.beam((xx, 96.5, L.ground(xx, 96.5)), (xx, 96.5, L.ground(xx, 96.5) + 6.2), 0.14, 'wood_dark')
            pennants(b, (x0, 96.5, L.ground(x0, 96.5) + 5.9), (x0 + run, 96.5, L.ground(x0 + run, 96.5) + 5.9), 0.6, 7)
    for x, y, yaw in ((-300, 91, 12), (-150, 91, -10), (0, 91, 8), (150, 91, -12), (300, 91, 10)):
        fish_crate(b, x, y, L.ground(x, y) + 0.1, yaw, 1.1)
    for x, y in ((-260, 166), (-90, 166), (60, 166), (220, 166)):
        potted_plant(b, x, y, L.ground(x, y) + 0.05, 0.75, RNG)
        sack(b, x + 1.4, y + 0.6, L.ground(x, y) + 0.1, 0.85)
    return b
