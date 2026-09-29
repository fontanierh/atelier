"""Opaque vertex-colour landscape, with restrained blue atmospheric depth."""
import unreal

def material():
    e=unreal.EditorAssetLibrary;l=unreal.MaterialEditingLibrary
    path='/Game/Japan/Materials';name='M_NorthMountains'
    m=e.load_asset(path+'/'+name) if e.does_asset_exist(path+'/'+name) else unreal.AssetToolsHelpers.get_asset_tools().create_asset(name,path,unreal.Material,unreal.MaterialFactoryNew())
    l.delete_all_material_expressions(m)
    vc=l.create_material_expression(m,unreal.MaterialExpressionVertexColor,-500,0)
    depth=l.create_material_expression(m,unreal.MaterialExpressionPixelDepth,-500,200)
    c=l.create_material_expression(m,unreal.MaterialExpressionCustom,-100,0)
    c.set_editor_property('code','float3 base=lerp(C/12.92,pow((C+.055)/1.055,2.4),step(.04045,C)); float haze=saturate((D-80000)/220000)*.09; return lerp(base,float3(.16,.24,.34),haze);')
    c.set_editor_property('output_type',unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    args=[]
    for key in ('C','D'):
        a=unreal.CustomInput();a.set_editor_property('input_name',key);args.append(a)
    c.set_editor_property('inputs',args)
    l.connect_material_expressions(vc,'',c,'C');l.connect_material_expressions(depth,'',c,'D')
    l.connect_material_property(c,'',unreal.MaterialProperty.MP_BASE_COLOR)
    for prop,value in [(unreal.MaterialProperty.MP_ROUGHNESS,1.),(unreal.MaterialProperty.MP_SPECULAR,0.)]:
        n=l.create_material_expression(m,unreal.MaterialExpressionConstant,100,300);n.set_editor_property('r',value)
        l.connect_material_property(n,'',prop)
    m.set_editor_property('used_with_instanced_static_meshes',True)
    m.set_editor_property('dithered_lod_transition',True)
    l.recompile_material(m);e.save_loaded_asset(m)
    return m
