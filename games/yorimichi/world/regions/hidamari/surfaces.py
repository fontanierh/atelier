"""The surface each face of a textured city mesh is made of, as a material slot HDS_<slug> for the city material
(unreal/Scripts/city_material.py, textures from tools/hidamari_textures.py).

A face keeps its vertex colour (the palette); the slot only says which detail texture multiplies it. The surface comes
from the face's palette key (village Mesh.keys) by the first rule below whose pattern the key contains: kit modules
name their colours after what they are (iz_tin, mc_plaster, sento_granite...). A face coloured with a tuple is given
the key of the nearest palette colour (same hue, any brightness within a factor 1.5). 'flat' is the vertex colour
alone: lamps and glass, which glow; cloth, paper, signs and lettering, which carry their own pattern; leaves and
water. Painted colours and any key no rule names get 'paint'. UVs stay as the village Mesh writes them, in metres; the material tiles by the texture's
size.
"""
import math, re
from functools import lru_cache
import bpy
from village import build as v

RULES = [
    ('rice', r'^ar_rice'),                  # before 'flat' (stalk) and 'grass' (lawn)
    ('drystone', r'drystone'),
    ('blockwall', r'block_concrete'),
    ('flat', r'glow|lamp|downlight|glass|mirror|window|display|vend|sign$|_sign|text|steam|noren|banner|futon|cloth|'
             r'shoji|paper|bottle|map$|broth|bowl|bread|bun$|crust|fruit|tyre|bike|cat$|fox|mane|shide|rope|bloom|rose|'
             r'iris|reed|stalk|twig|leaf|ginkgo|hedge|fallen|water|foam|tactile|_line|stripe|chalk|glaze|drum|machine|'
             r'bucket|belt|leather|^shr_ink$|^st_ink$|tatami|mushiko|gold|brass|node'),
    ('roof', r'roof|tile|ridge|slate'),
    ('metal', r'tin|galv|copper|iron|metal|seam|rib$|steel|shutter'),
    ('brick', r'brick'),
    ('asphalt', r'asphalt|gutter'),
    ('sidewalk', r'paving|paver|kerb|floor|^hd_walk'),
    ('gravel', r'gravel|pebble'),
    ('moss', r'moss'),
    ('grass', r'^park$|lawn|^green$|^green_dark$|^hd_grass'),
    ('earth', r'soil|lane|earth|dirt|^hd_yard'),
    ('flagstone', r'^hd_flag'),
    ('concrete', r'concrete'),
    ('stone', r'stone|rock|granite|plinth|_base$|cap$|well|mortar|step|foundation'),
    ('siding', r'board|plank|deck|siding|clap|black|char|lattice|kura_bark'),
    ('timber', r'wood|timber|cedar|frame|fascia|soffit|rail|post|beam|barge|bark|dark|endgrain|trim|surround|door|'
               r'under|inner|bamboo|gable|edge'),
    ('plaster', r'plaster|cream|ivory|white|wall|stucco|pale|panel|^cream$'),
]
# The meshes drawn with the city material (unreal/Scripts/import_hidamari.py routes the same names). Trees, lanterns,
# water, the harbour, the floors with their own paving materials and the northern mountains keep theirs.
TEXTURED = {'HD_ClockHall', 'HD_Station', 'HD_Shrine', 'HD_Temple', 'HD_Square', 'HD_Park', 'HD_Streets',
            'HD_CivicGardens', 'HD_Terrain', 'HD_Arcade', 'HD_ArcadeGate', 'HD_ArcadeRoof', 'HD_PlazaShopSides',
            'HD_PlazaShopSidesCorner', 'HD_PlazaShopApproaches', 'HD_PlazaFountain', 'HD_Market', 'HD_Pavilion',
            'HD_Lighthouse', 'HD_Playground', 'HD_LaneEdges', 'HD_Pagoda', 'HD_Graves', 'HD_Precinct',
            'HD_StationYard', 'HD_ParkGrounds', 'HD_Arrival'}


def textured(name):
    return name in TEXTURED or name.startswith(('HD_Shop_', 'HD_ArcadeShop_', 'HD_House_'))


SLUGS = ['flat'] + sorted({s for s, _ in RULES if s != 'flat'} | {'paint'})


@lru_cache(maxsize=None)
def slug_for(key):
    for slug, pattern in RULES:
        if re.search(pattern, key): return slug
    return 'paint'


def nearest(colour, palette):
    """The palette key whose colour has the same hue as colour, at any brightness within x1.5 (None if none is close)."""
    best, key = .22, None
    lc = [math.log(max(c, 1e-4)) for c in colour[:3]]
    for k, p in palette:
        r = [a - math.log(max(b, 1e-4)) for a, b in zip(lc, p)]
        mean = sum(r) / 3
        d = max(abs(x - mean) for x in r) + .25 * max(0., abs(mean) - .4)
        if d < best: best, key = d, k
    return key


def slugs(m):
    """One slug per face of the village Mesh m."""
    palette = [(k, c) for k, c in v.PALETTE.items() if isinstance(c, tuple) and len(c) == 3]
    keys = m.keys if len(m.keys) == len(m.faces) else [None] * len(m.faces)
    cache = {}; out = []
    for face, key in zip(m.faces, keys):
        if key is None:
            c = tuple(round(x, 4) for x in m.colors[face[0]][:3])
            if c not in cache:
                k = nearest(c, palette); cache[c] = slug_for(k) if k else 'paint'
            out.append(cache[c])
        else:
            out.append(slug_for(key))
    return out


_materials = {}


def material(slug):
    if slug not in _materials:
        mat = bpy.data.materials.new('HDS_' + slug); mat.use_nodes = True
        vc = mat.node_tree.nodes.new('ShaderNodeVertexColor'); vc.layer_name = 'Color'
        mat.node_tree.links.new(vc.outputs['Color'], mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
        _materials[slug] = mat
    return _materials[slug]


def export(m):
    """village.build.export with one material slot per surface; the manifest entry lists the slots."""
    per_face = slugs(m); used = sorted(set(per_face)); index = {s: i for i, s in enumerate(used)}
    make = m.object

    def textured(_material):
        ob = make(material(used[0]))
        data = ob.data
        for s in used[1:]: data.materials.append(material(s))
        data.polygons.foreach_set('material_index', [index[s] for s in per_face])
        return ob
    m.object = textured
    try:
        ob, info = v.export(m, material(used[0]))
    finally:
        del m.object
    counts = {s: 0 for s in used}
    for s in per_face: counts[s] += 1
    info.update(materials=len(used), slots={s: counts[s] for s in used})
    return ob, info
