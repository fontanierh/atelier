"""Brinecove on the world map and its atlas reference: ground heights, roofs, piers, streets and landmarks.

build_map.py samples heights() from the exported ground (ground_surface) into its raster and calls draw() with its world-to-pixel mapping. World metres.
Plain Python.
"""
import hashlib
import json
import math

import numpy as np

from brinecove import layout as L
from brinecove import region as R

ROOF = {'roof_terra': (178, 92, 62), 'roof_terra_light': (198, 120, 84), 'roof_teal': (70, 126, 120),
        'roof_slate': (88, 92, 104), 'roof_straw': (196, 160, 92)}
TIMBER = (150, 120, 84)


def contains(x, y):
    x0, y0, x1, y1 = R.OUTER_WORLD
    return (x > x0) & (x < x1) & (y > y0) & (y < y1)


def trees(runtime, prefixes):
    """World xy of the region's own trees for the map's forest cover: every flora prototype counts as warm broadleaf
    except the palms, which count with the conifers' cool tint."""
    warm = any(p.startswith(('Tree_Maple', 'Tree_Broad')) for p in prefixes)
    rows = []
    for group in runtime['groups']:
        name = group['asset'].rsplit('.', 1)[-1]
        if not name.startswith('SM_BC_Plant_'):
            continue
        palm = 'Palm' in name
        if palm == warm:
            continue
        for t in group['transforms']:
            x, y = t['translation_cm'][0] / 100. + R.ORIGIN[0], -t['translation_cm'][1] / 100. + R.ORIGIN[1]
            rows.append((x, y))
    return np.asarray(rows, float).reshape(-1, 2)


def ground_surface(out):
    """The game ground world.brinecove exported (its SM_BC_Ground tiles: the layout, the jagged cliffs and the collar
    zipped onto FarHills' own rim), as a height sampler in world metres. The atlas reference samples these triangles,
    so the painted coast is the coast the game ships rather than an approximation of it."""
    from belmonte import source
    report = json.loads((out / 'brinecove' / 'build-report.json').read_text())
    tiles = [mesh for mesh in report['meshes'] if mesh['name'].startswith('SM_BC_Ground_')]
    if not tiles:
        raise ValueError('Brinecove export has no ground tiles')
    faces = []
    for mesh in tiles:
        path = out / 'brinecove' / mesh['path']
        # Only bytes the export declared: a missing or altered tile must fail, not draw a different coast.
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != mesh['sha256']:
            raise ValueError(f'Brinecove ground tile {mesh["name"]} is missing or differs from build-report.json')
        faces.append(source.triangles(path))
    faces = np.concatenate(faces) + np.asarray(R.ORIGIN, float)
    return source.Surface(faces)


def heights(gx, gy, surface):
    """The game ground at world points inside the region, from ground_surface()."""
    z = surface.height(gx, gy)
    if not np.isfinite(z).all():
        raise ValueError(f'Brinecove ground leaves {int((~np.isfinite(z)).sum())} map samples uncovered')
    return z.astype(np.float32)


def _rect(d, wp, x, y, w, h, yaw, fill, outline):
    a = math.radians(yaw)
    c, s = math.cos(a), math.sin(a)
    pts = [wp(x + u * c - v * s + R.ORIGIN[0], y + u * s + v * c + R.ORIGIN[1])
           for u, v in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2))]
    d.polygon(pts, fill=fill, outline=outline)


def _line(d, wp, px, pts, fill, width):
    d.line([wp(x + R.ORIGIN[0], y + R.ORIGIN[1]) for x, y in pts], fill=fill, width=max(1, round(width * px)),
           joint='curve')


def draw(d, wp, px):
    """Streets, the market, piers, roofs, ships and landmarks, in plan."""
    pave = (214, 200, 170)
    # The quay promenade, the waterfront street and the upper terrace street (layout.on_street).
    for x0, x1, y0, y1 in ((-392, 392, L.QUAY_Y - 4, 104), (-392, 392, 143, 177), (-318, 338, 312, 378), (-20, 20, 225, 318)):
        _rect(d, wp, (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0, 0, pave, None)
    _rect(d, wp, 0, 160, 200, 140, 0, (222, 208, 176), (150, 130, 100))
    for name, x, y0, y1, width in L.PIERS:
        _rect(d, wp, x, (y0 + y1) / 2, width, abs(y1 - y0), 0, TIMBER, (80, 60, 30))
    for x, y, w, h, roof in L.MARKET_STALLS:
        _rect(d, wp, x, y, w, h, 0, (196, 82, 64) if roof == 'roof_red' else (236, 226, 200), (90, 60, 40))
    for b in list(L.DENSE_LOTS) + list(L.SHORE_BUILDINGS) + list(L.HILLSIDE_BUILDINGS):
        key, x, y, z, w, depth, h, floors, style, yaw, roof = b
        _rect(d, wp, x, y, w, depth, yaw, ROOF.get(roof, ROOF['roof_terra']), (60, 36, 24))
    for name, x, y, yaw, scale, sails in L.SHIPS:
        _rect(d, wp, x, y, 18 * scale, 60 * scale, yaw, (98, 66, 44), (40, 24, 16))
    # The river down the gorge to the two falls.
    g = L.gorge_levels()
    _line(d, wp, px, [(g['lower'] - 2, L.GORGE_Y), (690, L.GORGE_Y)], (69, 143, 174), 10)
    for x, y, r, colour in ((L.LIGHTHOUSE[0], L.LIGHTHOUSE[1], 5, (240, 236, 220)), (L.WATCHTOWER[0], L.WATCHTOWER[1], 9, (170, 150, 120)),
                            (L.STATUE[0], L.STATUE[1], 4, (190, 186, 176))):
        _rect(d, wp, x, y, 2 * r, 2 * r, 45, colour, (40, 30, 20))
