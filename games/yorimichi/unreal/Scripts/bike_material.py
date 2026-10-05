"""M_Bike: the bike's vertex-colour palette with its finish mask (vertex alpha: 0 matte, .5 enamel, .65 satin, 1 chrome)."""
import unreal as U
E = U.EditorAssetLibrary; M = U.MaterialEditingLibrary


def material():
    path = '/Game/Japan/Materials/M_Bike'
    mat = E.load_asset(path) if E.does_asset_exist(path) else U.AssetToolsHelpers.get_asset_tools().create_asset('M_Bike', '/Game/Japan/Materials', U.Material, U.MaterialFactoryNew())
    M.delete_all_material_expressions(mat)

    def custom(code, names, output=U.CustomMaterialOutputType.CMOT_FLOAT3):
        n = M.create_material_expression(mat, U.MaterialExpressionCustom, -200, 0)
        n.set_editor_property('code', code); n.set_editor_property('output_type', output)
        args = []
        for key in names:
            arg = U.CustomInput(); arg.set_editor_property('input_name', key); args.append(arg)
        n.set_editor_property('inputs', args)
        return n

    vc = M.create_material_expression(mat, U.MaterialExpressionVertexColor, -600, 0)
    colour = custom('return lerp(C/12.92,pow((C+.055)/1.055,2.4),step(.04045,C));', ['C'])
    # Same curves as the Blender preview in assets/vehicles/bike/build.py: paint stays dielectric, chrome is metal.
    metal = custom('return saturate((A-.5)*2.5);', ['A'], U.CustomMaterialOutputType.CMOT_FLOAT1)
    rough = custom('return lerp(.78,.22,A);', ['A'], U.CustomMaterialOutputType.CMOT_FLOAT1)
    assert M.connect_material_expressions(vc, '', colour, 'C')
    assert M.connect_material_expressions(vc, 'A', metal, 'A')
    assert M.connect_material_expressions(vc, 'A', rough, 'A')
    assert M.connect_material_property(colour, '', U.MaterialProperty.MP_BASE_COLOR)
    assert M.connect_material_property(metal, '', U.MaterialProperty.MP_METALLIC)
    assert M.connect_material_property(rough, '', U.MaterialProperty.MP_ROUGHNESS)
    M.recompile_material(mat); E.save_loaded_asset(mat)
    return mat
