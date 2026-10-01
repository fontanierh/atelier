"""The park's hilltop letters: SHARKS becomes 寄り道 (docs/MEGAPARK.md, "Restyle").

Pure NumPy, plus fontTools for font(). The original letters are one render part and their own triangles in one
collision section. The park build (Blender) leaves both out and extrudes 寄り道 from a static Black instance of the
island's Noto Sans JP in their place: the same plane, the same height, the same support trusses behind, the same
weathered concrete, and a collision of their own like the originals had. Nothing else on the hill changes.
"""
from functools import lru_cache
from pathlib import Path

import numpy as np

from megapark import placement

MODEL = '0x1E077DDD5C16EF04'            # the hilltop resource: rock, lamps, the SHARKS letters
PART = 12                               # the letters, in concrete
SUPPORTS = 13                           # the trusses behind them
SECTION = '40A58EF9D5F1AE6E_0'          # the collision section holding the letters' own triangles
TEXT = '寄り道'
FONT = Path(__file__).resolve().parents[1] / 'hidamari' / 'fonts' / 'NotoSansJP.ttf'
WEIGHT = 900                            # Black: strokes that read from across the park
HEIGHT = 9.4                            # metres, the tallest glyph (SHARKS: 9.9)
DEPTH = 1.5                             # metres, from the trusses toward the park
SPACING = 1.08                          # Blender character spacing
TEXELS = .141                           # UV units per metre, as on the original letters
BLACK = 'lettering/NotoSansJP-Black.ttf'  # font(), under build/yorimichi/megapark


def is_letters(model, part):
    return model['asset_id'] == MODEL and part['index'] == PART


@lru_cache(maxsize=1)
def _source():
    src = placement.source()
    model = next(m for m in src['models'] if m['asset_id'] == MODEL)
    with np.load(placement.SOURCE / model['npz'], allow_pickle=False) as arrays:
        letters = arrays[f'vertices_{PART}'].astype('f8')
        supports = arrays[f'vertices_{SUPPORTS}'].astype('f8')
    return model, letters, supports


@lru_cache(maxsize=1)
def frame():
    """The original letters' frame in native metres: centre (mid-length, at the base, on their back face, where the
    trusses stand), axis (reading direction), normal (toward the readers), bottom and top heights, length."""
    _, v, supports = _source()
    plan = v[:, [0, 2]]
    middle = plan.mean(0)
    _, _, vt = np.linalg.svd(plan - middle, full_matrices=False)
    normal = np.array([-vt[0][1], 0., vt[0][0]])
    if np.dot(supports[:, [0, 2]].mean(0) - middle, normal[[0, 2]]) > 0:
        normal = -normal
    axis = np.cross([0., 1., 0.], normal)           # axis x up = normal: glyph x, y, z map to axis, up, normal
    along = (plan - middle) @ axis[[0, 2]]
    depth = (plan - middle) @ normal[[0, 2]]
    centre = np.array([middle[0], 0., middle[1]]) + axis * (along.min() + along.max()) / 2 \
        + normal * depth.min()
    centre[1] = v[:, 1].min()
    return {'centre': centre, 'axis': axis, 'normal': normal, 'bottom': float(v[:, 1].min()),
            'top': float(v[:, 1].max()), 'length': float(along.max() - along.min())}


def letters_mask(triangles):
    """True for collision triangles whose three corners are corners of the rendered letters (within 2 cm)."""
    _, v, _ = _source()
    keys = {tuple(k) for k in np.round(v / .02).astype(np.int64).tolist()}
    shifts = [(a, b, c) for a in (-1, 0, 1) for b in (-1, 0, 1) for c in (-1, 0, 1)]
    corners = np.round(np.asarray(triangles, 'f8').reshape(-1, 3) / .02).astype(np.int64).tolist()
    on = np.array([any((x + a, y + b, z + c) in keys for a, b, c in shifts) for x, y, z in corners])
    return on.reshape(-1, 3).all(1)


def place(local):
    """Glyph metres (x along the text, y up from the base, z out of the front) -> native metres."""
    f = frame()
    local = np.asarray(local, 'f8')
    return f['centre'] + local[..., :1] * f['axis'] + local[..., 1:2] * np.array([0., 1., 0.]) + local[..., 2:] * f['normal']


def uvs(local, normals):
    """Box-projected UVs at the original letters' texel density: faces use the two frame axes they lie along."""
    local = np.asarray(local, 'f8'); n = np.abs(np.asarray(normals, 'f8'))
    axis = n.argmax(1)
    u = np.where(axis == 0, local[:, 2], local[:, 0])
    v = np.where(axis == 1, local[:, 2], local[:, 1])
    return np.stack([u, -v], 1) * TEXELS


def font(path):
    """Write a static Black instance of the island's Noto Sans JP, cut down to TEXT, for Blender's text curves."""
    from fontTools import subset
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer
    face = TTFont(FONT)
    options = subset.Options(); options.layout_features = []; options.name_IDs = ['*']
    cut = subset.Subsetter(options); cut.populate(text=TEXT); cut.subset(face)
    face = instancer.instantiateVariableFont(face, {'wght': WEIGHT})
    path.parent.mkdir(parents=True, exist_ok=True)
    face.save(path)
    return path
