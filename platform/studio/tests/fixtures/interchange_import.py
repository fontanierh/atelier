"""Native control/current mesh import, with no project modules or production outputs."""
import json
import os
from pathlib import Path
import sys

import unreal as U

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from atelier.interchange_mesh import import_static_mesh

folder = Path(os.environ['ATELIER_MESH_CANARY_DIR'])
E, AT = U.EditorAssetLibrary, U.AssetToolsHelpers.get_asset_tools()
registry = U.AssetRegistryHelpers.get_asset_registry()
# Previous owner path, kept verbatim as a receiving control for its geometry settings.
generic = U.InterchangeGenericAssetsPipeline()
mesh_pipeline = generic.get_editor_property('mesh_pipeline')
for name, value in dict(import_static_meshes=True, import_skeletal_meshes=False,
    combine_static_meshes_behavior=U.InterchangeCombineStaticMeshesBehavior.ALL, build_nanite=False).items():
    mesh_pipeline.set_editor_property(name, value)
generic.get_editor_property('animation_pipeline').set_editor_property('import_animations', False)
stack = U.InterchangePipelineStackOverride()
stack.add_pipeline(generic)
stack.add_pipeline(U.InterchangeGLTFPipeline())
task = U.AssetImportTask()
task.filename = str(folder/'Probe.glb')
task.destination_path = '/Game/Before/Import/Probe'
task.options = stack
task.automated = True
task.replace_existing = True
task.save = True
AT.import_asset_tasks([task])
found = [str(row.package_name) for row in registry.get_assets_by_path(task.destination_path, recursive=True)
         if str(row.asset_class_path.asset_name) == 'StaticMesh']
assert len(found) == 1, found
assert E.rename_asset(found[0], '/Game/Before/Meshes/Probe')
before = E.load_asset('/Game/Before/Meshes/Probe')
after = import_static_mesh(folder/'Probe.glb', '/Game/After/Meshes', 'Probe')
new_assets = list(registry.get_assets_by_path('/Game/After', recursive=True))
assert len(new_assets) == 1 and str(new_assets[0].asset_class_path.asset_name) == 'StaticMesh'
U.load_module('StaticMeshEditor')
editor = U.get_editor_subsystem(U.StaticMeshEditorSubsystem)
def state(mesh):
    box = mesh.get_bounding_box()
    return dict(triangles=mesh.get_num_triangles(0),
        slots=[[str(slot.get_editor_property('material_slot_name')),
                str(slot.get_editor_property('imported_material_slot_name'))]
               for slot in mesh.get_editor_property('static_materials')],
        bounds=[getattr(point, axis) for point in (box.min, box.max) for axis in ('x', 'y', 'z')],
        simple=editor.get_simple_collision_count(mesh), convex=editor.get_convex_collision_count(mesh),
        collision=str(editor.get_collision_complexity(mesh)))
assert state(before) == state(after), [state(before), state(after)]
assert state(after)['triangles'] == 2 and len(state(after)['slots']) == 2
assert max(abs(value) for value in state(after)['bounds']) >= 199., state(after)
# Same owner finishing; placeholder interfaces must not enter the geometry comparison.
material = E.load_asset('/Engine/EngineMaterials/DefaultMaterial')
assert material
for label, mesh in (('before', before), ('after', after)):
    for index in range(len(mesh.get_editor_property('static_materials'))):
        mesh.set_material(index, material)
    assert E.save_loaded_asset(mesh, only_if_is_dirty=True)
    options = U.FbxExportOption()
    for name, value in dict(ascii=False, vertex_color=True, level_of_detail=False,
                            collision=False, export_source_mesh=True).items():
        options.set_editor_property(name, value)
    export = U.AssetExportTask()
    export.object = mesh
    export.filename = str(folder/(label+'.fbx'))
    export.automated = True
    export.replace_identical = True
    export.prompt = False
    export.options = options
    export.exporter = U.StaticMeshExporterFBX()
    assert U.Exporter.run_asset_export_task(export), label
(folder/'import-result.json').write_text(json.dumps(dict(state=state(after), new_packages=len(new_assets),
    previous_packages=len(registry.get_assets_by_path('/Game/Before', recursive=True))), indent=2))
print('INTERCHANGE MESH CANARY COMPLETE', flush=True)
