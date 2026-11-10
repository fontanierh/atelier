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
import material_base  # noqa: E402
import lod_preservation  # noqa: E402
from mesh_materials import assign_materials  # noqa: E402
import master_digest  # noqa: E402
from master_sources import builder as _master_builder, checked_sources as _checked_master_sources  # noqa: E402

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
    return settings.get('collision') == 'simple_and_complex' or import_settings.legacy_fbx(settings)


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
        materials = []
        for index, material in enumerate(slots):
            loaded = EAL.load_asset(material)
            if loaded is None:
                raise RuntimeError(f'material {material} for slot {index} does not exist')
            materials.append(loaded)
        assign_materials(asset, materials)
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
        # Complex-as-simple keeps no simple shapes (no saved package has any): drop the UCX hull an FBX source carries.
        editor = _static_mesh_editor()
        if editor.get_simple_collision_count(asset) or editor.get_convex_collision_count(asset):
            editor.remove_collisions(asset)
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
    trace = import_settings.collision_trace(settings)
    if trace is not None:
        # The saved package's own trace flag (default, simple-as-complex, ...) when it differs from the collision mode's.
        _set(asset.get_editor_property('body_setup'), dict(collision_trace_flag=getattr(U.CollisionTraceFlag, trace)))
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
        # The donor's tiling surfaces (import_hippodrome.py `wrap=True`) and the plaza's mirrored ones (the saved packages
        # read TA_MIRROR on both axes): both axes take the one mode.
        mode = _texture_address(settings['address'])
        asset.set_editor_property('address_x', mode)
        asset.set_editor_property('address_y', mode)
    _read_back_texture_settings(asset, settings)


def _texture_address(name):
    if name == 'wrap':
        return U.TextureAddress.TA_WRAP
    if name == 'mirror':
        return U.TextureAddress.TA_MIRROR
    raise RuntimeError(f'unknown texture address {name!r}')


def _read_back_texture_settings(asset, settings):
    """Read each stated setting back before the save: UE 5.8's setters can report success and keep the old value
    (tint_material.py), so only the read proves what the package will contain. An unstated setting is not read."""
    name = asset.get_path_name()
    checks = []
    if 'srgb' in settings:
        checks.append(('srgb', bool(settings['srgb'])))
    if 'compression' in settings:
        checks.append(('compression_settings', getattr(U.TextureCompressionSettings, settings['compression'])))
    if import_settings.max_texture_size(settings) is not None:
        checks.append(('max_texture_size', import_settings.max_texture_size(settings)))
    if import_settings.lod_group(settings) is not None:
        checks.append(('lod_group', getattr(U.TextureGroup, import_settings.lod_group(settings))))
    if 'address' in settings:
        checks += [('address_x', _texture_address(settings['address'])), ('address_y', _texture_address(settings['address']))]
    for prop, want in checks:
        got = asset.get_editor_property(prop)
        if got != want:
            raise RuntimeError(f'{name}: {prop} reads back {got!r}, not {want!r}; nothing is saved')


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
        # A level goes through the importer of its own file: an FBX the same way as the record's LOD0 (the donor's city
        # tree levels are FBX), a glTF or GLB as before. Collision is off for every level.
        if import_settings.level_kind(source) == 'fbx':
            fbx = _fbx_static_mesh(dict(settings, collision='none'))
            legacy = _legacy_fbx(settings)
            if legacy:
                U.SystemLibrary.execute_console_command(None, 'Interchange.FeatureFlags.Import.FBX 0')
            try:
                lod = _import(resolve(source), f'{TRANSIENT}/{name}', fbx)
            finally:
                if legacy:
                    U.SystemLibrary.execute_console_command(None, 'Interchange.FeatureFlags.Import.FBX 1')
        else:
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
        screens = [screen for _, screen, _, _ in chain]
        editor.set_lod_screen_sizes(asset, screens)
        got = [float(s) for s in editor.get_lod_screen_sizes(asset)][:len(chain)]
        if len(got) != len(chain) or any(abs(a - b) > 1e-3 for a, b in zip(got, screens)):
            raise RuntimeError(f'{asset.get_path_name()} has LOD screen sizes {got}, the record {screens}')
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


def _scrub_import_data(asset, package):
    """An existing instance's donor provenance, blanked before the save as scrub_import_data.py does it: each recorded
    source file, and an Interchange node graph that repeats them. The read-back refuses a save while any file is left."""
    try:
        data = asset.get_editor_property('asset_import_data')
    except Exception:
        data = None
    if data is None:
        return
    for slot in range(len(data.extract_filenames())):
        data.scripted_add_filename('', slot, '')
    if hasattr(data, 'set_node_container') and hasattr(U, 'InterchangeBaseNodeContainer'):
        data.set_node_container(U.new_object(U.InterchangeBaseNodeContainer, outer=data))
        if not U.ImportProvenance.rename_interchange_node(data, f'Factory_{asset.get_name()}'):
            raise RuntimeError(f'{package}: Interchange data without a renamable node ID')
    left = import_settings.donor_free(data.extract_filenames(), os.getcwd())
    if left:
        raise RuntimeError(f'{package} still names {left} after the scrub; not saved')


def _refuse_donor_names(asset, package, portable):
    """A texture's import data may keep only its repository-relative source: an absolute name (a checkout's, a home
    folder's) refuses the save. Checked after the portable source is set."""
    data = asset.get_editor_property('asset_import_data')
    if data is None:
        return
    left = import_settings.donor_named(data.extract_filenames(), os.getcwd(), portable)
    if left:
        raise RuntimeError(f'{package} names a donor path {left} after the portable source; not saved')


def _override_names(instance):
    """The names of the scalar, vector and texture parameters the instance itself saves, by kind."""
    def names(prop):
        return {str(p.get_editor_property('parameter_info').get_editor_property('name'))
                for p in instance.get_editor_property(prop)}
    return {'scalars': names('scalar_parameter_values'), 'vectors': names('vector_parameter_values'),
            'textures': names('texture_parameter_values')}


def _undeclared_overrides(instance, settings):
    """Sorted `kind:name` of every saved override the record's settings do not state."""
    return sorted(f'{kind}:{name}' for kind, have in _override_names(instance).items()
                  for name in have - set(settings.get(kind, {})))


def _switch_value(MEL, instance, name):
    """A static switch's value as the editor reads it (the call may return the value alone or a (value, found) pair)."""
    got = MEL.get_material_instance_static_switch_parameter_value(instance, name)
    if isinstance(got, tuple):
        if len(got) > 1 and not got[1]:
            raise RuntimeError(f'{instance.get_path_name()} has no static switch {name}')
        got = got[0]
    return bool(got)


def unknown_switches(stated, names):
    """Sorted switch names the row states that the instance does not have: a misspelt name would otherwise read back as
    false, the editor's answer for a missing switch, and pass as verified."""
    return sorted(set(stated) - set(names))


def stale_switches(stated, own, inherited):
    """Sorted names of the static switches the row does not state whose value differs from the parent's, or whose parent
    value cannot be read. `own` and `inherited` map each switch name to the instance's and the parent's value. Such a
    switch may be an earlier override the record no longer asks for: UE 5.8's clear does not reach static switches, so
    the import refuses it instead."""
    return sorted(n for n, v in own.items() if n not in stated and (n not in inherited or v != inherited[n]))


def _parent_switch_values(MEL, parent, names):
    """The parent's value of each switch: an instance parent reads like the instance, a base material its default."""
    out = {}
    for name in names:
        try:
            if isinstance(parent, U.MaterialInstance):
                out[name] = _switch_value(MEL, parent, name)
            else:
                got = MEL.get_material_default_static_switch_parameter_value(parent, name)
                out[name] = bool(got[0] if isinstance(got, tuple) else got)
        except Exception:
            pass   # a switch the parent cannot report is left out; stale_switches then refuses it unless stated
    return out


def _base_flags(overrides):
    """The Python name of every bOverride_* flag (material_base.py); one that cannot be read stops the import before
    any save."""
    return material_base.flags(overrides)


def base_value(value):
    """A base-property value as a record states it: an enum by its name, a float to six places, a bool as it is."""
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return round(value, 6)
    name = getattr(value, 'name', None)
    return str(name) if name is not None else value


def base_matches(stated, read):
    """True when the overrides read back are exactly the ones the row states, with the same values."""
    if set(stated) != set(read):
        return False
    for name, want in stated.items():
        got = read[name]
        if isinstance(want, bool) or isinstance(want, str):
            if got != want:
                return False
        elif isinstance(got, bool) or not isinstance(got, (int, float)) or abs(float(got) - float(want)) > 1e-4:
            return False
    return True


def _write_base(instance, base, package):
    """Set each base-property override the row states, with its value, and clear every other override flag: a donor
    override the record does not state would otherwise survive the parameter clear."""
    overrides = instance.get_editor_property('base_property_overrides')
    flags = _base_flags(overrides)
    unknown = sorted(set(base) - {flag[len('override_'):] for flag in flags})
    if unknown:
        raise RuntimeError(f'{package} has no base override {", ".join(unknown)}; nothing is saved')
    for flag in flags:
        name = flag[len('override_'):]
        overrides.set_editor_property(flag, name in base)
        if name in base:
            value = base[name]
            overrides.set_editor_property(name, getattr(U.BlendMode, value) if name == 'blend_mode' else value)
    instance.set_editor_property('base_property_overrides', overrides)


def read_base(instance):
    """{name: value} of every base-property override the instance sets; a value this Python cannot read is None."""
    overrides = instance.get_editor_property('base_property_overrides')
    out = {}
    for flag in _base_flags(overrides):
        if overrides.get_editor_property(flag):
            name = flag[len('override_'):]
            try:
                out[name] = base_value(overrides.get_editor_property(name))
            except Exception:
                out[name] = None
    return out


def _material_instances(plan, settings):
    """Write each planned material instance in place: its parent and the parameter values the record states, nothing
    else. A new package is created; an existing one keeps its object path, so references to it survive, and its donor
    import data is scrubbed first. The values are read back before the save, because UE 5.8's setters report False
    (tint_material.py), so the read is the proof. Parameter names come from the record (BaseColorTexture, BaseColorFactor,
    RoughnessFactor, ...). Static switches are written where the row states them; one it does not state must read the
    parent's value, or the import is refused. Base-property overrides are exactly the row's `base`, every other cleared."""
    MEL = U.MaterialEditingLibrary
    for row in import_settings.material_instances(settings, plan['packages']):
        package, parent_path = row['package'], row['parent']
        # EditorAssetLibrary does not load engine plugin content (the Interchange default instances) and logs an error that
        # fails the session, so a parent outside /Game goes through unreal.load_asset (a read-only probe, 2026-11-10).
        parent = EAL.load_asset(parent_path) if parent_path.startswith('/Game/') else U.load_asset(parent_path)
        if parent is None:
            raise RuntimeError(f'the parent {parent_path} is not in the project')
        if EAL.does_asset_exist(package):
            instance = EAL.load_asset(package)
            if isinstance(instance, U.MaterialInstanceConstant):
                _scrub_import_data(instance, package)
        else:
            folder, name = package.rsplit('/', 1)
            instance = TOOLS.create_asset(name, folder, U.MaterialInstanceConstant,
                                          U.MaterialInstanceConstantFactoryNew())
        if not isinstance(instance, U.MaterialInstanceConstant):
            raise RuntimeError(f'{package} is not a material instance')
        instance.set_editor_property('parent', parent)   # the editable parent property, as the saved records hold it
        # Every earlier override goes first, so a value the row no longer states falls back to the parent. This clears the
        # scalar, vector and texture overrides only: a read-only editor probe (2026-11-10) showed UE 5.8's clear leaves
        # static switches as they were. So every switch the row states is written below, and a switch it does not state
        # must read the parent's value, or the import is refused before the save (stale_switches).
        MEL.clear_all_material_instance_parameters(instance)
        for name, texture_path in sorted(row['textures'].items()):
            texture = EAL.load_asset(texture_path)
            if texture is None:
                raise RuntimeError(f'texture {texture_path} is not in the project')
            MEL.set_material_instance_texture_parameter_value(instance, name, texture)
        for name, value in sorted(row['scalars'].items()):
            MEL.set_material_instance_scalar_parameter_value(instance, name, float(value))
        for name, value in sorted(row['vectors'].items()):
            MEL.set_material_instance_vector_parameter_value(instance, name, U.LinearColor(*map(float, value)))
        names = {str(n) for n in MEL.get_static_switch_parameter_names(instance)}
        unknown = unknown_switches(row['switches'], names)
        if unknown:
            raise RuntimeError(f'{package} has no static switch {", ".join(unknown)}; nothing is saved')
        for name, value in sorted(row['switches'].items()):
            MEL.set_material_instance_static_switch_parameter_value(instance, name, bool(value))
        _write_base(instance, row['base'], package)
        MEL.update_material_instance(instance)
        # The read-back: the parent, every value the record states, and no donor path in the import data.
        if instance.get_editor_property('parent') != parent:
            raise RuntimeError(f'{package} does not read back its parent {parent_path}')
        for name, texture_path in sorted(row['textures'].items()):
            got = MEL.get_material_instance_texture_parameter_value(instance, name)
            if got is None or got.get_path_name().split('.')[0] != texture_path:
                raise RuntimeError(f'{package} {name} reads {got} instead of {texture_path}')
        for name, value in sorted(row['scalars'].items()):
            got = float(MEL.get_material_instance_scalar_parameter_value(instance, name))
            if abs(got - float(value)) > 1e-4:
                raise RuntimeError(f'{package} {name} reads {got} instead of {value}')
        for name, value in sorted(row['vectors'].items()):
            got = MEL.get_material_instance_vector_parameter_value(instance, name)
            want = list(map(float, value))
            if max(abs(a - b) for a, b in zip([got.r, got.g, got.b, got.a], want)) > 1e-4:
                raise RuntimeError(f'{package} {name} reads {got} instead of {value}')
        for name, value in sorted(row['switches'].items()):
            if _switch_value(MEL, instance, name) != bool(value):
                raise RuntimeError(f'{package} {name} reads {_switch_value(MEL, instance, name)} instead of {value}')
        own = {name: _switch_value(MEL, instance, name) for name in names}
        stale = stale_switches(row['switches'], own, _parent_switch_values(MEL, parent, names))
        if stale:
            raise RuntimeError(f'{package} keeps static switch overrides its record does not state: {", ".join(stale)}')
        base = read_base(instance)
        if not base_matches(row['base'], base):
            raise RuntimeError(f'{package} reads base overrides {base} instead of {row["base"]}')
        stray = _undeclared_overrides(instance, row)
        if stray:
            raise RuntimeError(f'{package} keeps overrides its record does not state: {", ".join(stray)}')
        data = instance.get_editor_property('asset_import_data')
        if data is not None and import_settings.donor_free(data.extract_filenames(), os.getcwd()):
            raise RuntimeError(f'{package} still names a donor file in its import data; not saved')
        if not EAL.save_asset(package, only_if_is_dirty=False):
            raise RuntimeError(f'could not save {package}')
        U.log(f'V2 import wrote {package} from parent {parent_path}')


def _material_master(plan):
    """@cc [owner:fontanierh,label:correctness] importer-writes-only-record-outputs
    Rebuild one generator master from its pinned builder and save it only when its wiring digest equals the saved original's
    (master_digest.accept). The rebuild first goes to a transient package, which is compared and deleted and never saved. Only
    an accepted rebuild is saved, into the record's one output package, and read back against the same digest. Nothing else is
    written: a builder error, a difference, or an unreadable digest refuses before the save.

    Before the rebuild over the original, every expression of the original is deleted one by one and the graph is checked
    empty: delete_all_material_expressions leaves some unwired leftovers in 5.8, and a rebuild over them would grow the
    package on every import. The saved master is therefore the fresh build, and its read-back has exactly the fresh
    build's unwired expressions."""
    if not plan['sources'] or len(plan['packages']) != 1:
        raise RuntimeError('a material master names an entry builder with optional helpers and builds one package')
    game = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(game / 'tools/content'))
    import authority
    asset = authority.discovered(game).by_id.get(plan['asset'])
    contents = _checked_master_sources(game, asset, plan)
    with _master_builder(plan['sources'], plan['settings']['builder'], source_bytes=contents) as builder:
        _material_master_with_builder(plan, builder)


def _material_master_with_builder(plan, builder):
    """The existing scratch, save and read-back route while this record's source namespace remains loaded."""
    settings = plan['settings']
    reads = {}
    for path in settings.get('reads', []):
        loaded = U.load_asset(path) if path.startswith('/Engine/') else EAL.load_asset(path)
        if loaded is None:
            raise RuntimeError(f'read {path} is not in the project')
        reads[path] = loaded
    package = plan['packages'][0]
    arguments = dict(settings.get('arguments', {}))
    if not EAL.does_asset_exist(package):
        raise RuntimeError(f'{package} has no saved original to compare with; a master is rebuilt only over its original')
    saved = master_digest.read(EAL.load_asset(package))
    scratch = f'{TRANSIENT}/MasterCheck/{package.rsplit("/", 1)[1]}'
    if EAL.does_asset_exist(scratch):
        EAL.delete_asset(scratch)
    try:
        fresh = master_digest.read(builder(scratch, reads, **arguments))
        problems = master_digest.accept(saved, fresh)
    finally:
        if EAL.does_asset_exist(scratch):
            EAL.delete_asset(scratch)
    if problems:
        raise RuntimeError(f'{package} is not accepted: ' + '; '.join(problems[:8]))
    original = EAL.load_asset(package)
    MEL = U.MaterialEditingLibrary
    for expression in list(MEL.get_material_expressions(original) or []):
        MEL.delete_material_expression(original, expression)
    if MEL.get_num_material_expressions(original):
        raise RuntimeError(f'{package}: {MEL.get_num_material_expressions(original)} expression(s) survive deletion; nothing saved')
    builder(package, reads, **arguments)
    if not EAL.save_asset(package, only_if_is_dirty=False):
        raise RuntimeError(f'could not save {package}')
    back = master_digest.read(EAL.load_asset(package))
    problems = master_digest.accept(saved, back)
    if 'error' not in back and sorted(back.get('unwired', [])) != sorted(fresh.get('unwired', [])):
        problems.append(f'{len(back.get("unwired", []))} unwired expression(s) after the save, the fresh build has '
                        f'{len(fresh.get("unwired", []))}')
    if problems:
        raise RuntimeError(f'{package} reads back different from its saved original: ' + '; '.join(problems[:8]))
    U.log(f'V2 import wrote {package} from {plan["portable_sources"][0]}')


def main():
    if not U.V2SaveGuard.is_active():
        raise RuntimeError('the V2 save guard is not active (V2_SAVE_ALLOW); an import runs only through its build step')
    plan = json.loads(open(os.environ['V2_IMPORT_PLAN']).read())
    settings = plan['settings']
    if plan['importer'] == 'material-master':
        _material_master(plan)
        U.log(MARKER)
        return
    if plan['importer'] == 'material-instance':
        # A material instance pins no source file: its inputs are the parent and textures already in the project.
        _material_instances(plan, settings)
        U.log(MARKER)
        return
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
            # A new package is checked first: loading a missing one logs an error, which fails the session's exit.
            existing = EAL.load_asset(package) if EAL.does_asset_exist(package) else None
            # Read before any edit: removing collisions rebuilds the mesh, whose screen sizes then read 0 until built.
            before = lod_preservation.read(_static_mesh_editor(), existing) if existing is not None else None
            if existing is not None and settings.get('collision') == 'simple_and_complex':
                # An FBX reimport appends its UCX hulls to the saved ones: start from none.
                _static_mesh_editor().remove_collisions(existing)
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
            if resolve is not None:
                # The collision settings rebuild the mesh, whose screen sizes then read 0: the chain's are set again.
                _static_mesh_editor().set_lod_screen_sizes(asset, [screen for _, screen, _, _ in settings['lod_chain']])
            reduction = import_settings.reduction_plan(settings)
            if existing is None and reduction is not None and asset.get_num_lods() == 1:
                # A new package takes the record's reduction plan (the donor's generate_lods, which the donor ran on every
                # Brine Cove plant): preserve() below restores a chain only when the package already had one.
                levels = _static_mesh_editor()
                if levels.set_lods(asset, _reduction_options(reduction)) != len(reduction):
                    raise RuntimeError(f'{package}: the LOD reduction plan did not set {len(reduction)} levels')
                levels.set_lod_screen_sizes(asset, [screen for _, screen in reduction])
            after = lod_preservation.preserve(_static_mesh_editor(), asset, before, settings.get('lods'),
                                              _reduction_options)
            lod_results[package] = {'before': before, 'after': after}
        elif plan['importer'] == 'texture':
            asset = _import(source, package, _texture(settings))
            _apply_texture_settings(asset, settings)
            # The import recorded its source at this checkout's absolute path: blank it, and the node graph that repeats
            # it, before the repository-relative source is set; then refuse any absolute name left (as scrub does).
            _scrub_import_data(asset, package)
        else:
            raise RuntimeError(f'no editor importer {plan["importer"]}')
        _portable_source(asset, portable)
        if plan['importer'] == 'texture':
            _refuse_donor_names(asset, package, portable)
        if not EAL.save_asset(package, only_if_is_dirty=False):
            raise RuntimeError(f'could not save {package}')
        U.log(f'V2 import wrote {package} from {portable}')
    if lod_results:   # read back by tools/import/run.py, which records the chains in verified.json
        Path(os.environ['V2_IMPORT_PLAN']).with_name(LOD_RESULT).write_text(json.dumps(lod_results, indent=1) + '\n')
    U.log(MARKER)


main()
