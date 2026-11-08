"""Performance budgets of the Belmonte train (plain Python): furniture triangles per level of detail, texture sizes,
level-of-detail screen sizes and the per-coach furniture totals. The target is the fanless MacBook Air M5 at 1080p
and 60 fps or more with two seven-vehicle trains moving through the forest.

`lod_furniture.py` decimates the fitted Tripo furniture to these targets (Blender) and the budget tests check its
outputs from the GLBs alone (`tests/test_belmonte_train_budgets.py`), without Blender or Unreal.

Screen sizes follow Unreal's convention (a mesh's bounding-sphere diameter over the view's width at a 90 degree field
of view): a sphere of radius r at d metres is r / d.
"""
import json
import struct
from pathlib import Path

# asset: (LOD0 triangles, LOD1 triangles or None, texture px). None: no LOD1, the mesh is culled at distance.
FURNITURE = {
    'second-class-bench': (1200, 200, 1024),
    'second-class-bench-carved': (2500, 300, 1024),   # front and a clean back twin: the carved M+L reads from the front
    'first-class-sofa': (3000, 400, 1024),
    'restaurant-banquette': (2000, 300, 1024),
    'restaurant-table': (1000, 150, 2048),            # see LARGE_TEXTURES
    'first-class-table': (800, 120, 1024),
    'table-lamp': (600, None, 512),
    'wall-sconce': (400, None, 512),
    'canteen-counter': (2500, 400, 1024),
    'canteen-shelves': (2000, 300, 1024),
    'canteen-stove': (1500, 250, 1024),
    'canteen-pot': (800, None, 1024),
    'canteen-sink': (800, None, 1024),
    'canteen-ladle': (150, None, 512),
    'canteen-mug': (150, None, 512),
    'loco-backhead': (4000, 800, 1024),
}

# Aims below a cap where a coach total needs it: 31 benches at 200 would alone pass the second class's LOD1 budget.
LOD1_AIM = {'second-class-bench': 150}

# Assets allowed above 1024 px. The restaurant table: its cloth's woven damask is a fine pattern spread over a large
# draped area; at 1024 the bake loses it and the cloth turns plain. The eight tables share one material, so the
# 2048 set (about 8 MB of compressed maps with their mips) is paid once, and the table's LOD1 drops to 512.
LARGE_TEXTURES = {'restaurant-table'}

# Extra materials allowed beside the baked one: the pot's porridge is its own mesh and material for the game to animate.
EXTRA_MATERIALS = {'canteen-pot': ('M_BT_Porridge',)}

COACH_LOD0 = 50000          # instanced furniture triangles in one vehicle, every placement at LOD0
COACH_LOD1 = 6000           # the same at LOD1, meshes without LOD1 culled
SHELL = dict(LOD0=60000, LOD1=20000, LOD2=1500)   # the shell manifest's budgets, enforced as they stand

LOD1_DISTANCE_M = 6.        # furniture switches to LOD1 beyond this
CULL_DISTANCE_M = 40.       # and disappears (the shells' dark LOD2 windows take over)
SMALL_CULL_DISTANCE_M = 14.  # lamps, sconces, mugs, the ladle, the pot and the sink: no LOD1, culled sooner


def texture_cap(asset):
    return FURNITURE[asset][2]


def screen_sizes(asset, radius):
    """LOD screen sizes for a mesh of bounding-sphere radius `radius` (metres): LOD0 at 1.0, LOD1, cull."""
    lod1 = FURNITURE[asset][1]
    cull_d = CULL_DISTANCE_M if lod1 else SMALL_CULL_DISTANCE_M
    out = dict(lod0=1.0, cull=round(radius / cull_d, 5))
    if lod1:
        out['lod1'] = round(radius / LOD1_DISTANCE_M, 5)
    return out


def is_power_of_two(n):
    return n > 0 and n & (n - 1) == 0


# ---------------------------------------------------------------- GLB reading (no Blender)
def read_glb(path):
    """(json document, binary chunk) of a .glb."""
    data = Path(path).read_bytes()
    length = struct.unpack_from('<I', data, 8)[0]
    pos, doc, binary = 12, None, b''
    while pos < length:
        size, kind = struct.unpack_from('<II', data, pos)
        chunk = data[pos + 8:pos + 8 + size]
        if kind == 0x4E4F534A:
            doc = json.loads(chunk)
        elif kind == 0x004E4942:
            binary = chunk
        pos += 8 + size
    return doc, binary


def image_size(blob):
    """(width, height) of a PNG or JPEG held in bytes."""
    if blob[:8] == b'\x89PNG\r\n\x1a\n':
        return struct.unpack('>II', blob[16:24])
    if blob[:2] == b'\xff\xd8':
        i = 2
        while i < len(blob):
            if blob[i] != 0xFF:
                i += 1
                continue
            marker = blob[i + 1]
            if marker in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack('>HH', blob[i + 5:i + 9])
                return w, h
            i += 2 + struct.unpack('>H', blob[i + 2:i + 4])[0]
    raise ValueError('not a PNG or JPEG')


def glb_stats(path):
    """Triangles (every mesh instance of the default scene), the materials its primitives use, and the size of every
    embedded image."""
    doc, binary = read_glb(path)
    nodes, meshes, acc = doc.get('nodes', []), doc.get('meshes', []), doc['accessors']
    tris, used = 0, set()

    def walk(i):
        nonlocal tris
        n = nodes[i]
        if 'mesh' in n:
            for p in meshes[n['mesh']]['primitives']:
                count = acc[p['indices']]['count'] if 'indices' in p else acc[p['attributes']['POSITION']]['count']
                tris += count // 3
                used.add(p.get('material', -1))
        for c in n.get('children', []):
            walk(c)
    for i in doc['scenes'][doc.get('scene', 0)]['nodes']:
        walk(i)
    mats = doc.get('materials', [])
    images = []
    for im in doc.get('images', []):
        bv = doc['bufferViews'][im['bufferView']]
        o = bv.get('byteOffset', 0)
        images.append(image_size(binary[o:o + bv['byteLength']]))
    return dict(triangles=tris, materials=[mats[m].get('name', '') if m >= 0 else '' for m in sorted(used)], images=images)


# --- the shells' parts (parts.py): the shadow proxy that casts each vehicle's shadows in place of its detail
SHELL_PROXY = 400           # triangles
