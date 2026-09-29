"""Opaque arcade palette with restrained grain and warm paper lantern emission."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import unreal
from pathlib import Path


def texture(name):
    source=yori.REGIONS/'hidamari/textures'/f'{name}.png'
    task=unreal.AssetImportTask();task.filename=str(source);task.destination_path='/Game/Japan/Textures'
    task.destination_name='T_Arcade_'+name;task.automated=True;task.replace_existing=True;task.save=True
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    tex=unreal.EditorAssetLibrary.load_asset('/Game/Japan/Textures/T_Arcade_'+name)
    assert tex,source
    tex.set_editor_property('srgb',True)
    tex.set_editor_property('power_of_two_mode',unreal.TexturePowerOfTwoSetting.STRETCH_TO_POWER_OF_TWO)
    tex.set_editor_property('max_texture_size',1024)
    tex.set_editor_property('mip_gen_settings',unreal.TextureMipGenSettings.TMGS_SIMPLE_AVERAGE)
    tex.set_editor_property('address_x',unreal.TextureAddress.TA_MIRROR)
    tex.set_editor_property('address_y',unreal.TextureAddress.TA_MIRROR)
    unreal.EditorAssetLibrary.save_loaded_asset(tex)
    return tex


def material(paving=False):
    eal=unreal.EditorAssetLibrary;mel=unreal.MaterialEditingLibrary
    name='M_ArcadePaving' if paving else 'M_Arcade'
    path='/Game/Japan/Materials/'+name
    m=eal.load_asset(path) if eal.does_asset_exist(path) else unreal.AssetToolsHelpers.get_asset_tools().create_asset(name,'/Game/Japan/Materials',unreal.Material,unreal.MaterialFactoryNew())
    mel.delete_all_material_expressions(m)
    vc=mel.create_material_expression(m,unreal.MaterialExpressionVertexColor,-600,0)
    uv=mel.create_material_expression(m,unreal.MaterialExpressionTextureCoordinate,-600,200)
    tex=mel.create_material_expression(m,unreal.MaterialExpressionTextureObject,-600,400)
    tex.set_editor_property('texture',texture('paving' if paving else 'timber'))
    colour=mel.create_material_expression(m,unreal.MaterialExpressionCustom,-250,0)
    colour.set_editor_property('code','''
float3 L=lerp(C/12.92,pow((C+.055)/1.055,2.4),step(.04045,C));
float wood=step(L.g*1.45,L.r)*step(L.b*1.5,L.g)*(1-step(.35,L.r));
float grain=sin(UV.x*67+sin(UV.y*3.1)*1.6)*sin(UV.x*23+UV.y*.6);
float fade=1-saturate((length(ddx(UV))+length(ddy(UV)))*45);
float3 timber=Texture2DSample(Tex,TexSampler,UV*.65).rgb;
float variation=dot(timber,float3(.3,.59,.11));
return L*lerp(1,clamp(variation/.22,.72,1.25),wood*.75)*(1+grain*.03*wood*fade);
''')
    if paving:
        colour.set_editor_property('code','float3 L=lerp(C/12.92,pow((C+.055)/1.055,2.4),step(.04045,C)); float leaf=step(.07,max(L.r,max(L.g,L.b))-min(L.r,min(L.g,L.b))); return lerp(Texture2DSample(Tex,TexSampler,UV/2.1).rgb*.61,L,leaf);')
    colour.set_editor_property('output_type',unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    inputs=[]
    for name in ['C','UV','Tex']:
        a=unreal.CustomInput();a.set_editor_property('input_name',name);inputs.append(a)
    colour.set_editor_property('inputs',inputs)
    mel.connect_material_expressions(vc,'',colour,'C');mel.connect_material_expressions(uv,'',colour,'UV')
    mel.connect_material_expressions(tex,'',colour,'Tex')
    mel.connect_material_property(colour,'',unreal.MaterialProperty.MP_BASE_COLOR)
    glow=mel.create_material_expression(m,unreal.MaterialExpressionCustom,0,200)
    glow.set_editor_property('code','float lamp=step(.82,C.r)*step(.45,C.g)*step(C.g,.68)*step(C.b,.30); float canvas=step(.70,C.r)*step(C.r,.79)*step(.55,C.g)*step(.35,C.b); float leaf=step(.4,C.r)*step(.24,C.g)*step(C.b,.07); float shop=step(.18,C.r)*step(C.r,.22)*step(.08,C.g)*step(C.g,.11)*step(.02,C.b)*step(C.b,.04); return C*(.045+lamp*.9+canvas*.20+leaf*.38+shop*.15);')
    glow.set_editor_property('output_type',unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    a=unreal.CustomInput();a.set_editor_property('input_name','C');glow.set_editor_property('inputs',[a])
    mel.connect_material_expressions(colour,'',glow,'C');mel.connect_material_property(glow,'',unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    for prop,value in [(unreal.MaterialProperty.MP_ROUGHNESS,.87),(unreal.MaterialProperty.MP_SPECULAR,.12)]:
        n=mel.create_material_expression(m,unreal.MaterialExpressionConstant,200,400);n.set_editor_property('r',value);mel.connect_material_property(n,'',prop)
    m.set_editor_property('used_with_instanced_static_meshes',True)
    mel.recompile_material(m);eal.save_loaded_asset(m)
    return m
