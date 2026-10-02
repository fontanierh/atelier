"""The car park's cars (docs/MEGAPARK.md, "Restyle").

Pure NumPy. The four traffic cars the park came with (a sports car, two saloons and an SUV, photo-textured, sharing
one set of tyres) are left out of its render mesh, and the collision triangles that shaped them out of the car park's
section. Four kei cars after the Sunburst sheet (assets/vehicles/kei) stand in their bays instead, each with its own
box collision, so the bays keep something to walk round and to stop the board.
"""
from functools import lru_cache

import numpy as np

from megapark import placement

CARS = {'0xBD340E588EB1B8A8': (17, 18), '0xB5FC108CCBDF28D8': (3, 12, 13)}   # asset -> render parts (12: the tyres)
SECTION = '0AA6238270286C2E_0'      # the car park's collision section
MARGIN = .3                         # metres round a car's box that the collision shaping it stays within
KEI = ('SM_Kei_Pickup', 'SM_Kei_Wagon', 'SM_Kei_Retro', 'SM_Kei_Microvan')   # bay by bay, native x rising
KEI_LENGTH = 3.39                   # assets/vehicles/kei/build.py LENGTH
BACK = .06                          # metres between a kei car's back and where the old car's back stood


def is_car(model, part):
    return part['index'] in CARS.get(model['asset_id'], ())


@lru_cache(maxsize=1)
def bays():
    """[(lo, hi)] native boxes (x, y up, z) of the four cars, native x rising: the cars' vertices split where x jumps."""
    points = []
    for m in placement.source()['models']:
        if m['asset_id'] in CARS:
            with np.load(placement.SOURCE / m['npz']) as a:
                points += [a[f'vertices_{i}'].astype('f8') for i in CARS[m['asset_id']]]
    p = np.concatenate(points); xs = np.sort(p[:, 0]); cut = np.flatnonzero(np.diff(xs) > .5)
    spans = zip(np.r_[xs[0], xs[cut + 1]], np.r_[xs[cut], xs[-1]])
    return [(q.min(0), q.max(0)) for q in (p[(p[:, 0] >= a) & (p[:, 0] <= b)] for a, b in spans)]


def collision_mask(triangles):
    """Which collision triangles shaped the cars: every corner inside a car's box grown by MARGIN."""
    t = np.asarray(triangles, 'f8'); mask = np.zeros(len(t), bool)
    for lo, hi in bays():
        mask |= ((t >= lo - MARGIN) & (t <= hi + MARGIN)).all(2).all(1)
    return mask


def _ground(triangles, x, z):
    """Highest native y of the triangles (n, 3, 3) straight under (x, z); nan where there is none."""
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    e1 = (b - a)[:, [0, 2]]; e2 = (c - a)[:, [0, 2]]; q = np.array([x, z]) - a[:, [0, 2]]
    det = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
    ok = np.abs(det) > 1e-12; det = np.where(ok, det, 1)
    u = (q[:, 0] * e2[:, 1] - q[:, 1] * e2[:, 0]) / det; v = (e1[:, 0] * q[:, 1] - e1[:, 1] * q[:, 0]) / det
    hit = ok & (u >= -1e-6) & (v >= -1e-6) & (u + v <= 1 + 1e-6)
    y = a[:, 1] + u * (b - a)[:, 1] + v * (c - a)[:, 1]
    return float(y[hit].max()) if hit.any() else float('nan')


@lru_cache(maxsize=1)
def props():
    """[{mesh, location_cm, forward, up}] the kei cars in the park actor's frame (ue(native) = 100 (x, z, y)): each in
    its bay with its back where the old car's was, facing out of the bay (native +z), set on the plane that fits the
    ground under it."""
    section = next(c for c in placement.source()['collision'] if c['id'] == SECTION)
    t = np.load(placement.SOURCE / section['npz'])['triangles'].astype('f8')
    ground = t[~collision_mask(t)]
    out = []
    for name, (lo, hi) in zip(KEI, bays()):
        cx = (lo[0] + hi[0]) / 2; cz = lo[2] + BACK + KEI_LENGTH / 2
        gx, gz = (g.ravel() for g in np.meshgrid(np.linspace(cx - .6, cx + .6, 5), np.linspace(cz - 1.5, cz + 1.5, 7)))
        y = np.array([_ground(ground, a, b) for a, b in zip(gx, gz)])
        assert np.isfinite(y).all(), (name, 'no ground under the bay')
        y0, sx, sz = np.linalg.lstsq(np.c_[np.ones(len(y)), gx - cx, gz - cz], y, rcond=None)[0]
        up = np.array([-sx, 1., -sz]); up /= np.linalg.norm(up)
        forward = np.array([0., 0., 1.]) - up[2] * up; forward /= np.linalg.norm(forward)
        out.append({'mesh': name, 'location_cm': [round(100 * cx, 2), round(100 * cz, 2), round(100 * y0, 2)],
                    'forward': [round(float(forward[i]), 6) for i in (0, 2, 1)],
                    'up': [round(float(up[i]), 6) for i in (0, 2, 1)]})
    return out
