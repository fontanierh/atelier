"""Report what a saved map references and whether each reference resolves (read-only `editor.run`, V2_EDITOR_READ_ONLY=1).

V2_OPEN_MAP names the map (default the standalone Mega Park level); V2_REPORT_OUT is the JSON file to write. The report
holds the map package's hard and soft package dependencies from the asset registry, each with the assets it holds (none
means the reference does not resolve), and, after the map is opened, every actor's static mesh components with the mesh
each one draws (None when the saved reference did not load). Nothing is saved.
"""
import json
import os

import unreal as U

MAP = os.environ.get('V2_OPEN_MAP') or '/Game/MegaPark/Maps/SuperUltraMegaPark'
OUT = os.environ['V2_REPORT_OUT']
REG = U.AssetRegistryHelpers.get_asset_registry()

options = U.AssetRegistryDependencyOptions(include_soft_package_references=True, include_hard_package_references=True,
                                           include_searchable_names=False, include_soft_management_references=False,
                                           include_hard_management_references=False)
dependencies = {}
for dep in sorted(str(d) for d in (REG.get_dependencies(MAP, options) or [])):
    held = REG.get_assets_by_package_name(dep) or []
    dependencies[dep] = sorted(f'{a.asset_class_path.asset_name}:{a.asset_name}' for a in held)

if not U.get_editor_subsystem(U.LevelEditorSubsystem).load_level(MAP):
    raise RuntimeError(f'cannot open {MAP}')
actors = []
for actor in U.get_editor_subsystem(U.EditorActorSubsystem).get_all_level_actors():
    meshes = []
    for comp in actor.get_components_by_class(U.StaticMeshComponent):
        mesh = comp.static_mesh
        meshes.append({'component': comp.get_name(), 'mesh': mesh.get_path_name() if mesh else None})
    actors.append({'actor': actor.get_name(), 'class': actor.get_class().get_name(), 'meshes': meshes})

unresolved = sorted(d for d, held in dependencies.items() if d.startswith('/Game/') and not held)
missing = sum(1 for a in actors for m in a['meshes'] if m['mesh'] is None)
with open(OUT, 'w') as f:
    json.dump({'map': MAP, 'dependencies': dependencies, 'unresolved': unresolved, 'actors': actors,
               'components_without_mesh': missing}, f, indent=1, sort_keys=True)
U.log(f'V2 MAP REFS {MAP} dependencies={len(dependencies)} unresolved={len(unresolved)} actors={len(actors)} '
      f'components_without_mesh={missing}')
