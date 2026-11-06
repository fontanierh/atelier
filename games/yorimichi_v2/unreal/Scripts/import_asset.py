"""Editor side of a V2 targeted import: write exactly the planned packages of one asset, then stop.

Started by `atelier build yorimichi_v2 import.<id>` (guarded, admitted) from tools/import/run.py, which passes the
plan in V2_IMPORT_PLAN and owns journaling, verification and records. This script never deletes folders, never
recreates other packages and saves only the planned ones. It reimports into the existing package path so references
to it, and its user-owned settings, survive. Import metadata keeps the repository-relative source path, never the
absolute path of this checkout (CONTRACTS yorimichi-v2-portable-records).
"""
import json
import os

import unreal as U

MARKER = 'V2 IMPORT DONE'
EAL = U.EditorAssetLibrary
TOOLS = U.AssetToolsHelpers.get_asset_tools()


def _set(obj, values):
    for key, value in values.items():
        obj.set_editor_property(key, value)


def _fbx_static_mesh(settings):
    """The original game's proven static-mesh FBX settings, with every unit and normal option explicit."""
    ui = U.FbxImportUI()
    _set(ui, dict(automated_import_should_detect_type=False, mesh_type_to_import=U.FBXImportType.FBXIT_STATIC_MESH,
                  import_mesh=True, import_materials=False, import_textures=False, import_animations=False))
    data = ui.get_editor_property('static_mesh_import_data')
    _set(data, dict(convert_scene=True, convert_scene_unit=True, import_uniform_scale=float(settings.get('scale', 1.0)),
                    combine_meshes=True, generate_lightmap_u_vs=False,
                    auto_generate_collision=settings.get('collision', 'none') == 'auto',
                    build_nanite=bool(settings.get('nanite', False)),
                    normal_import_method=U.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS,
                    vertex_color_import_option=U.VertexColorImportOption.REPLACE))
    return ui


def _texture(settings):
    return None   # the texture factory's defaults; colour space and compression are applied after import


def _import(source, package, options):
    folder, name = package.rsplit('/', 1)
    task = U.AssetImportTask()
    _set(task, dict(filename=source, destination_path=folder, destination_name=name, automated=True,
                    replace_existing=True, replace_existing_settings=False, save=False))
    if options is not None:
        task.set_editor_property('options', options)
    TOOLS.import_asset_tasks([task])
    # An existing destination still loads after a failed reimport, so only the task's own result counts.
    imported = {str(path).split('.', 1)[0] for path in task.get_editor_property('imported_object_paths')}
    if package not in imported:
        raise RuntimeError(f'import of {source} did not produce {package} (task imported {sorted(imported)})')
    asset = EAL.load_asset(package)
    if asset is None:
        raise RuntimeError(f'import of {source} produced no asset at {package}')
    return asset


def _portable_source(asset, portable):
    """Point the asset's import data at the repository-relative source, not this checkout's absolute path."""
    data = asset.get_editor_property('asset_import_data')
    if data is not None:
        data.scripted_add_filename(portable, 0, '')


def _apply_texture_settings(asset, settings):
    if 'srgb' in settings:
        asset.set_editor_property('srgb', bool(settings['srgb']))
    if 'compression' in settings:
        asset.set_editor_property('compression_settings', getattr(U.TextureCompressionSettings, settings['compression']))


def _apply_material_slots(asset, plan):
    """Bind declared material slots to their referenced assets by stable path."""
    for slot, material in plan['settings'].get('materials', {}).items():
        loaded = EAL.load_asset(material)
        if loaded is None:
            raise RuntimeError(f'material {material} for slot {slot} does not exist')
        index = asset.get_material_index(slot)
        if index < 0:
            raise RuntimeError(f'{asset.get_path_name()} has no material slot {slot}')
        asset.set_material(index, loaded)


def main():
    if not U.V2SaveGuard.is_active():
        raise RuntimeError('the V2 save guard is not active (V2_SAVE_ALLOW); an import runs only through its build step')
    plan = json.loads(open(os.environ['V2_IMPORT_PLAN']).read())
    settings = plan['settings']
    if len(plan['sources']) != len(plan['packages']):
        raise RuntimeError('a V2 import plan pairs each source with one package')
    for source, portable, package in zip(plan['sources'], plan['portable_sources'], plan['packages']):
        if plan['importer'] == 'static-mesh':
            asset = _import(source, package, _fbx_static_mesh(settings) if source.lower().endswith('.fbx') else None)
            _apply_material_slots(asset, plan)
        elif plan['importer'] == 'texture':
            asset = _import(source, package, _texture(settings))
            _apply_texture_settings(asset, settings)
        else:
            raise RuntimeError(f'no editor importer {plan["importer"]}')
        _portable_source(asset, portable)
        if not EAL.save_asset(package, only_if_is_dirty=False):
            raise RuntimeError(f'could not save {package}')
        U.log(f'V2 import wrote {package} from {portable}')
    U.log(MARKER)


main()
