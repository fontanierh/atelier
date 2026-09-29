"""The flat-shaded character material, on its own so it can be rebuilt without reimporting meshes.

    create()            # /Game/CapeBoy/M_CapeBoy

Restores the original soft vertex-colour shading: constant 0.30 albedo fill, with no Fresnel rim.
"""
import unreal as U

DEST = '/Game/CapeBoy'
FILL = .30   # original uniform self-illumination, as a fraction of albedo


def create():
    E = U.EditorAssetLibrary
    M = U.MaterialEditingLibrary
    path = DEST+'/M_CapeBoy'
    material = (E.load_asset(path) if E.does_asset_exist(path) else
                U.AssetToolsHelpers.get_asset_tools().create_asset('M_CapeBoy', DEST, U.Material, U.MaterialFactoryNew()))
    M.delete_all_material_expressions(material)
    material.set_editor_property('used_with_skeletal_mesh', True)
    material.set_editor_property('two_sided', True)
    vc = M.create_material_expression(material, U.MaterialExpressionVertexColor, -500, 0)
    linear = M.create_material_expression(material, U.MaterialExpressionCustom, -300, 0)
    linear.set_editor_property('code', 'return lerp(C/12.92,pow((C+0.055)/1.055,2.4),step(0.04045,C));')
    linear.set_editor_property('output_type', U.CustomMaterialOutputType.CMOT_FLOAT3)
    pin = U.CustomInput(); pin.set_editor_property('input_name', 'C')
    linear.set_editor_property('inputs', [pin])
    assert M.connect_material_expressions(vc, '', linear, 'C')
    assert M.connect_material_property(linear, '', U.MaterialProperty.MP_BASE_COLOR)
    for prop, value, y in [(U.MaterialProperty.MP_ROUGHNESS, 1., 100), (U.MaterialProperty.MP_SPECULAR, 0., 180)]:
        constant = M.create_material_expression(material, U.MaterialExpressionConstant, -200, y)
        constant.set_editor_property('r', value)
        assert M.connect_material_property(constant, '', prop)
    fill = M.create_material_expression(material, U.MaterialExpressionMultiply, -100, 280)
    fill.set_editor_property('const_b', FILL)
    assert M.connect_material_expressions(linear, '', fill, 'A')
    assert M.connect_material_property(fill, '', U.MaterialProperty.MP_EMISSIVE_COLOR)
    M.recompile_material(material)
    E.save_loaded_asset(material)
    return material
