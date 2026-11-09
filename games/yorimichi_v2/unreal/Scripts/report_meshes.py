"""Report saved static meshes as JSON (read-only `editor.run`, V2_EDITOR_READ_ONLY=1): what a recipe must reproduce.

V2_REPORT_PACKAGES names the meshes ("/Game/A/SM_X /Game/B/SM_Y"); V2_REPORT_OUT the JSON file to write. For each mesh:
its material slots in index order (slot name and material), each LOD's screen size, triangles and per-section slot,
its collision (trace flag, the simple boxes, convex and other shape counts, the LOD used for collision), its bounds and
its import sources. Nothing is saved.
"""
import json
import os

import unreal as U

MARKER = 'V2 MESHES REPORTED'
EAL = U.EditorAssetLibrary


def _vec(v):
    return [round(v.x, 4), round(v.y, 4), round(v.z, 4)]


def _collision(mesh, editor):
    body = mesh.get_editor_property('body_setup')
    if body is None:
        return None
    geom = body.get_editor_property('agg_geom')
    boxes = [dict(center=_vec(b.get_editor_property('center')),
                  rotation=[round(r, 4) for r in (b.get_editor_property('rotation').roll,
                                                  b.get_editor_property('rotation').pitch,
                                                  b.get_editor_property('rotation').yaw)],
                  size=[round(b.get_editor_property(k), 4) for k in ('x', 'y', 'z')])
             for b in geom.get_editor_property('box_elems')]
    return dict(trace=str(body.get_editor_property('collision_trace_flag')).split('.')[-1], boxes=boxes,
                convex=len(geom.get_editor_property('convex_elems')),
                spheres=len(geom.get_editor_property('sphere_elems')),
                capsules=len(geom.get_editor_property('sphyl_elems')),
                simple=int(editor.get_simple_collision_count(mesh)),
                lod_for_collision=int(mesh.get_editor_property('lod_for_collision')),
                double_sided=bool(body.get_editor_property('double_sided_geometry')))


def report(path, editor):
    mesh = EAL.load_asset(path)
    if not isinstance(mesh, U.StaticMesh):
        return {'error': f'not a static mesh: {mesh}'}
    slots = [dict(name=str(m.get_editor_property('material_slot_name')),
                  imported=str(m.get_editor_property('imported_material_slot_name')),
                  material=(m.get_editor_property('material_interface').get_path_name().split('.')[0]
                            if m.get_editor_property('material_interface') else None))
             for m in mesh.get_editor_property('static_materials')]
    screens = [float(s) for s in editor.get_lod_screen_sizes(mesh)]
    lods = [dict(screen=screens[i] if i < len(screens) else None, triangles=int(mesh.get_num_triangles(i)),
                 sections=[int(editor.get_lod_material_slot(mesh, i, s)) for s in range(mesh.get_num_sections(i))])
            for i in range(mesh.get_num_lods())]
    box = mesh.get_bounding_box()
    data = mesh.get_editor_property('asset_import_data')
    return dict(slots=slots, lods=lods, collision=_collision(mesh, editor), bounds=[_vec(box.min), _vec(box.max)],
                nanite=bool(mesh.get_editor_property('nanite_settings').get_editor_property('enabled')),
                sources=list(data.extract_filenames()) if data else [])


def main():
    U.load_module('StaticMeshEditor')
    editor = U.get_editor_subsystem(U.StaticMeshEditorSubsystem)
    out = {}
    for path in os.environ['V2_REPORT_PACKAGES'].split():
        try:
            out[path] = report(path, editor)
        except Exception as exc:   # one unreadable mesh is reported, not fatal to the rest
            out[path] = {'error': repr(exc)}
    with open(os.environ['V2_REPORT_OUT'], 'w') as f:
        json.dump(out, f, indent=1)
    errors = sum('error' in r for r in out.values())
    U.log(f'{MARKER} {len(out)} errors={errors}')


main()
