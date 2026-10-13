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
    detail=E.load_asset('/Game/Japan/Textures/T_ground_detail');assert detail
    tex=node(U.MaterialExpressionTextureObject,texture=detail)
    # The forest floor brightens over the 300 m north of Belmonte's southern join (belmonte/appearance.py far_palette).
    join=json.loads((yori.OUT/'hidamari/north_snow.json').read_text())['south_join_m']*100
    base=node(U.MaterialExpressionCustom,output_type=U.CustomMaterialOutputType.CMOT_FLOAT3,
              code=f'float n=smoothstep({join:.0f}.,{join+30000:.0f}.,-P.y);'+'''
float3 colour=lerp(float3(.055,.11,.035),float3(.105,.145,.055),n);
'''+ground_grain.code('Tex','TexSampler','P')+'\nreturn colour*groundDetail;')
    args=[]
    for key in ['P','Tex']:
        a=U.CustomInput();a.set_editor_property('input_name',key);args.append(a)
    base.set_editor_property('inputs',args)
    assert M.connect_material_expressions(p,'',base,'P')
    assert M.connect_material_expressions(tex,'',base,'Tex')
    fill=node(U.MaterialExpressionConstant,r=0.)
    shaded,emission=atmosphere.apply(m,base,fill)
    M.connect_material_property(shaded,'',U.MaterialProperty.MP_BASE_COLOR)
    M.connect_material_property(emission,'',U.MaterialProperty.MP_EMISSIVE_COLOR)
    M.connect_material_property(node(U.MaterialExpressionConstant,r=1.),'',U.MaterialProperty.MP_ROUGHNESS)
    M.connect_material_property(node(U.MaterialExpressionConstant,r=0.),'',U.MaterialProperty.MP_SPECULAR)
    m.set_editor_property('used_with_instanced_static_meshes',True)
    M.recompile_material(m);E.save_loaded_asset(m)
    return m
