"""Export Brinecove for the game: ground tiles, town and nature meshes, hero models, foliage instances,
runtime.json and build-report.json in build/yorimichi/brinecove.

    uv run atelier build yorimichi world.brinecove

The ground closes onto the FarHills final product's hole (ground.py), so this step reads that product. Every mesh
is exported in local metres around region.ORIGIN; the Unreal importer (import_brinecove.py) binds each material
slot to a region material, and ABelmonteRegion (tag brinecove) places the groups. The review scene
(review_build.py) builds the same modules for Eevee renders and is never read here.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import random  # noqa: E402
import shutil  # noqa: E402
import time  # noqa: E402

import bpy  # noqa: E402
import numpy as np  # noqa: E402

from atelier.gltf import glb_parts  # noqa: E402
from atelier.mesh_partition import face_groups  # noqa: E402
from terrain_product import load  # noqa: E402
from brinecove import flora, ground, hero_assets, hero_sources, modules, region as R, rocks  # noqa: E402
from brinecove import layout as L  # noqa: E402
from brinecove.geom import Builder, distinct_corners  # noqa: E402
from brinecove.paths import BUILD as OUT, TEXTURES  # noqa: E402

ROOT = '/Game/Brinecove'
TILE = 256.0
# Bound mixed models without increasing draw calls for small existing parts.
MIXED_TRIANGLE_LIMIT = 32768
IDENTITY = {'translation_cm': [0., 0., 0.], 'rotation_xyzw': [0., 0., 0., 1.], 'scale': [1., 1., 1.]}
# Surfaces a player walks through: no collision, and the translucent ones cast no shadow.
SOFT = ('leaf_', 'palm_', 'waterfall', 'mist', 'spray', 'foam', 'water', 'vine', 'flower', 'grass', 'fern', 'cover_')
SEA_LEVEL = ('water', 'foam', 'spray', 'mist', 'waterfall', 'seabed')
MASKED = ('leaf_', 'palm_', 'waterfall', 'spray', 'foam')
TERRAIN = ('terrain', 'rock')
# ground.py's collar seam strip still names the old per-cell beach and jungle materials: they join the blended terrain.
GROUND_REMAP = {'sand': 'terrain', 'jungle_dark': 'terrain'}
TRANSLUCENT = ('mist',)
EMISSIVE = ('lantern', 'glass_warm')
# UV v per second. The glTF export flips v, so in Unreal the curtain's v grows upward: a positive pan runs its streaks
# down (playtest note 5 saw -0.9 run them up). Foam spreads out.
PAN_CM_S = {'waterfall': 0.9, 'foam': 0.05}
# Water motion (import_brinecove.parent): a second, faster streak layer on the curtain; foam lace drifting along the
# shore while its outer edge washes in and out.
MOTION = {'waterfall': {'Layer': 1.0}, 'foam': {'Drift': 0.03, 'Wash': 0.22},
          'mist': {'Opacity': 0.42}}  # spray, not an opaque white cloud at the plunge (note 9 review)
# Materials whose texture has another name: the keyed streak and lace atlases (references/redesign.py --finish).
TEXTURE = {'waterfall': 'waterfall_streaks', 'foam': 'foam_lace'}
# The blended terrain material's layers (albedo and normal-plus-cavity), and the rock tints of its rock-only use.
TERRAIN_LAYERS = {'Sand': 'terrain_sand', 'Meadow': 'terrain_meadow', 'Forest': 'terrain_forest', 'Rock': 'terrain_rock'}
ROCK_TINT = {'rock': 1.0, 'rock_light': 1.12, 'rock_dark': 0.72, 'rock_strata': 0.95}
MODULES = [('Rocks', lambda: modules.terrain_dressing(Builder('rocks'), hills=False)),
           ('Harbor', modules.harbor), ('TownLower', modules.lower_town), ('Market', modules.market),
           ('TownUpper', modules.upper_town), ('Landmarks', modules.landmarks), ('Ships', modules.ships),
           ('Props', modules.props), ('Understory', modules.vegetation)]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def srgb_to_linear(value):
    value = value / 255.0
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def soft(mat):
    return mat.startswith(SOFT)


def kind(mat):
    if mat.startswith(TRANSLUCENT):
        return 'translucent'
    if mat.startswith(MASKED):
        return 'masked'
    if mat.startswith(TERRAIN):
        return 'terrain'
    if mat.startswith(EMISSIVE):
        return 'emissive'
    return 'opaque'


def rim():
    """FarHills' hole boundary from its final product (world.farhills)."""
    mesh = load(yori.OUT / 'terrain/FarHills/final.npz', owner='FarHills', stage='final', city=True)
    vertices, triangles = np.asarray(mesh.vertices), np.asarray(mesh.triangles())
    vertices, triangles = ground.weld(vertices, triangles)
    x0, y0, x1, y1 = R.OUTER_WORLD
    near = ((np.abs(vertices[:, 0] - x0) < .05) | (np.abs(vertices[:, 0] - x1) < .05)
            | (np.abs(vertices[:, 1] - y0) < .05) | (np.abs(vertices[:, 1] - y1) < .05))
    near &= (vertices[:, 0] > x0 - .05) & (vertices[:, 0] < x1 + .05) & (vertices[:, 1] > y0 - .05) & (vertices[:, 1] < y1 + .05)
    keep = near[triangles].sum(1) >= 2
    used = np.unique(triangles[keep])
    remap = {int(v): i for i, v in enumerate(used)}
    local = [[remap[int(v)] for v in t] for t in triangles[keep]]
    return R.rim_from_mesh(vertices[used].tolist(), local)


def settle(rim):
    """(x, y) -> (ground change, game ground) across the collar, where ground.py eases the layout into the far-hills
    rim; (0, None) inside INNER. Dressing placed on the layout moves with the ground under it."""
    cache = {}

    def at(x, y):
        key = (round(x, 1), round(y, 1))
        if key not in cache:
            if R.collar_weight(x, y) <= 0.0:
                cache[key] = (0.0, None)
            else:
                g = R.ground(L.ground, rim, x, y)
                cache[key] = (g - L.ground(x, y), g)
        return cache[key]
    return at


def split(builder, prefix, settle, remap=None):
    """Tiles of TILE metres, and per tile a solid part and a soft part (foliage cards, water, spray).

    Faces in the collar follow the eased ground (settle); water, foam and spray stay at sea level, and plant cards
    whose ground went under the sea are dropped. The ground itself is already eased: settle is None for it.
    Faces with a collapsed corner (a cone's apex quad) lose the repeat, and faces with no area are dropped:
    Unreal drops them on import, and the import checks every tile's triangle count against this report."""
    parts, outside, drowned, degenerate = {}, 0, 0, 0
    ox0, oy0, ox1, oy1 = R.OUTER
    anchors = builder.anchors or ()
    for n, (f, mat) in enumerate(zip(builder.faces, builder.mats)):
        pts = [builder.verts[i] for i in f]
        cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
        if not (ox0 <= cx <= ox1 and oy0 <= cy <= oy1):
            outside += 1
            continue
        anchor = anchors[n] if n < len(anchors) else None
        if settle is not None and not mat.startswith(SEA_LEVEL):
            # A rigid object (a rock, a prop) moves by its anchor's change as one piece; loose faces follow the
            # ground under each vertex. Moving a rock's vertices apart sheared it into overlapping slabs.
            if anchor == rocks.FIXED:
                moves = [(0.0, None)] * len(pts)  # placed on the final ground already
            elif anchor is not None:
                moves = [settle(*anchor)] * len(pts)
            else:
                moves = [settle(p[0], p[1]) for p in pts]
            if soft(mat) and any(g is not None and g < 0.2 for _, g in moves):
                drowned += 1
                continue
            pts = [(p[0], p[1], p[2] + d) for p, (d, _) in zip(pts, moves)]
        if remap:
            mat = remap.get(mat, mat)
            pts = [(p[0], p[1], min(p[2], under_paving(p[0], p[1]))) for p in pts]
            # A seabed face is chosen by its average height, so on a steep shore one corner can stand above the sea:
            # a flat untextured teal wedge on the beach. The blended terrain layer turns to sand at the waterline.
            if mat == 'seabed' and max(p[2] for p in pts) > -0.05:
                mat = 'terrain'
        corners = distinct_corners(pts)
        if corners is None:
            degenerate += 1
            continue
        key = (int((cx - ox0) // TILE), int((cy - oy0) // TILE), soft(mat))
        part = parts.get(key)
        if part is None:
            part = parts[key] = Builder(f'SM_BC_{prefix}_{key[0]}_{key[1]}' + ('_Soft' if key[2] else ''))
            part.spatial_centers = []
        normals = [builder.normals[f[k]] for k in corners] if builder.normals is not None else None
        part.face([pts[k] for k in corners], mat, [builder.uvs[f[k]] for k in corners], normals)
        part.spatial_centers.append((cx, cy))
    return bounded_parts(parts, prefix), outside, drowned, degenerate




def bounded_parts(parts, prefix):
    """Keep final ground tiles and small models intact; partition oversized mixed meshes.

    Complete faces keep the same positions, UVs, normals, materials and role labels.
    Each piece keeps the parent's identity transform and solid/soft policy. Fixed
    child-cell names stay stable while their ancestor subdivision decisions stay the same.
    """
    result = {}
    for key, part in parts.items():
        x, y, is_soft = key
        if prefix == 'Ground' or sum(len(face) - 2 for face in part.faces) <= MIXED_TRIANGLE_LIMIT:
            result[(*key, '')] = part
            continue
        x0, y0 = R.OUTER[0] + x * TILE, R.OUTER[1] + y * TILE
        groups = face_groups(part.verts, part.faces, (x0, y0, x0 + TILE, y0 + TILE),
                             triangle_limit=MIXED_TRIANGLE_LIMIT, locations=getattr(part, 'spatial_centers', None))
        parent_water = all(mat.startswith(('water', 'mist', 'spray', 'foam', 'waterfall')) for mat in part.mats)
        roles = getattr(part, 'foliage_roles', {})
        for suffix, indices in groups:
            piece = Builder(part.name + '_Piece' + suffix)
            # Splitting a mixed water/foliage parent must not change its shadow policy.
            piece.parent_water = parent_water
            for index in indices:
                face = part.faces[index]
                piece.anchor = part.anchors[index] if part.anchors is not None else None
                normals = [part.normals[i] for i in face] if part.normals is not None else None
                piece.face([part.verts[i] for i in face], part.mats[index], [part.uvs[i] for i in face], normals)
                if index in roles:
                    if not hasattr(piece, 'foliage_roles'):
                        piece.foliage_roles = {}
                    piece.foliage_roles[len(piece.faces) - 1] = roles[index]
            result[(*key, suffix)] = piece
    return result


def under_paving(x, y):
    """@cc [owner:fontanierh,label:correctness] brinecove-ground-under-flat-paving
    The highest the ground may stand at (x, y): just below any flat paving over it, else unbounded. Each fixed-z
    paving rectangle laid whole (modules.paving without skip, and the quay apron) MUST be registered in
    modules.FLAT_PAVING with its slab bottom, and every exported ground vertex inside a registered rectangle MUST
    stay at least 5 cm below its bottom, so terrain never pokes through or flickers on paving.
    """
    z = math.inf
    for x0, x1, y0, y1, bottom in modules.FLAT_PAVING:
        if x0 <= x <= x1 and y0 <= y <= y1:
            z = min(z, bottom - 0.05)
    return z


def collar_normals(builder, rim, normals, h=1.0):
    """Collar vertices take the eased ground's own gradient: the zipper's long fan triangles to the far-hills rim
    averaged only among themselves and shaded as bands (2026-10-19 capture, note 5)."""
    ox0, oy0, ox1, oy1 = R.OUTER
    memo = {}
    out = list(normals)
    for i, p in enumerate(builder.verts):
        x, y = p[0], p[1]
        if R.collar_weight(x, y) <= 0.0:
            continue
        key = (round(x, 2), round(y, 2))
        if key not in memo:
            xa, xb = max(ox0, x - h), min(ox1, x + h)
            ya, yb = max(oy0, y - h), min(oy1, y + h)
            gx = (R.ground(L.ground, rim, xb, y) - R.ground(L.ground, rim, xa, y)) / max(1e-3, xb - xa)
            gy = (R.ground(L.ground, rim, x, yb) - R.ground(L.ground, rim, x, ya)) / max(1e-3, yb - ya)
            m = math.sqrt(gx * gx + gy * gy + 1.0)
            memo[key] = (-gx / m, -gy / m, 1.0 / m)
        out[i] = memo[key]
    return out


def smooth_normals(builder, crease=0.5):
    """Per-vertex normals for a builder whose faces own their vertices: each corner averages the area-weighted
    normals of the faces meeting at its position that bend less than ~60 degrees from its own face.

    Without them the ground shades flat per triangle: the meadow slopes read as lit facets (playtest note 5)."""
    faces = []
    meet = {}
    for f in builder.faces:
        pts = [builder.verts[i] for i in f]
        nx = ny = nz = 0.0
        for (x0, y0, z0), (x1, y1, z1) in zip(pts, pts[1:] + pts[:1]):
            nx += (y0 - y1) * (z0 + z1)
            ny += (z0 - z1) * (x0 + x1)
            nz += (x0 - x1) * (y0 + y1)
        if nz < 0:  # a heightfield: every normal points up, whatever a face's winding
            nx, ny, nz = -nx, -ny, -nz
        faces.append((nx, ny, nz))
        for p in pts:
            meet.setdefault((round(p[0], 3), round(p[1], 3), round(p[2], 3)), []).append((nx, ny, nz))
    normals = [None] * len(builder.verts)
    for f, (nx, ny, nz) in zip(builder.faces, faces):
        length = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        own = (nx / length, ny / length, nz / length)
        for i in f:
            p = builder.verts[i]
            sx = sy = sz = 0.0
            for mx, my, mz in meet[(round(p[0], 3), round(p[1], 3), round(p[2], 3))]:
                m = math.sqrt(mx * mx + my * my + mz * mz) or 1.0
                if (mx * own[0] + my * own[1] + mz * own[2]) / m >= crease:
                    sx, sy, sz = sx + mx, sy + my, sz + mz
            s = math.sqrt(sx * sx + sy * sy + sz * sz)
            normals[i] = (sx / s, sy / s, sz / s) if s > 0 else own
    return normals


def area(points):
    """A planar polygon's area from its Newell normal."""
    points = list(points)
    nx = ny = nz = 0.0
    for (x0, y0, z0), (x1, y1, z1) in zip(points, points[1:] + points[:1]):
        nx += (y0 - y1) * (z0 + z1)
        ny += (z0 - z1) * (x0 + x1)
        nz += (x0 - x1) * (y0 + y1)
    return math.sqrt(nx * nx + ny * ny + nz * nz) / 2


def blender_materials():
    result = {}
    for name in L.COLORS:
        material = bpy.data.materials.new('BC_' + name)
        material.use_nodes = True
        result[name] = material
    return result


def mesh_object(builder, materials):
    used = sorted(set(builder.mats))
    index = {name: i for i, name in enumerate(used)}
    mesh = bpy.data.meshes.new(builder.name)
    mesh.from_pydata(builder.verts, [], builder.faces)
    uv_layer = mesh.uv_layers.new(name='UVMap')
    for loop in mesh.loops:
        uv_layer.data[loop.index].uv = builder.uvs[loop.vertex_index]
    for name in used:
        mesh.materials.append(materials[name])
    custom = builder.normals is not None
    for poly, mat in zip(mesh.polygons, builder.mats):
        poly.material_index = index[mat]
        poly.use_smooth = custom
    mesh.validate(verbose=False)
    mesh.update()
    if custom:
        normals = list(builder.normals)
        for poly in mesh.polygons:
            for v in poly.vertices:
                if normals[v] is None:
                    normals[v] = tuple(poly.normal)
        mesh.normals_split_custom_set_from_vertices(normals)
    obj = bpy.data.objects.new(builder.name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def export(obj, path):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.gltf(filepath=str(path), export_format='GLB', use_selection=True, export_apply=True,
                              export_yup=True, export_animations=False, export_skins=False, export_cameras=False,
                              export_lights=False, export_extras=False, export_normals=True,
                              export_image_format='NONE', export_materials='EXPORT')


def glb_info(path):
    """Triangle count, material slot names and bounds (local metres, z up) of an exported GLB."""
    doc, _ = glb_parts(path.read_bytes())
    triangles, low, high = 0, [math.inf] * 3, [-math.inf] * 3
    for mesh in doc['meshes']:
        for primitive in mesh['primitives']:
            triangles += doc['accessors'][primitive['indices']]['count'] // 3
            accessor = doc['accessors'][primitive['attributes']['POSITION']]
            # glTF is y up: (x, z, -y) in Blender's frame.
            (ax, ay, az), (bx, by, bz) = accessor['min'], accessor['max']
            for k, (lo, hi) in enumerate(((ax, bx), (-bz, -az), (ay, by))):
                low[k], high[k] = min(low[k], lo), max(high[k], hi)
    return triangles, [m['name'] for m in doc.get('materials', [])], [low, high]


def material_report(names):
    (OUT / 'textures').mkdir(parents=True, exist_ok=True)

    def texture_file(stem):
        texture = next((TEXTURES / f'{stem}{ext}' for ext in ('.png', '.jpg') if (TEXTURES / f'{stem}{ext}').exists()), None)
        if texture is None:
            return None
        file = f'T_BC_{stem}{texture.suffix}'
        shutil.copy2(texture, OUT / 'textures' / file)
        return file
    report = {}
    for name in sorted(names):
        hex_colour = L.COLORS.get(name, '#808080')
        colour = [srgb_to_linear(int(hex_colour[i:i + 2], 16)) for i in (1, 3, 5)]
        entry = {'name': 'MI_BC_' + name, 'colour': colour, 'texture': texture_file(TEXTURE.get(name, name)),
                 'kind': kind(name), 'pan': PAN_CM_S.get(name, 0.), 'motion': MOTION.get(name, {}),
                 'roughness': .3 if name.startswith('water') else .88, 'metal': name in ('metal', 'gold')}
        if entry['kind'] == 'terrain':
            # Layers in world space: no texture of its own; rock meshes use the rock layer alone, tinted.
            entry['texture'] = None
            entry['layers'] = {key: texture_file(stem) for key, stem in TERRAIN_LAYERS.items()}
            entry['normals'] = {key + 'N': texture_file(stem + '_n') for key, stem in TERRAIN_LAYERS.items()}
            entry['rock_only'] = name != 'terrain'
            entry['colour'] = [ROCK_TINT.get(name, 1.0)] * 3
        report[name] = entry
    return report

def hero_models(materials_out):
    """Each processed TRELLIS/Tripo model once, with its placements; its own textures become region textures."""
    entries, groups = [], []
    for slug, placements in hero_assets.placements(modules.HULL).items():
        obj = hero_assets.import_model(slug)
        if obj is None:
            raise SystemExit(f'Brinecove: hero model {slug} has no mesh')
        name = 'SM_BC_Hero_' + ''.join(part.title() for part in slug.split('-'))
        obj.name = name
        slots = []
        for k, material in enumerate(obj.data.materials):
            key = f'hero_{slug}_{k}'
            image = next((node.image for node in material.node_tree.nodes if node.type == 'TEX_IMAGE' and node.image), None)
            file = None
            colour = [1., 1., 1.]
            if image is not None:
                file = f'T_BC_{key}.png'
                image.file_format = 'PNG'
                image.save(filepath=str(OUT / 'textures' / file))  # the glTF importer packs its images
            else:
                # A palette slot without a texture (rope, flag red) carries its colour as the base colour factor.
                # Writing white here rendered those slots pure white: on the cannon a third of its triangles,
                # scattered through the iron and oak as white confetti (playtest note 8).
                bsdf = next((n for n in material.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
                if bsdf is not None:
                    colour = [float(c) for c in bsdf.inputs['Base Color'].default_value[:3]]
            materials_out[key] = {'name': 'MI_BC_' + key, 'colour': colour, 'texture': file, 'kind': 'opaque',
                                  'pan': 0., 'roughness': .8, 'metal': False}
            material.name = 'BC_' + key
            slots.append(key)
        path = OUT / 'glb' / f'{name}.glb'
        export(obj, path)
        triangles, names, bounds = glb_info(path)
        entries.append({'name': name, 'path': path.relative_to(OUT).as_posix(), 'sha256': sha(path), 'triangles': triangles,
                        'bounds_m': bounds, 'slots': [n[3:] for n in names], 'collision': True})
        transforms = [transform(x, y, z, yaw, scale, pitch) for x, y, z, yaw, scale, pitch in placements]
        groups.append(group(name, [n[3:] for n in names], transforms, collision=True, shadow=True, cull_cm=60000))
    return entries, groups


def transform(x, y, z, yaw=0.0, scale=1.0, pitch=0.0):
    """Unreal transform relative to the region origin from local metres and Blender degrees.

    Unreal's y is Blender's -y, so a turn about z by yaw becomes -yaw; pitch turns about local x first."""
    hy, hp = math.radians(-yaw) / 2, math.radians(-pitch) / 2
    qz = (0., 0., math.sin(hy), math.cos(hy))
    qx = (math.sin(hp), 0., 0., math.cos(hp))
    x1, y1, z1, w1 = qz
    x2, y2, z2, w2 = qx
    q = (w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2, w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
         w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2, w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2)
    return {'translation_cm': [round(x * 100, 1), round(-y * 100, 1), round(z * 100, 1)],
            'rotation_xyzw': [round(c, 5) for c in q], 'scale': [round(scale, 3)] * 3}  # runtime.json carries ~10^5 of these


def group(name, slots, transforms, *, collision, shadow, cull_cm):
    return {'asset': f'{ROOT}/Meshes/{name}.{name}', 'materials': [f'{ROOT}/Materials/MI_BC_{s}.MI_BC_{s}' for s in slots],
            'plant': False, 'collision': collision, 'shadow': shadow, 'cull_cm': cull_cm, 'transforms': transforms}


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-library', type=Path, default=hero_sources.LIBRARY)
    if argv is None:
        argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    args = parser.parse_args(argv)
    started = time.time()
    try:
        heroes = hero_sources.verify(args.source_library)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    missing = set(hero_assets.placements(modules.HULL)) - set(heroes)
    if not modules.HAS_HULL or missing:
        raise SystemExit(f'Brinecove: the hero hull or selected models are not committed: {sorted(missing)}')
    (OUT / 'glb').mkdir(parents=True, exist_ok=True)
    for stale in (OUT / 'glb').glob('*.glb'):
        stale.unlink()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    materials = blender_materials()
    meshes, groups, used = [], [], set()
    rim_shape, rim_world = rim()
    terrain, seam = ground.build(rim_shape, rim_world)
    settled = settle(rim_shape)
    # Dressing that must meet the real ground (shore foam) samples the eased collar, not the layout under it.
    def final_ground(x, y):
        eased = settled(x, y)[1]
        return eased if eased is not None else L.ground(x, y)

    rocks.FINAL = final_ground
    if terrain.normals is None:
        terrain.normals = collar_normals(terrain, rim_shape, smooth_normals(terrain))
    print(f'ground: {seam}; {time.time() - started:.0f}s', flush=True)
    sources = [('Ground', terrain)] + [(name, fn()) for name, fn in MODULES]
    report_outside, report_drowned, report_degenerate = {}, {}, {}
    for prefix, builder in sources:
        parts, outside, drowned, degenerate = split(builder, prefix, None if prefix == 'Ground' else settled,
                                                    GROUND_REMAP if prefix == 'Ground' else None)
        report_outside[prefix] = outside
        report_drowned[prefix] = drowned
        report_degenerate[prefix] = degenerate
        for (_, _, is_soft, _), part in sorted(parts.items()):
            obj = mesh_object(part, materials)
            path = OUT / 'glb' / f'{part.name}.glb'
            export(obj, path)
            bpy.data.objects.remove(obj, do_unlink=True)
            triangles, names, bounds = glb_info(path)
            slots = [n[3:] for n in names]
            used.update(slots)
            water = getattr(part, 'parent_water',
                            all(s.startswith(('water', 'mist', 'spray', 'foam', 'waterfall')) for s in slots))
            meshes.append({'name': part.name, 'path': path.relative_to(OUT).as_posix(), 'sha256': sha(path),
                           'triangles': triangles, 'bounds_m': bounds, 'slots': slots, 'collision': not is_soft})
            groups.append(group(part.name, slots, [IDENTITY], collision=not is_soft, shadow=not water,
                                cull_cm=0 if prefix in ('Ground', 'Rocks') else 120000))
        print(f'{prefix}: {len(parts)} parts, {sum(len(f) - 2 for f in builder.faces)} triangles; '
              f'{time.time() - started:.0f}s', flush=True)
    material_entries = material_report(used)
    hero_meshes, hero_groups = hero_models(material_entries)
    meshes += hero_meshes
    groups += hero_groups
    # Foliage: each species prototype once, its placements as instances.
    protos = flora.prototypes()
    placements, scrub = {}, {}
    cover = flora.groundcover(rocks.ground)
    print(f'groundcover: {len(cover)} instances', flush=True)
    for proto, x, y, z, yaw, scale in cover:
        # The slope scrub (flora.groundcover's doubled clumps) is seen from the beach below: it keeps a longer cull.
        (scrub if scale > 1.5 else placements).setdefault(proto, []).append(transform(x, y, z, yaw, scale))
    for proto, x, y, z, yaw, scale in flora.scatter() + flora.bloom_spots(random.Random(5)):
        dz, g = settled(x, y)
        if g is not None and g < 0.4:
            continue  # the eased ground is under the sea here
        placements.setdefault(proto, []).append(transform(x, y, z + dz, yaw, scale))
    for proto, builder in protos.items():
        if proto not in placements and proto not in scrub:
            continue
        builder.name = 'SM_BC_Plant_' + ''.join(part.title() for part in proto.split('_'))
        obj = mesh_object(builder, materials)
        path = OUT / 'glb' / f'{builder.name}.glb'
        export(obj, path)
        bpy.data.objects.remove(obj, do_unlink=True)
        triangles, names, bounds = glb_info(path)
        slots = [n[3:] for n in names]
        for s in slots:
            if s not in material_entries:
                material_entries.update(material_report({s}))
        height = bounds[1][2] - bounds[0][2]
        meshes.append({'name': builder.name, 'path': path.relative_to(OUT).as_posix(), 'sha256': sha(path),
                       'triangles': triangles, 'bounds_m': bounds, 'slots': slots, 'collision': False, 'lods': True})
        low = proto.startswith('cover_')
        if proto in placements:
            groups.append(group(builder.name, slots, placements[proto], collision=False, shadow=not low,
                                cull_cm=5000 if low else 24000 if height < 4 else 60000))
        if proto in scrub:
            groups.append(group(builder.name, slots, scrub[proto], collision=False, shadow=False, cull_cm=9000))
    quay_z = float(L.ground(R.QUAY_STOP[0] - R.ORIGIN[0], R.QUAY_STOP[1] - R.ORIGIN[1])) + 1.0
    runtime = {'version': 1,
               'origin_cm': [R.ORIGIN[0] * 100., -R.ORIGIN[1] * 100., R.ORIGIN[2] * 100.],
               'bounds_m': list(R.OUTER_WORLD), 'clearance_m': list(R.OUTER_WORLD),
               # Coastal dressing's boulders line the old shore, which now runs through the cove.
               'clear_prefixes': ['SW_Boulder'], 'groups': groups, 'signs': [],
               'zones': [{'key': 'brinecove_quay', 'name': 'Brinecove · quay', 'x': R.QUAY_STOP[0],
                          'y': R.QUAY_STOP[1], 'z': quay_z, 'yaw': -90.,
                          'hint': 'The pirate port in the western reach: market, galleons and the waterfall'}]}
    (OUT / 'runtime.json').write_text(json.dumps(runtime, separators=(',', ':')) + '\n')
    report = {'meshes': meshes, 'materials': material_entries, 'seam': seam, 'outside_faces': report_outside,
              'drowned_faces': report_drowned, 'degenerate_faces': report_degenerate,
              'triangles': sum(m['triangles'] for m in meshes),
              'instances': sum(len(g['transforms']) for g in groups)}
    (OUT / 'build-report.json').write_text(json.dumps(report, indent=1) + '\n')
    print(f'BRINECOVE GAME BUILD COMPLETE: {len(meshes)} meshes, {len(groups)} groups, {report["triangles"]} unique '
          f'triangles, {report["instances"]} instances; {time.time() - started:.0f}s', flush=True)


if __name__ == '__main__':
    main()
