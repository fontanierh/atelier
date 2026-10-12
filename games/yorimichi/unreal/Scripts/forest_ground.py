"""Physical forest floor shared by FarHills and the northern countryside.

The distant forest's mass comes from its HISM crowns. Ground uses meadow grain,
never a flat image of tree tops.
"""
import unreal as U
import atmosphere


def material():
    E=U.EditorAssetLibrary;M=U.MaterialEditingLibrary;AT=U.AssetToolsHelpers.get_asset_tools()
    path='/Game/Japan/Materials/M_ForestGround'
    m=E.load_asset(path) if E.does_asset_exist(path) else AT.create_asset('M_ForestGround','/Game/Japan/Materials',U.Material,U.MaterialFactoryNew())
    M.delete_all_material_expressions(m)
    def node(cls,**props):
        n=M.create_material_expression(m,cls)
        for k,v in props.items():n.set_editor_property(k,v)
        return n
    p=node(U.MaterialExpressionWorldPosition)
    base=node(U.MaterialExpressionCustom,output_type=U.CustomMaterialOutputType.CMOT_FLOAT3,
              code='''float n=smoothstep(300000.,330000.,-P.y);
float3 colour=lerp(float3(.055,.11,.035),float3(.105,.145,.055),n);
return colour;''')
    a=U.CustomInput();a.set_editor_property('input_name','P');base.set_editor_property('inputs',[a])
    assert M.connect_material_expressions(p,'',base,'P')
    fill=node(U.MaterialExpressionConstant,r=0.)
    shaded,emission=atmosphere.apply(m,base,fill)
    M.connect_material_property(shaded,'',U.MaterialProperty.MP_BASE_COLOR)
    M.connect_material_property(emission,'',U.MaterialProperty.MP_EMISSIVE_COLOR)
    M.connect_material_property(node(U.MaterialExpressionConstant,r=1.),'',U.MaterialProperty.MP_ROUGHNESS)
    M.connect_material_property(node(U.MaterialExpressionConstant,r=0.),'',U.MaterialProperty.MP_SPECULAR)
    m.set_editor_property('used_with_instanced_static_meshes',True)
    M.recompile_material(m);E.save_loaded_asset(m)
    return m
