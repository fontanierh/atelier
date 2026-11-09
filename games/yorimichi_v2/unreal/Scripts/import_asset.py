"""Editor side of a V2 targeted import: write exactly the planned packages of one asset, then stop.

Started by `atelier build yorimichi_v2 import.<id>` (guarded, admitted) from tools/import/run.py, which passes the
plan in V2_IMPORT_PLAN and owns journaling, verification and records. This script never deletes folders, never
recreates other packages and saves only the planned ones. It reimports into the existing package path so references
to it, and its user-owned settings, survive. Import metadata keeps the repository-relative source path, never the
absolute path of this checkout (CONTRACTS yorimichi-v2-portable-records).
"""
import json
import os
import sys
from pathlib import Path

import unreal as U

# A one-asset import runs this file in its own commandlet, which does not put unreal/Scripts on the path (the
# editor session does): its helper modules beside it must import either way.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import import_settings  # noqa: E402
import lod_preservation  # noqa: E402

MARKER = 'V2 IMPORT DONE'
LOD_RESULT = 'lod-result.json'   # beside the plan: each static-mesh package's LOD chain before and after
TRANSIENT = '/Game/V2Import/Transient'   # a lod_chain's further levels, imported here and never saved
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
    if settings.get('collision') == 'simple_and_complex':
        data.set_editor_property('one_convex_hull_per_ucx', True)   # each authored UCX_ node is one hull
    return ui


def _legacy_fbx(settings):
    """True when the record imports authored UCX hulls: only the legacy FBX importer brings them in (the donor's
    importers turn Interchange off for FBX; an Interchange reimport here leaves the mesh with no shapes)."""
    return settings.get('collision') == 'simple_and_complex'


def _gltf_static_mesh(name, collision=True):
    """glTF geometry only, the original region importers' Interchange route: every primitive combined into one mesh
    with its material slots, and no material or texture created (the record binds its own, slot_materials).
    `collision` False imports no shapes at all (the record sets its own boxes, or keeps none)."""
    generic = U.InterchangeGenericAssetsPipeline()
    generic.set_editor_property('asset_name', name)
    material = generic.get_editor_property('material_pipeline')
    material.set_editor_property('import_materials', False)
    material.get_editor_property('texture_pipeline').set_editor_property('import_textures', False)
    mesh = generic.get_editor_property('mesh_pipeline')
    _set(mesh, dict(import_static_meshes=True, import_skeletal_meshes=False, build_nanite=False,
                    combine_static_meshes_behavior=U.InterchangeCombineStaticMeshesBehavior.ALL))
    if not collision:
        _set(mesh, dict(collision=False, import_collision_according_to_mesh_name=False))
    generic.get_editor_property('animation_pipeline').set_editor_property('import_animations', False)
    stack = U.InterchangePipelineStackOverride()
    stack.add_pipeline(generic)
    stack.add_pipeline(U.InterchangeGLTFPipeline())
    return stack


def _apply_mesh_settings(asset, settings):
    """The original region importers' mesh settings (import_brinecove.py), each only when the record names it:
    materials bound by slot index, full-precision metre UVs, complex double-sided collision, the triangle count."""
    slots = settings.get('slot_materials')
    if slots is not None:
        if len(asset.get_editor_property('static_materials')) != len(slots):
            raise RuntimeError(f'{asset.get_path_name()} has {len(asset.get_editor_property("static_materials"))} '
                               f'material slots, the record binds {len(slots)}')
        for index, material in enumerate(slots):
            loaded = EAL.load_asset(material)
            if loaded is None:
                raise RuntimeError(f'material {material} for slot {index} does not exist')
            asset.set_material(index, loaded)
    slot_map = settings.get('slot_map')
    if slot_map is not None:
        # Each imported slot binds by its authored name (the donor's city importer); a slot the record does not
        # name is a broken source or record, never left on a default material.
        for index, slot in enumerate(asset.get_editor_property('static_materials')):
            key = str(slot.get_editor_property('imported_material_slot_name'))
            if key not in slot_map:
                raise RuntimeError(f'{asset.get_path_name()} has slot {key}, which the record does not bind')
            loaded = EAL.load_asset(slot_map[key])
            if loaded is None:
                raise RuntimeError(f'material {slot_map[key]} for slot {key} does not exist')
            asset.set_material(index, loaded)
    if settings.get('full_precision_uvs'):
        U.load_module('StaticMeshEditor')
        editor = U.get_editor_subsystem(U.StaticMeshEditorSubsystem)
        build = editor.get_lod_build_settings(asset, 0)
        build.set_editor_property('use_full_precision_u_vs', True)
        editor.set_lod_build_settings(asset, 0, build)
    cpu = import_settings.allow_cpu_access(settings)
    if cpu is not None:
        asset.set_editor_property('allow_cpu_access', cpu)   # cooked riding snapshots and LOD checks read positions on the CPU
    if settings.get('collision') == 'complex':
        body = asset.get_editor_property('body_setup')
        _set(body, dict(collision_trace_flag=U.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE,
                        double_sided_geometry=import_settings.double_sided(settings)))
    elif settings.get('collision') == 'simple_and_complex':
        # The source's authored UCX hulls are the simple collision (import_city_surface_tiles.py); a piece declared
        # with none keeps no shapes. The hull count must be the source's: a stale or missing hull is a broken import.
        editor = _static_mesh_editor()
        _set(asset.get_editor_property('body_setup'),
             dict(collision_trace_flag=U.CollisionTraceFlag.CTF_USE_SIMPLE_AND_COMPLEX))
        hulls = int(settings.get('hulls', 0))
        if hulls == 0 and (editor.get_simple_collision_count(asset) or editor.get_convex_collision_count(asset)):
            editor.remove_collisions(asset)
        count = editor.get_simple_collision_count(asset) + editor.get_convex_collision_count(asset)
        if count != hulls:
            raise RuntimeError(f'{asset.get_path_name()} has {count} collision shapes, the source {hulls}')
    elif settings.get('collision') == 'boxes':
        # The donor's fixed boxes ([min x, y, z, max x, y, z], mesh space, cm), used as complex collision
        # (import_belmonte_train.py); an empty list leaves a render-only part with no shapes.
        boxes = [_box(b) for b in settings.get('boxes', [])]
        count = U.BelmonteTrainImportLibrary.set_simple_boxes(asset, boxes)
        if count != len(boxes):
            raise RuntimeError(f'{asset.get_path_name()} took {count} collision boxes, the record {len(boxes)}')
        asset.set_editor_property('lod_for_collision', 0)
    elif settings.get('collision') == 'none':
        editor = _static_mesh_editor()
        if editor.get_simple_collision_count(asset) or editor.get_convex_collision_count(asset):
            editor.remove_collisions(asset)
    if 'triangles' in settings:
        # Unreal drops a few degenerate slivers from a procedural kit; more than 2 % is a broken import.
        count, wanted = asset.get_num_triangles(0), int(settings['triangles'])
        if not wanted * .98 <= count <= wanted:
            raise RuntimeError(f'{asset.get_path_name()} has {count} triangles, the source {wanted}')


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
    if data is None:
        return
    data.scripted_add_filename(portable, 0, '')
    # An Interchange import (textures) also keeps its node graph and a factory node ID ("Factory_<absolute path>"),
    # which both repeat the checkout's path: drop the graph and name the node after the asset, as the scrub does.
    if hasattr(data, 'set_node_container') and hasattr(U, 'InterchangeBaseNodeContainer'):
        data.set_node_container(U.new_object(U.InterchangeBaseNodeContainer, outer=data))
        if not U.ImportProvenance.rename_interchange_node(data, f'Factory_{asset.get_name()}'):
            raise RuntimeError(f'{asset.get_path_name()}: Interchange data without a renamable node ID')


def _apply_texture_settings(asset, settings):
    if 'srgb' in settings:
        asset.set_editor_property('srgb', bool(settings['srgb']))
    if 'compression' in settings:
        asset.set_editor_property('compression_settings', getattr(U.TextureCompressionSettings, settings['compression']))
    size, group = import_settings.max_texture_size(settings), import_settings.lod_group(settings)
    if size is not None:
        asset.set_editor_property('max_texture_size', size)
    if group is not None:
        asset.set_editor_property('lod_group', getattr(U.TextureGroup, group))
    if 'address' in settings:
        # The donor's tiling surfaces (import_hippodrome.py `wrap=True`): wrap on both axes, nothing else.
        if settings['address'] != 'wrap':
            raise RuntimeError(f'unknown texture address {settings["address"]!r}')
        asset.set_editor_property('address_x', U.TextureAddress.TA_WRAP)
        asset.set_editor_property('address_y', U.TextureAddress.TA_WRAP)


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


def _static_mesh_editor():
    U.load_module('StaticMeshEditor')
    return U.get_editor_subsystem(U.StaticMeshEditorSubsystem)


def _reduction_options(lods):
    """The editor's reduction options for a recipe's plan: [[percent, screen], ...], LOD0 first (donor generate_lods)."""
    options = U.StaticMeshReductionOptions()
    options.set_editor_property('auto_compute_lod_screen_size', False)
    levels = []
    for percent, screen in lods:
        level = U.StaticMeshReductionSettings()
        level.set_editor_property('percent_triangles', percent)
        level.set_editor_property('screen_size', screen)
        levels.append(level)
    options.set_editor_property('reduction_settings', levels)
    return options


def _box(values):
    box = U.Box()
    box.min, box.max, box.is_valid = U.Vector(*values[:3]), U.Vector(*values[3:]), True
    return box


def _material_path(slot):
    material = slot.get_editor_property('material_interface')
    return material.get_path_name().split('.', 1)[0] if material else None


def _build_lod_chain(asset, settings, resolve):
    """One source per LOD (settings `lod_chain`: [[source, screen, triangles, [section slots]], ...], LOD0 first, and
    `slots`: [[imported slot name, material], ...] in slot order), as the donor's train built it
    (import_belmonte_train.py with_lods). LOD0 is the package's own import. Each further level is imported as a
    transient mesh that is never saved, its sections bound to the record's materials, then attached with slot reuse:
    a section on a material the mesh already has takes that slot, any other a new one, so the slot table comes out in
    the donor's order. The slot table, each level's section slots and triangles must then be the record's exactly."""
    editor = _static_mesh_editor()
    chain, slots = settings['lod_chain'], settings['slots']
    materials = []
    for _, path in slots:
        loaded = EAL.load_asset(path)
        if loaded is None:
            raise RuntimeError(f'material {path} does not exist')
        materials.append(loaded)

    def bind(mesh, sections):
        if mesh.get_num_sections(0) != len(sections):
            raise RuntimeError(f'{mesh.get_path_name()} has {mesh.get_num_sections(0)} sections, the record '
                               f'{len(sections)}')
        bound = {}
        for section, slot in enumerate(sections):
            index = editor.get_lod_material_slot(mesh, 0, section)
            if bound.setdefault(index, slot) != slot:
                raise RuntimeError(f'{mesh.get_path_name()} slot {index} holds sections of two record slots')
            mesh.set_material(index, materials[slot])

    if asset.get_num_lods() > 1:
        editor.remove_lods(asset)
    bind(asset, chain[0][3])
    transient = []
    for level, (source, _, _, sections) in enumerate(chain[1:], 1):
        name = f'{asset.get_name()}_LOD{level}'
        lod = _import(resolve(source), f'{TRANSIENT}/{name}', _gltf_static_mesh(name, collision=False))
        bind(lod, sections)
        if editor.set_lod_from_static_mesh(asset, level, lod, 0, True) != level:
            raise RuntimeError(f'{asset.get_path_name()}: LOD{level} from {source} was not attached')
        transient.append(lod)
    # The attached levels are copies: delete the never-saved transient meshes (which drops their packages' dirty state;
    # an unload skips dirty packages), so a batch session ends the job with no dirty package.
    lod = None
    for mesh in transient:
        EAL.delete_loaded_asset(mesh)
    transient.clear()
    left = [p.get_name() for p in U.EditorLoadingAndSavingUtils.get_dirty_content_packages()
            if p.get_name().startswith(TRANSIENT)]
    if left:
        raise RuntimeError(f'{asset.get_path_name()}: transient LOD packages {left} are still loaded')
    if len(chain) > 1:
        editor.set_lod_screen_sizes(asset, [screen for _, screen, _, _ in chain])
    got = [[str(m.get_editor_property('imported_material_slot_name')), _material_path(m)]
           for m in asset.get_editor_property('static_materials')]
    if got != [list(s) for s in slots]:
        raise RuntimeError(f'{asset.get_path_name()} has slots {got}, the record {slots}')
    if asset.get_num_lods() != len(chain):
        raise RuntimeError(f'{asset.get_path_name()} has {asset.get_num_lods()} LODs, the record {len(chain)}')
    for level, (source, _, triangles, sections) in enumerate(chain):
        actual = [editor.get_lod_material_slot(asset, level, s) for s in range(asset.get_num_sections(level))]
        if actual != list(sections) or asset.get_num_triangles(level) != triangles:
            raise RuntimeError(f'{asset.get_path_name()} LOD{level} has sections {actual} and '
                               f'{asset.get_num_triangles(level)} triangles, the record {sections} and {triangles}')


def main():
    if not U.V2SaveGuard.is_active():
        raise RuntimeError('the V2 save guard is not active (V2_SAVE_ALLOW); an import runs only through its build step')
    plan = json.loads(open(os.environ['V2_IMPORT_PLAN']).read())
    settings = plan['settings']
    jobs = list(zip(plan['sources'], plan['portable_sources'], plan['packages']))
    resolve = None
    if 'lod_chain' in settings:
        # One package from one source per LOD: the chain names them (record-relative), LOD0 first.
        by_name = {portable.rsplit('/src/', 1)[-1]: source
                   for source, portable in zip(plan['sources'], plan['portable_sources'])}
        resolve = lambda rel: by_name[rel.removeprefix('src/')]  # noqa: E731
        first = settings['lod_chain'][0][0].removeprefix('src/')
        if len(plan['packages']) != 1 or sorted(by_name) != sorted(c[0].removeprefix('src/')
                                                                   for c in settings['lod_chain']):
            raise RuntimeError('a lod_chain plan is one package and exactly the sources its chain names')
        jobs = [(by_name[first], next(p for p in plan['portable_sources'] if p.endswith('/src/' + first)),
                 plan['packages'][0])]
    elif len(plan['sources']) != len(plan['packages']):
        raise RuntimeError('a V2 import plan pairs each source with one package')
    lod_results = {}
    for source, portable, package in jobs:
        if plan['importer'] == 'static-mesh':
            # The chain the package had before this import; a new package has none.
            existing = EAL.load_asset(package)
            if existing is not None and settings.get('collision') == 'simple_and_complex':
                # An FBX reimport appends its UCX hulls to the saved ones: start from none.
                _static_mesh_editor().remove_collisions(existing)
            before = lod_preservation.read(_static_mesh_editor(), existing) if existing is not None else None
            slots = settings.get('slot_materials')
            if (existing is not None and slots is not None
                    and len(existing.get_editor_property('static_materials')) != len(slots)):
                # The source has a different material set (a split took a material): a reimport keeps the old slot
                # table, so the import starts from no package; its LOD settings were read above and are kept.
                EAL.delete_loaded_asset(existing)
                existing = None
            # Made after any delete above: its garbage collection would free a pipeline made earlier.
            if source.lower().endswith('.fbx'):
                options = _fbx_static_mesh(settings)
            elif source.lower().endswith(('.glb', '.gltf')):
                options = _gltf_static_mesh(package.rsplit('/', 1)[1],
                                            collision=settings.get('collision') not in ('boxes', 'none'))
            else:
                options = None
            legacy = source.lower().endswith('.fbx') and _legacy_fbx(settings)
            if legacy:
                U.SystemLibrary.execute_console_command(None, 'Interchange.FeatureFlags.Import.FBX 0')
            try:
                asset = _import(source, package, options)
            finally:
                if legacy:
                    U.SystemLibrary.execute_console_command(None, 'Interchange.FeatureFlags.Import.FBX 1')
            if resolve is not None:
                _build_lod_chain(asset, settings, resolve)
            _apply_material_slots(asset, plan)
            _apply_mesh_settings(asset, settings)
            after = lod_preservation.preserve(_static_mesh_editor(), asset, before, settings.get('lods'),
                                              _reduction_options)
            lod_results[package] = {'before': before, 'after': after}
        elif plan['importer'] == 'texture':
            asset = _import(source, package, _texture(settings))
            _apply_texture_settings(asset, settings)
        else:
            raise RuntimeError(f'no editor importer {plan["importer"]}')
        _portable_source(asset, portable)
        if not EAL.save_asset(package, only_if_is_dirty=False):
            raise RuntimeError(f'could not save {package}')
        U.log(f'V2 import wrote {package} from {portable}')
    if lod_results:   # read back by tools/import/run.py, which records the chains in verified.json
        Path(os.environ['V2_IMPORT_PLAN']).with_name(LOD_RESULT).write_text(json.dumps(lod_results, indent=1) + '\n')
    U.log(MARKER)


main()
