"""Crater Park v2 export step (world.craterpark): geometry.npz -> FBX, build.json and park.json, for the unchanged
Unreal importer (unreal/Scripts/import_craterpark.py) and ASuperUltraMegaPark::Spawn (plan/pipeline.md 2).

Run with Blender for main(): FBX writing is the only thing bpy does here. line_npz() is bpy-free (generate.py uses it).
The contract kept byte-compatible with r4: build.json {scene_sha256, render[], collision[]} with r4's entry key sets,
SM_CP_* / UC_CP_* names, material ids, the SM_CP_ImportSeed FBX, park.json's key set, cp_lip_### rails, spawn on the
marked drop-in.
"""
import hashlib
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))        # world/regions
sys.path.insert(0, str(HERE.parents[2]))        # world

import numpy as np  # noqa: E402

from craterpark.v2 import dsl, v4_config  # noqa: E402

MESH_ROOT = '/Game/CraterPark/Meshes'
FOLDED = 2e-7           # square metres (twice a face's area): a face flatter than this is never exported
RENDER_KEYS = ('name', 'fbx', 'sha256', 'native_origin', 'bounds', 'vertices', 'triangles', 'materials', 'source_id',
               'role', 'skipped', 'covered', 'occlusion_mean')
COLLISION_KEYS = ('name', 'fbx', 'sha256', 'native_origin', 'bounds', 'vertices', 'triangles', 'materials',
                  'source_triangles', 'role', 'one_sided')
PARK_KEYS = ('source_sha256', 'name', 'mesh_root', 'rails_required', 'location_cm', 'yaw_deg', 'placement', 'render',
             'collision', 'rails', 'spawn')     # plus `lines` (designed lines) and `trees` (dressing.plant) when present


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ue(point):
    return [point[0] * 100., point[2] * 100., point[1] * 100.]


def native_to_blender(values):
    result = np.asarray(values, 'f8')[:, [0, 2, 1]].copy()
    result[:, 1] *= -1
    return result


def origin_of(vertices):
    """The FBX's local origin: the bounds' centre on a 32 m grid (as r4)."""
    v = np.asarray(vertices, 'f8')
    return np.round((v.min(axis=0) + v.max(axis=0)) / 2 / 32) * 32


def line_npz(mesh, line, path):
    """One designed line's collision for park-assist's line validator (v2_chat coordinator 23:23): every collidable
    face of the park, native y-up metres, in the mesh's own (stable) face order, with per-face feature names and tags
    (takeoff / landing masks), the line's path polyline, spawn pose, finish point and entry-speed range."""
    collidable = np.isin(mesh.role, [dsl.ROLE[r] for r in dsl.COLLISION_ROLE])
    sub = mesh.subset(collidable)
    np.savez(path, triangles=sub.triangles().astype('f8'), face_feature=sub.feature.astype('i4'),
             features=np.asarray(sub.features, 'U'), face_tag=sub.tag.astype('i4'), tags=np.asarray(dsl.TAGS, 'U'),
             takeoff=sub.tag == dsl.TAG['takeoff'], landing=sub.tag == dsl.TAG['landing'],
             face_role=np.asarray(dsl.ROLES, 'U')[sub.role], line=np.asarray(line.name),
             line_features=np.asarray(line.features, 'U'), path=line.path,
             spawn_position=np.asarray(line.spawn[0], 'f8'), spawn_yaw_deg=np.float64(line.spawn[1]),
             finish=np.asarray(line.finish, 'f8'), entry_speed=np.asarray(line.entry_speed, 'f8'),
             airs=np.asarray(json.dumps([list(a) for a in line.airs])))
    return path


def mesh_object(out, name, vertices, faces, materials, face_materials, uvs=None, normals=None, ao=None, *, native_origin=None):
    """An FBX about a local origin on a 32 m grid, native units, Y up (craterpark/build.py export_mesh), with the
    analytic per-vertex `normals` as custom split normals. Returns its build.json entry (r4's common keys)."""
    import bpy
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    vertices = np.asarray(vertices, 'f8'); faces = np.asarray(faces, 'i8')
    origin = origin_of(vertices[np.unique(faces)]) if native_origin is None else np.asarray(native_origin, 'f8')
    if origin.shape != (3,) or not np.isfinite(origin).all():
        raise ValueError('Invalid canonical park origin')
    t = vertices[faces] - origin
    flat = np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1) <= FOLDED
    if flat.any():          # generate.py drops these already; never let one reach the importer's triangle check
        faces, face_materials = faces[~flat], np.asarray(face_materials)[~flat]
    data = bpy.data.meshes.new(name)
    data.from_pydata(native_to_blender(vertices - origin).tolist(), [], faces.tolist())
    data.update()
    for key in materials:
        data.materials.append(bpy.data.materials.get(key) or bpy.data.materials.new(key))
    data.polygons.foreach_set('material_index', np.asarray(face_materials, dtype='i4'))
    if uvs is not None:
        loops = np.empty(len(data.loops), dtype='i4')
        data.loops.foreach_get('vertex_index', loops)
        uv = np.asarray(uvs, 'f8').copy(); uv[:, 1] = 1 - uv[:, 1]
        data.uv_layers.new(name='UVMap').data.foreach_set('uv', uv[loops].ravel())
    if ao is not None:
        colour = data.color_attributes.new(name='Color', type='FLOAT_COLOR', domain='POINT')
        rgba = np.repeat(np.asarray(ao, 'f4')[:, None], 4, 1); rgba[:, 3] = 1.
        colour.data.foreach_set('color', rgba.ravel())
    data.shade_smooth()
    if normals is not None:
        data.normals_split_custom_set_from_vertices(native_to_blender(normals).tolist())
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    used = vertices[np.unique(faces)]
    lo, hi = used.min(axis=0), used.max(axis=0)
    result = {'name': name, 'fbx': f'fbx/{name}.fbx', 'sha256': None, 'native_origin': origin.tolist(),
              'bounds': {'minimum': lo.tolist(), 'maximum': hi.tolist()}, 'vertices': len(vertices),
              'triangles': len(faces), 'materials': list(materials)}
    return obj, result


def export_mesh(out, name, vertices, faces, materials, face_materials, uvs=None, normals=None, ao=None):
    import bpy
    obj, result = mesh_object(out, name, vertices, faces, materials, face_materials, uvs, normals, ao)
    path = Path(out) / 'fbx' / f'{name}.fbx'
    from atelier.blender.fbx import export_fbx as export_scene_fbx
    export_scene_fbx(filepath=str(path), use_selection=True, object_types={'MESH'},
                             apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', global_scale=1.,
                             axis_forward='-Z', axis_up='Y', use_mesh_modifiers=False, mesh_smooth_type='FACE',
                             use_tspace=uvs is not None, bake_anim=False, add_leaf_bones=False, path_mode='STRIP',
                             colors_type='SRGB')
    result['sha256'] = sha(path)
    bpy.data.meshes.remove(obj.data, do_unlink=True)
    return result

ZONE_PAD = 200.     # cm round each capped launch ramp


def assist_boxes(zones, placement):
    """Editor launch ramps with a vert assist cap -> oriented boxes in island centimetres (yaw about +Z), grown
    by ZONE_PAD so the rider is inside from the ramp's foot to its lip, and through its full height."""
    boxes = []
    for zone in zones:
        pts = np.asarray(placement.to_unreal(np.asarray(zone['points'], 'f8')), 'f8')
        axis = pts[-1, :2] - pts[0, :2]
        yaw = math.atan2(axis[1], axis[0])
        c, s = math.cos(yaw), math.sin(yaw)
        local = np.stack([pts[:, 0] * c + pts[:, 1] * s, -pts[:, 0] * s + pts[:, 1] * c], 1)
        lo, hi = local.min(0), local.max(0)
        mid = (lo + hi) / 2
        centre = [mid[0] * c - mid[1] * s, mid[0] * s + mid[1] * c, (pts[:, 2].min() + pts[:, 2].max()) / 2]
        half = [(hi[0] - lo[0]) / 2 + ZONE_PAD, zone['half_width'] * 100 + ZONE_PAD,
                (pts[:, 2].max() - pts[:, 2].min()) / 2 + 3 * ZONE_PAD]
        boxes.append({'id': zone['id'], 'center_cm': [round(v, 1) for v in centre], 'half_extent_cm': [round(v, 1) for v in half],
                      'yaw_deg': round(math.degrees(yaw), 3), 'vert_assist_max': zone['vert_assist_max']})
    return boxes


BOOST_PAD = 100.    # cm round each boost box, so the board on the coping and a rider leaning out are inside


def boost_boxes(zones, placement):
    """Editor boost zones (a bowl or a run cut along its length, as its own mesh points) -> boxes in island
    centimetres turned yaw_deg about +Z along the points' long axis, grown by BOOST_PAD. The skating applies the
    boost only on a tilted surface (a transition) inside one, so the flat a box takes in does not boost."""
    boxes = []
    for zone in zones:
        pts = np.asarray(placement.to_unreal(np.asarray(zone['points'], 'f8')), 'f8')
        xy = pts[:, :2] - pts[:, :2].mean(0)
        w, v = np.linalg.eigh(xy.T @ xy)
        yaw = math.atan2(v[1, -1], v[0, -1])
        c, s = math.cos(yaw), math.sin(yaw)
        local = np.stack([pts[:, 0] * c + pts[:, 1] * s, -pts[:, 0] * s + pts[:, 1] * c], 1)
        lo, hi = local.min(0), local.max(0)
        mid = (lo + hi) / 2
        centre = [mid[0] * c - mid[1] * s, mid[0] * s + mid[1] * c, (pts[:, 2].min() + pts[:, 2].max()) / 2]
        half = [(hi[0] - lo[0]) / 2 + BOOST_PAD, (hi[1] - lo[1]) / 2 + BOOST_PAD,
                (pts[:, 2].max() - pts[:, 2].min()) / 2 + 2 * BOOST_PAD]
        boxes.append({'id': zone['id'], 'center_cm': [round(float(x), 1) for x in centre],
                      'half_extent_cm': [round(float(x), 1) for x in half], 'yaw_deg': round(math.degrees(yaw), 3),
                      'boost': zone['boost']})
    return boxes


def validate_geometry(index):
    """Keep the existing structural/support admission before every atomic projection."""
    provenance = None
    if v4_config.selected():
        provenance = v4_config.provenance()
        if index.get('v4') != provenance:
            raise ValueError('v4 geometry does not match the selected design and inputs; rebuild geometry')
        validation = index.get('validation', {})
        # the owner's editor park (ATELIER_CRATERPARK_EDITOR_PARK): built without supports for a playtest, by choice
        playtest = v4_config.editor() and index.get('editor_playtest') and index.get('lines')
        cosmetic_preview = validation.get('preview') and validation.get('failed') and all(
            name in ('outlines', 'facets', 'uv_stretch', 'slivers') for name in validation['failed'])
        if not playtest and (not index.get('accepted') or not validation.get('ran')
                             or not (validation.get('ok') or cosmetic_preview)):
            raise ValueError('v4 geometry has not passed structural validation; diagnostic artifacts cannot export')
        if not playtest and (not validation.get('supports', {}).get('ran') or not validation['supports'].get('ok')):
            raise ValueError('v4 geometry has not passed actual support and ride envelope checks')
        if not index.get('lines'):
            raise ValueError('v4 geometry has no checked tower starts')
    elif index.get('v4'):
        raise ValueError('v4 geometry requires its explicit design selection; rebuild old geometry')
    return provenance


def write_metadata(out, source, geometry, placement, build, index, provenance):
    """Write placements/course/query metadata only; never construct or join render geometry."""
    out = Path(out)
    t = placement.unreal_transform()
    ground = None if provenance else json.loads((source / 'drop-in.json').read_text())['groundPosition']
    rails = []
    for i, spec in enumerate(index['rails']):
        points = np.asarray(geometry[f'rail{i}'], 'f8')
        rails.append({'id': f'cp_lip_{i:03d}', 'closed': bool(spec['closed']), 'points_cm': [ue(p) for p in points.tolist()]})
    if provenance:
        bounds = np.asarray(index.get('bounds_native'), 'f8')
        if bounds.shape != (2, 3) or not np.isfinite(bounds).all() or np.any(bounds[1] < bounds[0]):
            raise ValueError('v4 geometry requires finite native bounds')
        corners = np.asarray([[bounds[i, 0], bounds[j, 1], bounds[k, 2]]
                              for i in range(2) for j in range(2) for k in range(2)])
        world = corners[:, [0, 2, 1]] * 100.
        angle = np.radians(t['yaw_deg'])
        world[:, :2] = world[:, :2] @ np.asarray([[np.cos(angle), np.sin(angle)],
                                                [-np.sin(angle), np.cos(angle)]])
        world += np.asarray(t['location_cm'])
        island = world * np.asarray([.01, -.01, .01])
        start = np.asarray(index['lines'][0]['spawn']['location_cm']) * np.asarray([.01, -.01, .01])
        summary = {'version': 4, 'bounds_native': bounds.tolist(), 'bounds_min': island.min(0).tolist(),
                   'bounds_max': island.max(0).tolist(), 'drop_in': start.tolist(), 'unreal': t,
                   'provenance': provenance}
    else:
        summary = placement.summary()
    park = {'source_sha256': build['scene_sha256'], 'name': 'CRATERPARK', 'mesh_root': MESH_ROOT, 'rails_required': True,
            'location_cm': t['location_cm'], 'yaw_deg': t['yaw_deg'], 'placement': summary,
            'render': [{'name': e['name'], 'origin_cm': ue(e['native_origin'])} for e in build['render']],
            'collision': [{'name': e['name'], 'origin_cm': ue(e['native_origin'])} for e in build['collision']],
            'rails': rails, 'spawn': (dict(index['lines'][0]['spawn']) if provenance else
                                   {'location_cm': placement.to_unreal(ground).tolist(), 'yaw_deg': t['yaw_deg']})}
    if provenance:
        park['v4'] = provenance
        park['source_sha256'] = provenance['source_sha256']
    if any(index.get('trees', {}).values()):
        park['trees'] = index['trees']           # the park's own planting (dressing.plant), Spawn's HISM path
    if index.get('assist_zones_native'):
        park['assist_zones'] = assist_boxes(index['assist_zones_native'], placement)
    if index.get('boost_zones_native'):
        park['boost_zones'] = boost_boxes(index['boost_zones_native'], placement)
    if index.get('lines'):
        # one start per designed line (generate.line_spawns, CraterParkTower.cpp); the first is the hero line
        park['lines'] = index['lines']
        park['spawn'] = dict(index['lines'][0]['spawn'])
    if provenance and v4_config.provenance() != provenance:
        raise ValueError('v4 inputs changed during export; refusing to publish mixed design metadata')
    for name, data in (('build.json', build), ('park.json', park)):
        temporary = out / (name + '.tmp')
        temporary.write_text(json.dumps(data, indent=1 if name == 'build.json' else None) + '\n')
        temporary.replace(out / name)
    return build, park


def write(out, source, geometry, placement, entry_mesh=export_mesh):
    """Every FBX, build.json and park.json under `out` from the arrays in `geometry` (generate.bundle's npz)."""
    out = Path(out); (out / 'fbx').mkdir(parents=True, exist_ok=True)
    # mesh files this build does not make are removed, so no stale r4 FBX lies next to the new ones
    index = json.loads(str(geometry['index']))
    provenance = validate_geometry(index)
    build = {'scene_sha256': sha(source / 'scene.json'), 'render': [], 'collision': []}
    if provenance:
        build['v4'] = provenance
    for i, spec in enumerate(index['render']):
        mesh = dsl.Mesh.from_arrays(geometry, f'r{i}_')
        materials = [dsl.MATERIALS[int(m)] for m in np.unique(mesh.material)]
        local = np.searchsorted(np.unique(mesh.material), mesh.material)
        entry = entry_mesh(out, spec['name'], mesh.V, mesh.F, materials, local, mesh.UV, mesh.N, mesh.AO)
        entry.update(source_id=spec['name'][6:], role=spec['role'], skipped=0, covered=0,
                     occlusion_mean=round(float(mesh.AO.mean()), 4) if len(mesh.AO) else 1.)
        build['render'].append({k: entry[k] for k in RENDER_KEYS})
    for i, spec in enumerate(index['collision']):
        t = np.asarray(geometry[f'c{i}'], 'f8')
        vertices, faces = t.reshape(-1, 3), np.arange(len(t) * 3).reshape(-1, 3)
        entry = entry_mesh(out, spec['name'], vertices, faces, ['M_Collision'], np.zeros(len(faces), 'i4'))
        entry.update(source_triangles=len(t), role=spec['role'], one_sided=False)
        build['collision'].append({k: entry[k] for k in COLLISION_KEYS})
    entry_mesh(out, 'SM_CP_ImportSeed', np.asarray([[0, 0, 0], [1, 0, 0], [0, 0, 1]], 'f8'), np.asarray([[0, 2, 1]]),
               ['M_Collision'], [0], np.asarray([[0, 0], [1, 0], [0, 1]], 'f8'))
    keep = {e['name'] for e in build['render'] + build['collision']} | {'SM_CP_ImportSeed'}
    for stale in (out / 'fbx').glob('*.fbx'):
        if stale.stem not in keep:
            stale.unlink()
    return write_metadata(out, source, geometry, placement, build, index, provenance)


def main():
    import yori
    from craterpark import placement
    out = yori.OUT / 'craterpark'
    geometry = np.load(out / 'v2' / 'geometry.npz')
    build, park = write(out, placement.SOURCE, geometry, placement)
    print('CRATERPARK BUILD COMPLETE', len(build['render']), 'render', len(build['collision']), 'collision',
          sum(e['triangles'] for e in build['render']), 'render triangles', flush=True)


if __name__ == '__main__':
    main()
