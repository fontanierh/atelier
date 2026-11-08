"""Legacy FBX mesh import using the actual source for migration and fresh material slots."""
from pathlib import Path
import unreal
from atelier.unreal_mesh_reuse import common_fbx_mesh

EAL = unreal.EditorAssetLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()


def import_mesh(path, dest, name, *, seed=None, fresh_slots=False, before_import=None, reuse_validator=None):
    """@cc [owner:fontanierh,label:correctness] legacy-fbx-migration-before-reimport
    Non-FBX packages MUST establish legacy FBX import data from their own source before the final source pass.
    Existing package identity MUST stay stable, and the final pass MUST apply the declared unit settings.
    Reuse MUST verify current source/options and defer receipts until the owning guarded script succeeds.
    Owner preparation MUST run only after admission misses, before the first actual source pass;
    it MUST NOT dirty a package before saved-byte admission or run on a validated reuse hit.
    A supplied current owner reuse requirement MUST run with legacy option validation before
    admission; failed requirements MUST use ordinary import and current finishing.

    The obsolete seed keyword is accepted for existing callers but is never read or imported.
    UE converts Interchange import data to legacy FBX defaults before applying task options.
    That first pass must establish FBX data so the final pass can synchronize unit settings.
    """
    from city_parent_transition import excluded_packages
    validator = legacy_options_match if reuse_validator is None else lambda mesh: _reuse_matches(mesh, reuse_validator)
    validation_functions = ('legacy_options_match',) if reuse_validator is None else ('legacy_options_match', '_reuse_matches')
    mesh, reuse = common_fbx_mesh(path, dest, name, fresh_slots=fresh_slots,
                                  script=__file__, functions=('_source_mesh',), validator=validator,
                                  validation_functions=validation_functions, owner_transition=excluded_packages,
                                  owner_roots=(Path(__file__).resolve().parents[2] / 'world',
                                               Path(__file__).resolve().parents[2] / 'world/regions'))
    if mesh is None:
        if before_import is not None:
            before_import()
        mesh = _source_mesh(path, dest, name, fresh_slots)
        if reuse is not None:
            reuse.imported(dest + '/' + name)
    if not legacy_options_match(mesh):
        raise RuntimeError('FBX import did not preserve declared options: ' + name)
    if reuse is not None:
        reuse.defer_validated(dest + '/' + name)
    return mesh


def _source_mesh(path, dest, name, fresh_slots=False):
    """The raw source pass, separate from receipt bookkeeping and owner finishing."""
    existing = EAL.load_asset(dest + '/' + name) if EAL.does_asset_exist(dest + '/' + name) else None
    legacy = existing is not None and isinstance(existing.get_editor_property('asset_import_data'), unreal.FbxStaticMeshImportData)
    if existing is not None and not legacy:
        migrated = _import_mesh(path, dest, name, True)
        if not isinstance(migrated.get_editor_property('asset_import_data'), unreal.FbxStaticMeshImportData):
            raise RuntimeError('Source pass did not establish legacy import data: ' + name)
        # Imported source slots replace migration/default palettes before the correctly
        # scaled pass. No unrelated mesh can contribute geometry or material slots.
        fresh_slots = True
    return _import_mesh(path, dest, name, fresh_slots)


def legacy_options_match(mesh):
    data = mesh.get_editor_property('asset_import_data')
    if not isinstance(data, unreal.FbxStaticMeshImportData):
        return False
    settings = dict(combine_meshes=True, generate_lightmap_u_vs=False, auto_generate_collision=False,
        convert_scene=True, convert_scene_unit=True, import_uniform_scale=1.0, build_nanite=False,
        one_convex_hull_per_ucx=True, vertex_color_import_option=unreal.VertexColorImportOption.REPLACE,
        normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
    # ReimportRestrict can preserve an existing mesh's actual Nanite state even
    # when stored import data says false. The live asset tag includes force-enable.
    actual_nanite = unreal.AssetRegistryHelpers.create_asset_data(mesh).get_tag_value('NaniteEnabled')
    return actual_nanite == 'False' and all(data.get_editor_property(key) == value for key, value in settings.items())


def _reuse_matches(mesh, owner_check):
    """The full owner source closure binds its current read-only requirement."""
    return legacy_options_match(mesh) and owner_check(mesh)


def _import_mesh(path, dest, name, fresh_slots=False):
    task = unreal.AssetImportTask()
    task.filename = str(path)
    task.destination_path = dest
    task.destination_name = name
    task.automated = True
    task.replace_existing = True
    task.replace_existing_settings = True
    task.save = True
    ui = unreal.FbxImportUI()
    ui.automated_import_should_detect_type = False
    ui.import_mesh = True
    ui.import_materials = False
    ui.import_textures = False
    ui.import_animations = False
    ui.import_as_skeletal = False
    ui.mesh_type_to_import = unreal.FBXImportType.FBXIT_STATIC_MESH
    data = ui.static_mesh_import_data
    settings = dict(
        combine_meshes=True, generate_lightmap_u_vs=False, auto_generate_collision=False,
        convert_scene=True, convert_scene_unit=True, import_uniform_scale=1.0, build_nanite=False,
        one_convex_hull_per_ucx=True, vertex_color_import_option=unreal.VertexColorImportOption.REPLACE,
        normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
    for key, value in settings.items():
        data.set_editor_property(key, value)
    # Legacy reimport reads the stored import-data object before task options.
    # Keep these in sync so unit scale and vertex colours update on every rebuild.
    existing = EAL.load_asset(dest + '/' + name) if EAL.does_asset_exist(dest + '/' + name) else None
    if existing:
        prior = existing.get_editor_property('asset_import_data')
        if isinstance(prior, unreal.FbxStaticMeshImportData):
            for key, value in settings.items():
                prior.set_editor_property(key, value)
        if fresh_slots:
            existing.set_editor_property('static_materials', [])
    task.options = ui
    AT.import_asset_tasks([task])
    mesh = EAL.load_asset(dest + '/' + name)
    if not mesh or not task.imported_object_paths:
        raise RuntimeError('FBX import failed: ' + name)
    return mesh
