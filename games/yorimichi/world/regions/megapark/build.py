"""Build ordinary Unreal static-mesh interchange files from bundled map arrays.

Run with Blender. There is no game-data decoder in this stage. Render geometry
and authoritative riding collision stay separate, and neither is simplified.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori

import bpy
import hashlib
import json
import struct
import zlib
import numpy as np

SOURCE = yori.ASSETS / 'megapark'
OUT = yori.OUT / 'megapark'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_fallbacks():
    # Exact linear normal pixel, without depending on Blender's view transform.
    def chunk(kind, data):
        return struct.pack('>I', len(data))+kind+data+struct.pack('>I', zlib.crc32(kind+data))
    for name, pixel in {'white': (255,255,255,255), 'black': (0,0,0,255), 'normal': (128,128,255,255)}.items():
        data = b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('>2I5B',1,1,8,6,0,0,0))
        data += chunk(b'IDAT', zlib.compress(b'\0'+bytes(pixel)))+chunk(b'IEND', b'')
        (OUT/f'{name}.png').write_bytes(data)


def material_key(part):
    # Name is a provenance label; the draw parameters and channel bindings
    # determine whether two source parts may share one Unreal material.
    parameters = {key: values for key, values in part.get('retail_parameters', {}).items()
                  if key not in ('Name',)}
    identity = [part.get('shader_name'), part.get('retail_texture_ids'), parameters,
                part.get('alpha_mode'), part.get('alpha_cutoff')]
    return 'M_' + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]


def native_to_blender(values):
    result = np.asarray(values)[:, [0, 2, 1]].copy()
    result[:, 1] *= -1
    return result


def export_mesh(name, vertices, faces, materials, face_materials, channels=None, normals=None):
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    # A local origin makes each source chunk straightforward to select/move.
    # Keep source float words in the committed arrays; validate imported world bounds.
    origin = np.round((vertices.min(axis=0).astype('f8') + vertices.max(axis=0)) / 2 / 32) * 32
    local = native_to_blender(vertices.astype('f8') - origin)
    data = bpy.data.meshes.new(name)
    data.from_pydata(local.tolist(), [], faces.tolist())
    data.update()
    for key in materials:
        material = bpy.data.materials.get(key) or bpy.data.materials.new(key)
        data.materials.append(material)
    if len(face_materials):
        data.polygons.foreach_set('material_index', np.asarray(face_materials, dtype='i4'))
    loops = np.empty(len(data.loops), dtype='i4')
    data.loops.foreach_get('vertex_index', loops)
    for key, values in (channels or {}).items():
        layer = data.uv_layers.new(name=key)
        uv = values.copy(); uv[:, 1] = 1 - uv[:, 1]
        layer.data.foreach_set('uv', uv[loops].ravel())
    if normals is not None:
        data.polygons.foreach_set('use_smooth', np.ones(len(data.polygons), dtype=bool))
        data.normals_split_custom_set_from_vertices(native_to_blender(normals).tolist())
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    path = OUT / 'fbx' / f'{name}.fbx'
    bpy.ops.export_scene.fbx(filepath=str(path), use_selection=True, object_types={'MESH'},
        apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', global_scale=1.,
        axis_forward='-Z', axis_up='Y', use_mesh_modifiers=False, mesh_smooth_type='FACE',
        use_tspace=bool(channels), bake_anim=False, add_leaf_bones=False, path_mode='STRIP')
    lo, hi = vertices.min(axis=0), vertices.max(axis=0)
    result = {'name': name, 'fbx': f'fbx/{name}.fbx', 'sha256': sha(path),
        'native_origin': origin.tolist(), 'bounds': {'minimum': lo.tolist(), 'maximum': hi.tolist()},
        'vertices': len(vertices), 'triangles': len(faces), 'materials': materials}
    bpy.data.meshes.remove(data, do_unlink=True)
    return result


def sample_rail(rail):
    """Bound chord error by subdividing the original cubic's Bezier controls."""
    points = []
    def split(control, depth=0):
        a, b, c, d = control
        chord = d-a
        length = np.linalg.norm(chord)
        def distance(point):
            fraction = np.clip(np.dot(point-a, chord)/max(length*length, 1e-24), 0., 1.)
            return np.linalg.norm(point-(a+fraction*chord))
        error = max(distance(b), distance(c))
        if depth >= 16 or (error <= .002 and length <= .5):
            if not points:
                points.append(a.tolist())
            points.append(d.tolist())
            return
        ab, bc, cd = (a+b)/2, (b+c)/2, (c+d)/2
        abc, bcd = (ab+bc)/2, (bc+cd)/2
        middle = (abc+bcd)/2
        split((a, ab, abc, middle), depth+1)
        split((middle, bcd, cd, d), depth+1)
    for raw in rail['native_segment_payloads']:
        values = np.asarray(struct.unpack('>30f', bytes.fromhex(raw)), dtype='f8')
        a, b, c, d = (values[offset:offset+3] for offset in (0,4,8,12))
        split((d, d+c/3, d+2*c/3+b/3, d+c+b+a))
    return {'id': f"{rail['asset_id']}_{rail['section_index']}_{rail['rail_index']}",
            'closed': rail['closed'], 'points': points, 'original_segments': rail['native_segment_payloads']}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'fbx').mkdir(exist_ok=True)
    write_fallbacks()
    source = json.loads((SOURCE / 'map.json').read_text())
    report = {'source_sha256': sha(SOURCE / 'map.json'), 'render': [], 'collision': [], 'materials': {}, 'rails': [],
        'spawn': source['spawn'], 'summary': source['summary'], 'textures': source['textures']}
    scene = bpy.context.scene
    scene.unit_settings.system='METRIC'; scene.unit_settings.scale_length=1.
    for model in source['models']:
        assert sha(SOURCE/model['npz']) == model['sha256'], model['npz']
        vertices, faces, normals, uvs, lightmaps, decals, material_indices, slots = [], [], [], [], [], [], [], []
        offset = 0; degenerates = 0
        with np.load(SOURCE / model['npz'], allow_pickle=False) as arrays:
            for part in model['meshes']:
                i = part['index']; v = arrays[f'vertices_{i}']; f = arrays[f'faces_{i}']
                t = v[f].astype('f8')
                valid = np.linalg.norm(np.cross(t[:,1]-t[:,0], t[:,2]-t[:,0]), axis=1) > 1e-12
                degenerates += int((~valid).sum()); f = f[valid]
                if not len(v) or not len(f):
                    continue
                key = material_key(part)
                if key not in slots:
                    slots.append(key)
                report['materials'].setdefault(key, part)
                vertices.append(v); faces.append(f+offset); material_indices.extend([slots.index(key)]*len(f))
                n = arrays.get(f'retail_normals_{i}', arrays.get(f'normals_{i}'))
                if n is None:
                    n = np.zeros_like(v)
                    face_normals = np.cross(v[f[:,1]]-v[f[:,0]], v[f[:,2]]-v[f[:,0]])
                    for corner in range(3):
                        np.add.at(n, f[:,corner], face_normals)
                n = n/np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-20)
                normals.append(n)
                uv = arrays.get(f'uvs_{i}', np.zeros((len(v),2), dtype='f4'))
                uvs.append(uv)
                lightmaps.append(np.abs(arrays.get(f'lightmap_uvs_{i}', uv)))
                decals.append(arrays.get(f'decal_uvs_{i}', uv))
                offset += len(v)
        if not vertices:
            continue
        entry = export_mesh('SM_MP_'+model['asset_id'][2:], np.concatenate(vertices), np.concatenate(faces), slots,
            material_indices, {'UVMap': np.concatenate(uvs), 'RetailLightmap': np.concatenate(lightmaps), 'RetailDecal': np.concatenate(decals)}, np.concatenate(normals))
        entry['source_asset_id'] = model['asset_id']
        entry['degenerate_faces_removed'] = degenerates
        report['render'].append(entry)
        print('Exported', entry['name'], flush=True)
    for mesh in source['collision']:
        assert sha(SOURCE/mesh['npz']) == mesh['sha256'], mesh['npz']
        with np.load(SOURCE / mesh['npz'], allow_pickle=False) as arrays:
            triangles = arrays['triangles']
            cross = np.cross(triangles[:,1]-triangles[:,0], triangles[:,2]-triangles[:,0])
            valid = np.linalg.norm(cross, axis=1) > 1e-12
            # Only geometrically degenerate faces cannot be represented in Chaos.
            # Opposite-wound contacts and feature boundaries remain untouched.
            kept = triangles[valid]
            vertices = kept.reshape(-1,3)
            faces = np.arange(len(vertices), dtype='u4').reshape(-1,3)
            entry = export_mesh('UC_MP_'+mesh['id'], vertices, faces, ['M_Collision'], np.zeros(len(faces), dtype='i4'))
            entry['source_id'] = mesh['id']; entry['degenerate_faces_removed'] = int((~valid).sum())
            entry['one_sided'] = bool(mesh['mesh_flags'] & 0x10)
            report['collision'].append(entry)
    report['rails'] = [sample_rail(rail) for rail in source['rails']]
    # Seed the existing FBX factory's safe reimport route with a clean triangle.
    export_mesh('SM_MP_ImportSeed', np.asarray([[0,0,0],[1,0,0],[0,0,1]], dtype='f4'),
                np.asarray([[0,2,1]], dtype='u4'), ['M_Collision'], [0],
                {'UVMap': np.asarray([[0,0],[1,0],[0,1]], dtype='f4')})
    (OUT / 'build.json').write_text(json.dumps(report, indent=1) + '\n')
    print('MEGAPARK BUILD COMPLETE', source['summary'], flush=True)


if __name__ == '__main__':
    main()
