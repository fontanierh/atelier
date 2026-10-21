"""Matte painted kart palette; the authored vertex colors are sRGB, as in the world palette."""
import unreal as U


def material():
    editing, library = U.MaterialEditingLibrary, U.EditorAssetLibrary
    path = '/Game/Japan/Kart/M_Kart'
    mat = library.load_asset(path) if library.does_asset_exist(path) else U.AssetToolsHelpers.get_asset_tools().create_asset(
        'M_Kart', '/Game/Japan/Kart', U.Material, U.MaterialFactoryNew())
    editing.delete_all_material_expressions(mat)
    vc = editing.create_material_expression(mat, U.MaterialExpressionVertexColor, -500, 0)
    linear = editing.create_material_expression(mat, U.MaterialExpressionCustom, -250, 0)
    linear.set_editor_property('code', 'return lerp(C/12.92,pow((C+.055)/1.055,2.4),step(.04045,C));')
    linear.set_editor_property('output_type', U.CustomMaterialOutputType.CMOT_FLOAT3)
    argument = U.CustomInput(); argument.set_editor_property('input_name', 'C')
    linear.set_editor_property('inputs', [argument])
    assert editing.connect_material_expressions(vc, '', linear, 'C')
    tint = editing.create_material_expression(mat, U.MaterialExpressionVectorParameter, -250, -180)
    tint.set_editor_property('parameter_name', 'Tint'); tint.set_editor_property('default_value', U.LinearColor(1, 1, 1, 1))
    multiply = editing.create_material_expression(mat, U.MaterialExpressionMultiply, 0, 0)
    assert editing.connect_material_expressions(linear, '', multiply, 'A')
    assert editing.connect_material_expressions(tint, '', multiply, 'B')
    assert editing.connect_material_property(multiply, '', U.MaterialProperty.MP_BASE_COLOR)
    for prop, value in ((U.MaterialProperty.MP_ROUGHNESS, .82), (U.MaterialProperty.MP_SPECULAR, .2)):
        node = editing.create_material_expression(mat, U.MaterialExpressionConstant, -250, 200)
        node.set_editor_property('r', value)
        assert editing.connect_material_property(node, '', prop)
    editing.recompile_material(mat)
    library.save_loaded_asset(mat)
    return mat
