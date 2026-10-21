"""Legacy FBX mesh import with explicit seed ownership and fresh material slots."""
from pathlib import Path
import unreal
from atelier.unreal_mesh_reuse import common_fbx_mesh

EAL = unreal.EditorAssetLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()


def import_mesh(path, dest, name, *, seed, fresh_slots=False):
    """@cc [owner:fontanierh,label:correctness] legacy-fbx-migration-before-reimport
    New and non-FBX packages MUST establish legacy FBX import data before the final source pass.
    Existing package identity MUST stay stable, and the final pass MUST apply the declared unit settings.
    Reuse MUST verify current source/options and defer receipts until the owning guarded script succeeds.

    The caller supplies an owned seed; borrowing another region's export hides a build dependency.
    UE converts Interchange import data to legacy FBX defaults before applying task options.
    That first pass must establish FBX data so the final pass can synchronize unit settings.
    """
    mesh, reuse = common_fbx_mesh(path, dest, name, seed=seed, fresh_slots=fresh_slots,
                                  script=__file__, validator=legacy_options_match,
                                  owner_roots=(Path(__file__).resolve().parents[2] / 'world',
                                               Path(__file__).resolve().parents[2] / 'world/regions'))
    if mesh is None:
        existing = EAL.load_asset(dest + '/' + name) if EAL.does_asset_exist(dest + '/' + name) else None
        legacy = existing is not None and isinstance(existing.get_editor_property('asset_import_data'), unreal.FbxStaticMeshImportData)
        if not legacy and (existing is not None or Path(path).resolve() != Path(seed).resolve()):
            seeded = _import_mesh(seed, dest, name)
            if not isinstance(seeded.get_editor_property('asset_import_data'), unreal.FbxStaticMeshImportData):
                raise RuntimeError('FBX seed did not establish legacy import data: ' + name)
        mesh = _import_mesh(path, dest, name, fresh_slots)
        if reuse is not None:
            reuse.imported(dest + '/' + name)
    if reuse is not None:
        reuse.defer_validated(dest + '/' + name)
    return mesh


def legacy_options_match(mesh):
    data = mesh.get_editor_property('asset_import_data')
    if not isinstance(data, unreal.FbxStaticMeshImportData):
        return False
    settings = dict(combine_meshes=True, generate_lightmap_u_vs=False, auto_generate_collision=False,
        convert_scene=True, convert_scene_unit=True, import_uniform_scale=1.0, build_nanite=False,
        one_convex_hull_per_ucx=True, vertex_color_import_option=unreal.VertexColorImportOption.REPLACE,
        normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
    return all(data.get_editor_property(key) == value for key, value in settings.items())


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
            for key in ('combine_meshes', 'generate_lightmap_u_vs', 'auto_generate_collision', 'convert_scene',
                        'convert_scene_unit', 'import_uniform_scale', 'one_convex_hull_per_ucx',
                        'vertex_color_import_option', 'normal_import_method'):
                prior.set_editor_property(key, data.get_editor_property(key))
        if fresh_slots:
            existing.set_editor_property('static_materials', [])
    task.options = ui
    AT.import_asset_tasks([task])
    mesh = EAL.load_asset(dest + '/' + name)
    if not mesh or not task.imported_object_paths:
        raise RuntimeError('FBX import failed: ' + name)
    return mesh
