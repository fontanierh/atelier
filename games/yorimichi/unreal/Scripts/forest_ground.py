"""Physical forest floor shared by FarHills and the northern countryside.

The distant forest's mass comes from its HISM crowns. Ground uses meadow grain,
never a flat image of tree tops.
"""
import json
import sys
from pathlib import Path
import unreal as U
import atmosphere
import ground_grain
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'world'))
import yori  # noqa: E402


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
    vc=node(U.MaterialExpressionVertexColor)
    near=node(U.MaterialExpressionScalarParameter,parameter_name='NearGround',default_value=0.)
    near_tex=node(U.MaterialExpressionTextureObject,texture=E.load_asset('/Game/Japan/Textures/T_ground'))
    detail=E.load_asset('/Game/Japan/Textures/T_ground_detail');assert detail
    tex=node(U.MaterialExpressionTextureObject,texture=detail)
    # The forest floor brightens over the 300 m north of Belmonte's southern join (belmonte/appearance.py far_palette).
    join=json.loads((yori.OUT/'hidamari/north_snow.json').read_text())['south_join_m']*100
    base=node(U.MaterialExpressionCustom,output_type=U.CustomMaterialOutputType.CMOT_FLOAT3,
              code=f'float n=smoothstep({join:.0f}.,{join+30000:.0f}.,-P.y);'+'''
float3 colour=lerp(float3(.055,.11,.035),float3(.105,.145,.055),n);
float3 nearColour=Texture2DSample(NearTex,NearTexSampler,float2(P.x,-P.y)/600.).rgb;
colour=lerp(colour,nearColour,Near);
float3 coast=lerp(C.rgb/12.92,pow((C.rgb+.055)/1.055,2.4),step(.04045,C.rgb));
colour=lerp(colour,coast,Alpha);
'''+ground_grain.code('Tex','TexSampler','P')+'\nreturn colour*lerp(groundDetail,1,Near*(1-Alpha));')
    args=[]
    for key in ['P','Tex','NearTex','Near','C','Alpha']:
        a=U.CustomInput();a.set_editor_property('input_name',key);args.append(a)
    base.set_editor_property('inputs',args)
    assert M.connect_material_expressions(p,'',base,'P')
    assert M.connect_material_expressions(tex,'',base,'Tex')
    for src,out,key in [(near_tex,'','NearTex'),(near,'','Near'),(vc,'','C'),(vc,'A','Alpha')]:
        assert M.connect_material_expressions(src,out,base,key)
    fill=node(U.MaterialExpressionConstant,r=0.)
    shaded,emission=atmosphere.apply(m,base,fill)
    M.connect_material_property(shaded,'',U.MaterialProperty.MP_BASE_COLOR)
    M.connect_material_property(emission,'',U.MaterialProperty.MP_EMISSIVE_COLOR)
    M.connect_material_property(node(U.MaterialExpressionConstant,r=1.),'',U.MaterialProperty.MP_ROUGHNESS)
    M.connect_material_property(node(U.MaterialExpressionConstant,r=0.),'',U.MaterialProperty.MP_SPECULAR)
    m.set_editor_property('used_with_instanced_static_meshes',True)
    M.recompile_material(m);E.save_loaded_asset(m)
    return m


def coast_instance(parent=None):
    from material_assets import instance
    mi=instance('MI_Coast',parent or material())
    U.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(mi,'NearGround',1.)
    U.MaterialEditingLibrary.update_material_instance(mi)
    U.EditorAssetLibrary.save_loaded_asset(mi)
    return mi
