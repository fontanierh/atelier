"""Build Crater Park's Unreal interchange files from the committed library arrays (docs/CRATERPARK.md).

Run with Blender. Every mesh except the helpers is kept, with no simplification:
- render: one mesh per source mesh, without the faces its `render_skip` hides (coplanar flicker), smoothed only
  across edges under SMOOTH degrees;
- collision: every face of each role, the hidden ones included, in sections of at most SECTION triangles.
park.json places them on the caldera floor for ASuperUltraMegaPark::Spawn (placement.py).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yori
from craterpark import placement

import bpy
import hashlib
import json
import math
import numpy as np

SOURCE = placement.SOURCE
OUT = yori.OUT / 'craterpark'
MESH_ROOT = '/Game/CraterPark/Meshes'
SMOOTH = 35.0           # degrees: sharper edges keep their crease
SECTION = 200000        # collision triangles per mesh


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def native_to_blender(values):
    result = np.asarray(values)[:, [0, 2, 1]].copy()
    result[:, 1] *= -1
    return result


def ue(point):
    return [point[0] * 100., point[2] * 100., point[1] * 100.]


def export_mesh(name, vertices, faces, materials, face_materials, uvs=None):
    """As megapark/build.py export_mesh: an FBX about a local origin on a 32 m grid, native units, Y up."""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    origin = np.round((vertices.min(axis=0).astype('f8') + vertices.max(axis=0)) / 2 / 32) * 32
    data = bpy.data.meshes.new(name)
    data.from_pydata(native_to_blender(vertices.astype('f8') - origin).tolist(), [], faces.tolist())
    data.update()
    for key in materials:
        data.materials.append(bpy.data.materials.get(key) or bpy.data.materials.new(key))
    data.polygons.foreach_set('material_index', np.asarray(face_materials, dtype='i4'))
    if uvs is not None:
        loops = np.empty(len(data.loops), dtype='i4')
        data.loops.foreach_get('vertex_index', loops)
        uv = uvs.copy(); uv[:, 1] = 1 - uv[:, 1]
        data.uv_layers.new(name='UVMap').data.foreach_set('uv', uv[loops].ravel())
        data.shade_smooth()
        data.set_sharp_from_angle(angle=math.radians(SMOOTH))
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    path = OUT / 'fbx' / f'{name}.fbx'
    bpy.ops.export_scene.fbx(filepath=str(path), use_selection=True, object_types={'MESH'},
        apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', global_scale=1.,
        axis_forward='-Z', axis_up='Y', use_mesh_modifiers=False, mesh_smooth_type='OFF' if uvs is not None else 'FACE',
        use_tspace=uvs is not None, bake_anim=False, add_leaf_bones=False, path_mode='STRIP')
    lo, hi = vertices.min(axis=0), vertices.max(axis=0)
    result = {'name': name, 'fbx': f'fbx/{name}.fbx', 'sha256': sha(path), 'native_origin': origin.tolist(),
              'bounds': {'minimum': lo.tolist(), 'maximum': hi.tolist()}, 'vertices': len(vertices), 'triangles': len(faces),
              'materials': materials}
    bpy.data.meshes.remove(data, do_unlink=True)
    return result


def valid(positions, triangles):
    t = positions[triangles].astype('f8')
    return np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1) > 1e-12


def main():
    (OUT / 'fbx').mkdir(parents=True, exist_ok=True)
    scene = placement.scene()
    report = {'scene_sha256': sha(SOURCE / 'scene.json'), 'render': [], 'collision': []}
    sections = {}
    for entry in placement.meshes():
        assert sha(SOURCE / entry['npz']) == entry['sha256'], entry['npz']
        a = placement.arrays(entry)
        keep = valid(a['positions'], a['triangles'])
        sections.setdefault(entry['role'], []).append(a['positions'][a['triangles'][keep]])
        keep[a['render_skip']] = False
        used = np.unique(a['triangles'][keep])
        remap = np.full(len(a['positions']), -1, 'i8'); remap[used] = np.arange(len(used))
        mesh = export_mesh('SM_CP_' + entry['id'].replace('-', '_'), a['positions'][used], remap[a['triangles'][keep]],
                           [entry['material']], np.zeros(int(keep.sum()), 'i4'), a['uvs'][used])
        mesh.update(source_id=entry['id'], role=entry['role'], skipped=int(len(keep) - keep.sum()))
        report['render'].append(mesh)
        print('Exported', mesh['name'], flush=True)
    for role, parts in sections.items():
        triangles = np.concatenate(parts)
        for k in range(0, len(triangles), SECTION):
            chunk = triangles[k:k + SECTION]
            vertices = chunk.reshape(-1, 3)
            entry = export_mesh(f'UC_CP_{role}_{k // SECTION}', vertices, np.arange(len(vertices)).reshape(-1, 3),
                                ['M_Collision'], np.zeros(len(chunk), 'i4'))
            entry.update(role=role, one_sided=False)
            report['collision'].append(entry)
    # Seed the FBX factory's safe reimport route with a clean triangle (import_craterpark.py).
    export_mesh('SM_CP_ImportSeed', np.asarray([[0, 0, 0], [1, 0, 0], [0, 0, 1]], 'f4'), np.asarray([[0, 2, 1]]),
                ['M_Collision'], [0], np.asarray([[0, 0], [1, 0], [0, 1]], 'f4'))
    (OUT / 'build.json').write_text(json.dumps(report, indent=1) + '\n')
    t = placement.unreal_transform()
    # The marked ramp drop-in; the rider starts there facing the park's native +x.
    ground = json.loads((SOURCE / 'drop-in.json').read_text())['groundPosition']
    park = {'source_sha256': report['scene_sha256'], 'name': 'CRATERPARK', 'mesh_root': MESH_ROOT, 'rails_required': False,
            'location_cm': t['location_cm'], 'yaw_deg': t['yaw_deg'], 'placement': placement.summary(),
            'render': [{'name': e['name'], 'origin_cm': ue(e['native_origin'])} for e in report['render']],
            'collision': [{'name': e['name'], 'origin_cm': ue(e['native_origin'])} for e in report['collision']],
            'rails': [], 'spawn': {'location_cm': placement.to_unreal(ground).tolist(), 'yaw_deg': t['yaw_deg']}}
    (OUT / 'park.json').write_text(json.dumps(park) + '\n')
    print('CRATERPARK BUILD COMPLETE', len(report['render']), 'render', len(report['collision']), 'collision',
          scene['counts'], flush=True)


if __name__ == '__main__':
    main()
