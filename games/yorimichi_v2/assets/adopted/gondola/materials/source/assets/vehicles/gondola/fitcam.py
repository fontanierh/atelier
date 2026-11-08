"""Fit pinhole cameras to the concept paintings from picked correspondences (no Blender).

uv run python games/yorimichi/assets/vehicles/gondola/fitcam.py
Each view is a panel of a concept image (box in the painting's 1536 x 1024 pixels) with points picked on the painting
and the model point that matches each. A Levenberg-Marquardt fit solves the camera position, heading (yaw of the view
direction from +x), downward pitch, roll and focal length (pixels), with the principal point at the panel centre.
Writes cameras.json beside this file (render.py reads it) and prints the residual of every point.

The model points use the build parameters (params.py): the cabin hangs from the grip at the origin, the tower stands
on its datum, and each station has its platform top at z = 0 with the bullwheel centre at the origin.
"""
import json
import math
from pathlib import Path

import numpy as np

import params as P

HERE = Path(__file__).resolve().parent
p = P.load(); d = P.derived(p)
G = d['grip_to_floor']
F = -G                         # cabin floor top in the cabin's export frame


def cab(x, y, z):
    """Cabin body coordinates (floor top z = 0) to the export frame (grip at the origin)."""
    return (x, y, z + F)


# Views: name -> panel box, initial guess and correspondences [(model xyz, concept pixel)].
VIEWS = {
    'cabin_exterior': {
        'concept': 'gondola_cabin.jpg', 'box': (0, 0, 762, 1024),
        'guess': dict(pos=(4.6, -6.2, -1.0), yaw=math.radians(126), pitch=math.radians(4), roll=0.0, focal=900.0),
        'points': [
            (cab(1.097, -0.997, 2.12), (343, 440)), (cab(1.097, -0.997, 0.0), (345, 838)),
            (cab(-1.097, -0.997, 2.12), (137, 425)), (cab(-1.097, -0.997, 0.0), (140, 748)),
            (cab(1.097, 0.997, 2.12), (627, 450)), (cab(1.097, 0.997, 0.0), (612, 770)),
            (cab(-0.5, -1.05, 0.0), (180, 778)), (cab(0.5, -1.05, 0.0), (262, 824)),
            (cab(-0.5, -1.05, 2.05), (178, 437)), (cab(0.5, -1.05, 2.05), (265, 455)),
            (cab(0.0, 0.0, 2.50), (360, 348)), ((0.0, -0.1, 0.0), (378, 108)),
        ]},
    'cabin_interior': {
        # Looking along the rope at the -x end wall from just in front of the +x bench: the door wall is on the
        # left, as painted. Pitch and roll stay zero (the painting's verticals are vertical); a lens shift puts its
        # horizon (the sea line through the windows) above the frame centre.
        'concept': 'gondola_cabin.jpg', 'box': (772, 0, 1536, 1024),
        'guess': dict(pos=cab(0.55, -0.2, 1.4), yaw=math.radians(180), pitch=0.0, roll=0.0, focal=330.0),
        'free': [1, 2, 3, 6, 8],
        'points': [
            (cab(-1.059, -0.805, 1.945), (1040, 247)), (cab(-1.059, 0.805, 1.945), (1357, 247)),
            (cab(-1.059, -0.805, 0.745), (1040, 525)), (cab(-1.059, 0.805, 0.745), (1357, 525)),
            (cab(-0.905, 0.959, 1.945), (1400, 240)), (cab(-0.905, 0.959, 0.745), (1400, 560)),
            (cab(-0.905, -0.959, 1.945), (1000, 238)), (cab(-0.905, -0.959, 0.745), (1000, 548)),
        ]},
}


def eave(z_ridge, half, t, y, z_bottom):
    """stations.eave_for: the eave height that puts a slab roof's underside at z_bottom, y from the ridge."""
    def under(z_eave):
        rise = z_ridge - z_eave; nz = half / math.hypot(half, rise)
        return z_ridge - rise * y / half - t / nz
    lo, hi = 0.01, 30.0
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if under(z_ridge - mid) > z_bottom else (lo, mid)
    return z_ridge - (lo + hi) / 2


def guess(pos, target, lens, w=1536):
    d = np.array(target, float) - np.array(pos, float); d /= np.linalg.norm(d)
    return dict(pos=pos, yaw=math.atan2(d[1], d[0]), pitch=-math.asin(d[2]), roll=0.0, focal=lens / 36.0 * w)


# Stations: the valley and crater-floor cameras are fitted to structural anchors (roof apexes and eave corners, post
# feet, the bullwheel centre) with a fixed 30 mm lens and zero roll, so the overlays compare structure; the residuals
# measure what still differs. The rim painting's layout does not trace (its wheel overhangs the deck edge, with no
# room for the loop and pit), so its camera stays framed by eye (FRAMED). Station frame: platform top z = 0, the
# bullwheel centre at the origin, the line leaving along +x (stations.py).
ZS = p['berth_floor_step'] + p['cabin_floor_to_roof'] + p['hanger_length'] - 0.15     # bullwheel rope height
VH_E = 3.50                                             # valley house roof eave (irimoya)
VG_E = eave(10.0, 8.3, 0.14, 7.6, 4.95 + 0.32)          # valley cross-gable eave
CC_E = eave(7.4, 8.8, 0.16, 6.9, 4.95 + 0.32)           # crater canopy eave
VIEWS.update({
    'valley_view': {
        'concept': 'gondola_valley_station.jpg', 'box': (0, 0, 1536, 1024), 'free': [0, 1, 2, 3, 4],
        'guess': guess((-8.0, -29.0, 1.6), (-3.0, -8.0, 4.2), 30),
        'points': [((-19.1, -16.2, VH_E), (140, 385)), ((-16.9, -12.6, 5.7), (370, 262)), ((-8.3, -12.6, 5.7), (800, 228)),
                   ((-9.6, -17.1, 3.75), (762, 378)), ((-18.6, -15.6, 0.3), (210, 585)), ((-3.2, -8.2, 10.05), (885, 90)),
                   ((5.1, -8.2, VG_E), (1440, 325)), ((4.4, -6.9, 0.0), (1345, 655)), ((4.4, -6.9, 4.95), (1345, 335)),
                   ((0.0, 0.0, ZS), (1090, 335))]},
    'crater_view': {
        'concept': 'gondola_crater_floor_station.jpg', 'box': (0, 0, 1536, 1024), 'free': [0, 1, 2, 3, 4],
        'guess': guess((22.0, 27.0, 4.0), (-1.0, 0.0, 2.2), 30),
        'points': [((8.2, 0.0, 7.4), (545, 405)), ((8.2, 8.8, CC_E), (450, 515)), ((-1.7, 8.8, CC_E), (930, 500)),
                   ((7.2, 6.9, 0.0), (522, 640)), ((3.0, 6.9, 0.0), (660, 640)), ((-1.2, 6.9, 0.0), (825, 645)),
                   ((-9.6, 8.0, 0.0), (1300, 632)), ((-9.6, 8.0, 5.2), (1303, 505)), ((-1.6, 8.0, 5.2), (905, 422))]},
})


def basis(yaw, pitch, roll):
    dv = np.array([math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), -math.sin(pitch)])
    right = np.cross(dv, [0, 0, 1.0]); right /= np.linalg.norm(right); up = np.cross(right, dv)
    r2 = math.cos(roll) * right + math.sin(roll) * up; u2 = -math.sin(roll) * right + math.cos(roll) * up
    return dv, r2, u2


def project(x, pts, cx, cy):
    C = x[:3]; dv, r2, u2 = basis(x[3], x[4], x[5]); f = x[6]
    v = pts - C; z = v @ dv
    return np.stack([cx + x[7] + f * (v @ r2) / z, cy + x[8] - f * (v @ u2) / z], axis=1)


def fit(view):
    x0, y0, x1, y1 = view['box']; cx, cy = (x1 - x0) / 2, (y1 - y0) / 2
    pts = np.array([q[0] for q in view['points']], float)
    uv = np.array([(q[1][0] - x0, q[1][1] - y0) for q in view['points']], float)
    g = view['guess']; x = np.array([*g['pos'], g['yaw'], g['pitch'], g['roll'], g['focal'], 0.0, 0.0], float)
    lam = 1e-2; free = view.get('free', list(range(7)))

    def res(x):
        return (project(x, pts, cx, cy) - uv).ravel()
    r = res(x); cost = r @ r
    for _ in range(400):
        J = np.zeros((r.size, len(free)))
        for c, k in enumerate(free):
            h = 1e-5 * max(1.0, abs(x[k])); xp = x.copy(); xp[k] += h; J[:, c] = (res(xp) - r) / h
        A = J.T @ J; gvec = J.T @ r
        step = np.linalg.solve(A + lam * np.diag(np.diag(A) + 1e-9), -gvec)
        xn = x.copy(); xn[free] += step; rn = res(xn); cn = rn @ rn
        if cn < cost:
            x, r, cost, lam = xn, rn, cn, lam * 0.4
            if np.linalg.norm(step) < 1e-9:
                break
        else:
            lam *= 5
    errs = np.linalg.norm(r.reshape(-1, 2), axis=1)
    return x, errs


# Framed views: the tower is designed for riding, so its structure does not trace the painting; these cameras are
# placed by eye to match each panel's viewpoint and framing (no residual).
H16 = 16.0
FRAMED = {
    'tower_front': ('gondola_tower_pylon.jpg', (0, 40, 500, 1000), (9.0, -66.0, 5.0), (0.0, 0.0, 7.8), 240),
    'tower_side': ('gondola_tower_pylon.jpg', (480, 40, 700, 1000), (66.0, 4.0, 5.0), (0.0, 0.0, 7.8), 470),
    'tower_head': ('gondola_tower_pylon.jpg', (660, 40, 1180, 520), (2.6, -6.6, H16 - 1.0), (0.2, -2.6, H16 - 0.45), 30),
    'tower_base': ('gondola_tower_pylon.jpg', (720, 530, 940, 945), (4.4, -3.1, 1.2), (1.93, -1.49, 0.75), 40),
    'tower_anchor': ('gondola_tower_pylon.jpg', (955, 570, 1170, 945), (6.0, -4.6, 1.6), (4.05, -1.49, 1.0), 40),
    'tower_scene': ('gondola_tower_pylon.jpg', (1080, 30, 1536, 540), (17.0, -19.0, 7.0), (2.5, 0.0, 10.2), 32),
    'rim_view': ('gondola_rim_station.jpg', (0, 0, 1536, 1024), (-21.0, -25.0, 9.5), (-5.0, -2.0, 1.6), 24),
    'tower_vista': ('gondola_tower_pylon.jpg', (1180, 585, 1536, 995), (-22.0, -27.0, 13.0), (3.0, 0.0, 9.0), 30),
}


def framed():
    out = {}
    for name, (concept, box, pos, target, lens) in FRAMED.items():
        x0, y0, x1, y1 = box; w = x1 - x0
        d = np.array(target, float) - np.array(pos, float); d /= np.linalg.norm(d)
        out[name] = {'concept': concept, 'box': list(box), 'size': [w, y1 - y0], 'pos': list(pos),
                     'yaw': round(math.atan2(d[1], d[0]), 5), 'pitch': round(-math.asin(d[2]), 5), 'roll': 0.0,
                     'focal_px': round(lens / 36.0 * w, 2), 'principal_offset_px': [0.0, 0.0], 'fit': 'framed by eye', 'lens_mm': lens}
    return out


def main():
    out = {}
    for name, view in VIEWS.items():
        x, errs = fit(view)
        x0, y0, x1, y1 = view['box']
        out[name] = {'concept': view['concept'], 'box': list(view['box']), 'size': [x1 - x0, y1 - y0],
                     'pos': [round(v, 4) for v in x[:3]], 'yaw': round(float(x[3]), 5), 'pitch': round(float(x[4]), 5),
                     'roll': round(float(x[5]), 5), 'focal_px': round(float(x[6]), 2),
                     'principal_offset_px': [round(float(x[7]), 1), round(float(x[8]), 1)],
                     'rms_px': round(float(np.sqrt((errs ** 2).mean())), 1), 'max_px': round(float(errs.max()), 1)}
        print(f'{name}: rms {out[name]["rms_px"]} px, max {out[name]["max_px"]} px, pos {out[name]["pos"]}, '
              f'yaw {math.degrees(x[3]):.1f}, pitch {math.degrees(x[4]):.1f}, roll {math.degrees(x[5]):.1f}, f {x[6]:.0f}')
        print('   residuals', [round(float(e), 1) for e in errs])
    out.update(framed())
    (HERE / 'cameras.json').write_text(json.dumps(out, indent=1) + '\n')


if __name__ == '__main__':
    main()
