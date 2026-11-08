"""Small Unreal asset helpers. Callers own every package they pass here."""
import os
import unreal

AT = unreal.AssetToolsHelpers.get_asset_tools()
MEL = unreal.MaterialEditingLibrary
EAL = unreal.EditorAssetLibrary
LOG = unreal.log


def opt(obj, name, value):
    try:
        obj.set_editor_property(name, value)
    except Exception as e:
        LOG(f"  (skipped {name}: {e})")


def import_texture(path, dest):
    task = unreal.AssetImportTask()
    task.filename = path; task.destination_path = dest; task.automated = True; task.replace_existing = True; task.save = True
    AT.import_asset_tasks([task])
    p = list(task.imported_object_paths)
    texture = EAL.load_asset(p[0]) if p else None
    if texture and os.path.basename(path).startswith(('T_grass', 'T_leaf_', 'T_flower')):
        # Preserve the painted silhouette when sampling smaller mips. Sharpened
        # mips make thin alpha edges crawl; unsharpened averages stay quiet.
        texture.set_editor_property('do_scale_mips_for_alpha_coverage', True)
        texture.set_editor_property('alpha_coverage_thresholds', unreal.Vector4(0, 0, 0, .4))
        texture.set_editor_property('mip_gen_settings', unreal.TextureMipGenSettings.TMGS_SIMPLE_AVERAGE)
        EAL.save_loaded_asset(texture)
    return texture


def node(m, cls, x, y, **props):
    e = MEL.create_material_expression(m, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def link(a, ao, b, bi):
    MEL.connect_material_expressions(a, ao, b, bi)


def save_material(material):
    errors = MEL.recompile_material(material)
    if errors:
        raise RuntimeError(f'{material.get_path_name()}: material compile failed: {errors}')
    if not EAL.save_loaded_asset(material):
        raise RuntimeError('Could not save material: ' + material.get_path_name())


def create(name, cls, factory):
    """Reuse named generated assets without emitting an unattended creation error."""
    path = f"/Game/Japan/Materials/{name}"
    a = EAL.load_asset(path) if EAL.does_asset_exist(path) else None
    if a is not None:
        if not isinstance(a, cls):
            raise TypeError(f"Unexpected asset class at {path}: {type(a)}")
        if isinstance(a, unreal.Material):
            MEL.delete_all_material_expressions(a)
        LOG(f"  reused existing {path}")
    else:
        a = AT.create_asset(name, "/Game/Japan/Materials", cls, factory)
    if a is None:
        raise RuntimeError(f"Failed to create {path}")
    return a


def instance(name, parent, tex=None, tint=None):
    mi = create(name, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    MEL.clear_all_material_instance_parameters(mi)
    mi.set_editor_property('base_property_overrides', unreal.MaterialInstanceBasePropertyOverrides())
    MEL.set_material_instance_parent(mi, parent)
    if tex is not None:
        ok = MEL.set_material_instance_texture_parameter_value(mi, "Tex", tex)
        LOG(f"  {name}: Tex <- {tex.get_name()} ok={ok} readback={MEL.get_material_instance_texture_parameter_value(mi, 'Tex')}")
    if tint is not None: MEL.set_material_instance_vector_parameter_value(mi, "Tint", unreal.LinearColor(*tint, 1.0))
    MEL.update_material_instance(mi); EAL.save_loaded_asset(mi)
    return mi
