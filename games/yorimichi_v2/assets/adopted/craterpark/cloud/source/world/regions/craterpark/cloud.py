"""The lenticular cap cloud over Crater Park (docs/CRATERPARK.md, "Cap cloud").

A few nested, translucent lens-shaped shells sit on the volcano's summit, round the ramps on and inside the crest.
From afar (Belmonte, 2 km north) the shells read as one dense white cap and hide the ramps; from inside, where the
park is ridden, they thin to a soft veil over the world beyond the crest. The game builds the shells from this
module's record (craterpark/cloud.json, AJapanWorld -> ACraterCloud) and draws them with
/Game/CraterPark/Cloud/M_CraterCloud and M_CraterCloudVeil (unreal/Scripts/crater_cloud_material.py).

Pure NumPy, island Blender metres (x east, y north, z up). Unreal centimetres are (100 x, -100 y, 100 z).

The material's opacity (OPACITY below, mirrored by crater_cloud_material.py) depends on where the camera is, not on
the pixel: q, the camera's distance from the envelope's centre over its radii (the outer shell's bounding
ellipsoid), takes every shell from its far opacity at q >= FAR_Q down to its near opacity at q <= NEAR_Q. A shell's
surface nearer the camera than NEAR_FADE metres fades out, so nothing hangs in front of the rider's face, and every
shell fades into the ground it meets over SOFT metres.
"""
import json
import math
from pathlib import Path

import numpy as np

VERSION = 1
CENTRE = (860., 2440.)      # the shells' plan centre: the volcano (850, 2400), nudged toward the ramps' middle
# The space the ramps take, measured on the r5 editor park (world.craterpark, non-ground faces, island metres): every
# ramp lies within 505 m of the volcano's centre and under 859 m (the drop-in tower on the east crest); over the north
# crest (toward Belmonte) they reach 770 m. The cap must enclose all of it, with room for the shells' soft edges.
HIDE_RADIUS = 510.
HIDE_TOP = 870.

# The shells: the veil, a soft lens inside them that blurs what lies behind it, then the saucers, stacked as
# the concepts paint them (assets/craterpark/concepts/editor/lenticular-*.jpg): each rim (its widest level z) higher
# and narrower than the last, the lowest at the crest, the slopes below left clear. radius: mean plan radius (m); top /
# bottom: the lens's height over and depth under z at its centre; power: the profile exponent ((1 - s^2)^power over the
# plan fraction s): under 1 a rounded rim, 1 a pointed one. wobble: plan-radius harmonics (fraction, cycles, phase
# degrees) so no rim is a drawn circle. opacity: (near, far) for a saucer; for the veil, (near, far) of its blend of
# the blurred scene, which tint (near, far) turns toward the cloud's colour.
LAYERS = (
    {'name': 'veil', 'veil': True, 'radius': 600., 'z': 740., 'top': 195., 'bottom': 100., 'power': (.55, .75),
     'aspect': 1.08, 'yaw': 18., 'wobble': ((.02, 2, 40.), (.012, 3, 200.)), 'opacity': (.55, .60),
     'tint': (.15, .60)},
    {'name': 'base', 'radius': 645., 'z': 715., 'top': 62., 'bottom': 50., 'power': (.70, 1.),
     'aspect': 1.07, 'yaw': 22., 'wobble': ((.03, 2, 70.), (.02, 3, 160.), (.01, 7, 10.)), 'opacity': (.10, .85)},
    {'name': 'lower', 'radius': 590., 'z': 772., 'top': 55., 'bottom': 58., 'power': (.70, 1.),
     'aspect': 1.06, 'yaw': 30., 'wobble': ((.03, 2, 110.), (.018, 4, 20.)), 'opacity': (.08, .85)},
    {'name': 'upper', 'radius': 500., 'z': 826., 'top': 50., 'bottom': 52., 'power': (.72, 1.),
     'aspect': 1.05, 'yaw': 36., 'wobble': ((.03, 2, 150.), (.02, 3, 300.)), 'opacity': (.07, .80)},
    {'name': 'crown', 'radius': 360., 'z': 876., 'top': 55., 'bottom': 42., 'power': (.75, 1.),
     'aspect': 1.04, 'yaw': 44., 'wobble': ((.03, 2, 20.), (.02, 3, 120.)), 'opacity': (.06, .75)},
)
NEAR_Q, FAR_Q = 1.0, 1.7    # camera q: the shells' near opacity inside the envelope, their far opacity from FAR_Q out
NEAR_FADE = (40., 220.)     # metres: a surface nearer the camera than the first is clear, opaque beyond both summed
SOFT = 45.                  # metres: the shells fade into the ground they meet
# The look (linear emission, the island's fixed exposure: about the colour itself). Sunlit tops warm white, shaded
# undersides the painted sky's cool lavender grey; drift: the striations' slow flow, metres a second.
TOP = (0.96, 0.88, 0.74)
UNDER = (0.58, 0.60, 0.77)
STRIATION_M = (260., 260., 22.)     # the striation noise's size: long and flat, as a standing wave's laminae
STRIATION = .35                     # its share of the opacity, +- half of it
DRIFT = 2.5
BLUR = .010                         # the veil's blur radius, a fraction of the screen width
RINGS, SEGMENTS = 18, 128           # per surface: rings from centre to rim (denser toward it), segments round it


def layer_radius(layer, theta):
    """The plan radius (m) at heading theta (radians from east), before the ellipse."""
    w = sum(a * math.cos(k * theta + math.radians(p)) for a, k, p in layer['wobble']) if np.isscalar(theta) else \
        sum(a * np.cos(k * np.asarray(theta) + math.radians(p)) for a, k, p in layer['wobble'])
    return layer['radius'] * (1. + w)


def _plan(layer, theta, s):
    """Plan offset (m) from CENTRE of the point at heading theta and plan fraction s (0 centre, 1 rim)."""
    r = s * layer_radius(layer, theta)
    a = math.sqrt(layer['aspect'])
    yaw = math.radians(layer['yaw']); c, n = math.cos(yaw), math.sin(yaw)
    u, v = r * np.cos(theta) * a, r * np.sin(theta) / a
    return u * c - v * n, u * n + v * c


def profile(layer, s):
    """(top, bottom) heights (m) over the plan fraction s."""
    s = np.clip(np.asarray(s, float), 0., 1.)
    pt, pb = layer['power']
    f = 1. - s * s
    return layer['z'] + layer['top'] * f ** pt, layer['z'] - layer['bottom'] * f ** pb


def fraction(layer, x, y):
    """The plan fraction s of island points (x, y): below 1 inside the shell's outline."""
    dx = np.asarray(x, float) - CENTRE[0]; dy = np.asarray(y, float) - CENTRE[1]
    yaw = math.radians(layer['yaw']); c, n = math.cos(yaw), math.sin(yaw)
    u, v = dx * c + dy * n, -dx * n + dy * c
    a = math.sqrt(layer['aspect'])
    u, v = u / a, v * a
    theta = np.arctan2(v, u)
    return np.hypot(u, v) / layer_radius(layer, theta)


def inside(layer, points):
    """Whether island points (..., 3) are inside the shell."""
    p = np.asarray(points, float)
    s = fraction(layer, p[..., 0], p[..., 1])
    top, bottom = profile(layer, np.minimum(s, 1.))
    return (s < 1.) & (p[..., 2] <= top) & (p[..., 2] >= bottom)


def envelope():
    """The camera term's ellipsoid: centre (m) and radii (m) of the box round every shell (its corners at q = sqrt 2)."""
    reach = max(layer['radius'] * (1. + sum(a for a, _, _ in layer['wobble'])) * math.sqrt(layer['aspect'])
                for layer in LAYERS)
    lo = min(layer['z'] - layer['bottom'] for layer in LAYERS)
    hi = max(layer['z'] + layer['top'] for layer in LAYERS)
    return (CENTRE[0], CENTRE[1], (lo + hi) / 2.), (reach, reach, (hi - lo) / 2.)


def camera_q(camera):
    centre, radii = envelope()
    return float(np.linalg.norm((np.asarray(camera, float) - centre) / radii))


def smooth(t):
    t = np.clip(t, 0., 1.)
    return t * t * (3. - 2. * t)


def opacity(layer, camera):
    """A shell's opacity for this camera (the material's camera term; the veil: its blend share)."""
    near, far = layer['opacity']
    return near + (far - near) * float(smooth((camera_q(camera) - NEAR_Q) / (FAR_Q - NEAR_Q)))


def hiding(layer, camera):
    """The share of what lies behind a shell's surface that it hides: its opacity, and for the veil only its tint (the
    blur blends the scene, it does not hide it)."""
    a = opacity(layer, camera)
    if layer.get('veil'):
        near, far = layer['tint']
        a *= near + (far - near) * float(smooth((camera_q(camera) - NEAR_Q) / (FAR_Q - NEAR_Q)))
    return a


def coverage(camera, target, step=2.):
    """How much of `target` the shells hide from `camera` (island metres): one minus the light through every shell
    surface the sight line crosses, each faded as the material fades surfaces near the camera."""
    camera = np.asarray(camera, float); target = np.asarray(target, float)
    length = float(np.linalg.norm(target - camera))
    t = np.arange(0., length, step) / max(length, 1e-9)
    points = camera + t[:, None] * (target - camera)
    distance = t * length
    through = 1.
    for layer in LAYERS:
        state = inside(layer, points)
        crossings = np.flatnonzero(state[1:] != state[:-1])
        a = hiding(layer, camera)
        for i in crossings:
            near = float(smooth((distance[i] - NEAR_FADE[0]) / NEAR_FADE[1]))
            through *= 1. - a * near
    return 1. - through


def surface(layer, rings=RINGS, segments=SEGMENTS):
    """The closed lens: vertices (n, 3) island metres and triangles (m, 3), outward-facing, sharing the rim ring.
    Vertex 0 is the top's centre, 1 the bottom's; then the top's rings, then the bottom's, rim last in each."""
    theta = np.arange(segments) * (2 * math.pi / segments)
    s = np.sin(np.arange(1, rings + 1) / rings * math.pi / 2)     # denser toward the rim, where the profile turns
    top, bottom = profile(layer, s)
    ctop, cbottom = profile(layer, 0.)
    vertices = [(CENTRE[0], CENTRE[1], float(ctop)), (CENTRE[0], CENTRE[1], float(cbottom))]
    for heights in (top, bottom[:-1]):     # the bottom shares the top's rim ring
        for k, h in enumerate(heights):
            x, y = _plan(layer, theta, s[k])
            vertices += [(CENTRE[0] + float(a), CENTRE[1] + float(b), float(h)) for a, b in zip(x, y)]
    vertices = np.array(vertices)

    def ring(side, k):
        """Vertex indices of ring k (0 innermost) of side 0 top / 1 bottom; the rim is the top's last ring."""
        if side == 1 and k == rings - 1:
            side = 0
        return 2 + (side * rings + k) * segments + np.arange(segments)

    tris = []
    for side, centre in ((0, 0), (1, 1)):
        a = ring(side, 0); b = np.roll(a, -1)
        tris += [(centre, i, j) for i, j in zip(a, b)]
        for k in range(rings - 1):
            a, c = ring(side, k), ring(side, k + 1)
            b, d = np.roll(a, -1), np.roll(c, -1)
            tris += [(int(p), int(q), int(r)) for p, q, r in zip(a, c, d)] + [(int(p), int(q), int(r)) for p, q, r in zip(a, d, b)]
        if side == 1:   # counter-clockwise from below
            tris[-(segments * (2 * rings - 1)):] = [(p, r, q) for p, q, r in tris[-(segments * (2 * rings - 1)):]]
    return vertices, np.array(tris, 'i4')


def to_unreal(points):
    p = np.asarray(points, float)
    return np.stack([p[..., 0] * 100., -p[..., 1] * 100., p[..., 2] * 100.], -1)


def record():
    """The game's record (craterpark/cloud.json): each shell's mesh relative to the cloud's origin, and the material
    parameters. Unreal centimetres; the triangles wind for Unreal's left-handed frame (front faces outward)."""
    centre, radii = envelope()
    origin = to_unreal((CENTRE[0], CENTRE[1], 0.))
    layers = []
    for layer in LAYERS:
        v, f = surface(layer)
        local = to_unreal(v) - origin
        layers.append({'name': layer['name'], 'veil': bool(layer.get('veil')),
                       'opacity': list(layer['opacity']), 'tint': list(layer.get('tint', (0., 0.))),
                       'vertices': np.round(local, 1).reshape(-1).tolist(),
                       # the y flip mirrors the frame, so the winding flips with it
                       'triangles': f[:, [0, 2, 1]].reshape(-1).tolist()})
    return {'version': VERSION, 'origin_cm': origin.tolist(),
            'envelope': {'centre_cm': to_unreal(centre).tolist(), 'radii_cm': [r * 100. for r in radii]},
            'q': [NEAR_Q, FAR_Q], 'near_fade_cm': [NEAR_FADE[0] * 100., NEAR_FADE[1] * 100.], 'soft_cm': SOFT * 100.,
            'top': list(TOP), 'under': list(UNDER), 'striation_cm': [m * 100. for m in STRIATION_M],
            'striation': STRIATION, 'drift_cm': DRIFT * 100., 'blur': BLUR, 'layers': layers}


def write(path):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record(), separators=(',', ':')) + '\n')
    return path
