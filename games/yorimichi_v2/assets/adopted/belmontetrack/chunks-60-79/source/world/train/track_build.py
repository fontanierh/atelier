"""Belmonte railway track meshes (Blender, headless): `atelier build yorimichi world.belmonte_track`.

Turns track.py's layout into GLBs and writes the placements: build/yorimichi/belmonte-track/
- meshes/SM_TK_<name>_LOD<k>.glb: glTF, metres, Blender's standard Y-up export, each mesh relative to its origin;
- track.json: chunk and piece origins, instance lists (sleepers per chunk, portals, buffer stops, stop boards,
  turnouts, editor-only earthwork markers), tunnel data layers and load boxes, viaduct pieces;
- manifest.json: sizes, checksums, triangles per LOD and the budget checks (BELMONTE_TRACK.md).
UVs are planar in metres along the face's dominant axis (one material tile per metre).
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1])); import yori  # noqa: E402,F401
import hashlib
import json

import bpy
import numpy as np

from train import track as T

MESHES = T.OUT / 'meshes'


def clear():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def materials():
    out = {}
    for name, (r, g, b, rough) in T.MATERIALS.items():
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        bsdf = m.node_tree.nodes['Principled BSDF']
        bsdf.inputs['Base Color'].default_value = (r, g, b, 1.)
        bsdf.inputs['Roughness'].default_value = rough
        bsdf.inputs['Metallic'].default_value = .6 if name == 'MI_B_iron' else 0.
        if name == 'MI_TK_LampGlow':
            bsdf.inputs['Emission Color'].default_value = (r, g, b, 1.)
            bsdf.inputs['Emission Strength'].default_value = 8.
        out[name] = m
    return out


def to_object(name, mesh, mats, collection=None):
    """A Blender object from a track.Mesh: material slots in first-use order, planar UVs in metres, flat shading."""
    me = bpy.data.meshes.new(name)
    me.from_pydata(mesh.verts, [], mesh.faces)
    slots = list(dict.fromkeys(mesh.mats))
    for slot in slots:
        me.materials.append(mats[slot])
    index = {n: i for i, n in enumerate(slots)}
    me.polygons.foreach_set('material_index', [index[m] for m in mesh.mats])
    uv = me.uv_layers.new(name='UVMap')
    co = np.asarray(mesh.verts)
    data = []
    for poly in me.polygons:
        axis = int(np.argmax(np.abs(poly.normal)))
        a, b = [k for k in range(3) if k != axis]
        for li in poly.loop_indices:
            v = co[me.loops[li].vertex_index]
            data.extend((v[a], v[b]))
    uv.data.foreach_set('uv', data)
    me.validate()
    me.update()
    o = bpy.data.objects.new(name, me)
    (collection or bpy.context.scene.collection).objects.link(o)
    return o


def export_glb(path, obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.gltf(filepath=str(path), export_format='GLB', use_selection=True, export_yup=True,
                              export_apply=True, export_materials='EXPORT', export_cameras=False, export_lights=False,
                              export_animations=False)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    clear()
    MESHES.mkdir(parents=True, exist_ok=True)
    for old in MESHES.glob('*.glb'):
        old.unlink()
    meshes, doc = T.layout()
    mats = materials()
    files, triangles = {}, {}
    for name, lods in meshes.items():
        triangles[name] = [m.triangles for m in lods]
        for k, mesh in enumerate(lods):
            obj = to_object(f'{name}_LOD{k}', mesh, mats)
            path = MESHES / f'{name}_LOD{k}.glb'
            export_glb(path, obj)
            files[path.name] = dict(bytes=path.stat().st_size, sha256=sha(path))
            bpy.data.objects.remove(obj)
    doc['meshes'] = {name: dict(lods=[f'meshes/{name}_LOD{k}.glb' for k in range(len(lods))], triangles=triangles[name],
                                materials=list(dict.fromkeys(m for mesh in lods for m in mesh.mats)))
                     for name, lods in meshes.items()}
    (T.OUT / 'track.json').write_text(json.dumps(doc, indent=1))
    report = T.triangle_report(meshes)
    total = sum(f['bytes'] for f in files.values())
    manifest = dict(
        files=files, bytes=total, triangles=triangles, budgets=report,
        checks=dict(budgets_ok=all(r['ok'] for r in report.values()), disk_ok=total <= 15e6,
                    route_mismatch_m=doc['route']['mismatch_m'],
                    sleepers=sum(len(v) for v in doc['instances']['SM_TK_Sleeper'].values())))
    (T.OUT / 'manifest.json').write_text(json.dumps(manifest, indent=1))
    print(f'belmonte-track: {len(files)} GLBs, {total / 1e6:.1f} MB, budgets ok: {manifest["checks"]["budgets_ok"]}')
    if not manifest['checks']['budgets_ok']:
        raise SystemExit('track budgets exceeded: ' + ', '.join(k for k, r in report.items() if not r['ok']))


if __name__ == '__main__':
    main()
