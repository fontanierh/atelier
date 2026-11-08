"""Small opaque fountain water surface, with gently animated ripple normals."""
import unreal


def water_material(name='M_PlazaWater'):
    pond=name=='M_PondWater'
    eal=unreal.EditorAssetLibrary;mel=unreal.MaterialEditingLibrary
    path='/Game/Japan/Materials/'+name
    m=eal.load_asset(path) if eal.does_asset_exist(path) else unreal.AssetToolsHelpers.get_asset_tools().create_asset(name,'/Game/Japan/Materials',unreal.Material,unreal.MaterialFactoryNew())
    mel.delete_all_material_expressions(m)
    vc=mel.create_material_expression(m,unreal.MaterialExpressionVertexColor,-500,0)
    uv=mel.create_material_expression(m,unreal.MaterialExpressionTextureCoordinate,-500,200)
    time=mel.create_material_expression(m,unreal.MaterialExpressionTime,-500,400)
    colour=mel.create_material_expression(m,unreal.MaterialExpressionCustom,-200,0)
    colour.set_editor_property('code','return lerp(C/12.92,pow((C+.055)/1.055,2.4),step(.04045,C));')
    if pond:colour.set_editor_property('code','return float3(.006,.048,.042);')
    colour.set_editor_property('output_type',unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    a=unreal.CustomInput();a.set_editor_property('input_name','C');colour.set_editor_property('inputs',[a])
    mel.connect_material_expressions(vc,'',colour,'C');mel.connect_material_property(colour,'',unreal.MaterialProperty.MP_BASE_COLOR)
    normal=mel.create_material_expression(m,unreal.MaterialExpressionCustom,-200,200)
    normal.set_editor_property('code','float r=length(UV); float a=sin(r*20-T*2.5)*.055; return normalize(float3(sin(UV.x*11+UV.y*7+T)*.07+a,cos(UV.y*13-UV.x*4-T*1.2)*.07+a,1));')
    if pond:normal.set_editor_property('code','return normalize(float3(sin(UV.x*.8+UV.y*.6+sin(UV.y*.23+UV.x*.19)*.5+T*.45)*.075+sin(UV.y*2.1-T*.65)*.018,cos(UV.y*.9-UV.x*.5+sin(UV.x*.27)*.4-T*.35)*.075,1));')
    normal.set_editor_property('output_type',unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    inputs=[]
    for name in ['UV','T']:
        i=unreal.CustomInput();i.set_editor_property('input_name',name);inputs.append(i)
    normal.set_editor_property('inputs',inputs)
    mel.connect_material_expressions(uv,'',normal,'UV');mel.connect_material_expressions(time,'',normal,'T')
    mel.connect_material_property(normal,'',unreal.MaterialProperty.MP_NORMAL)
    for prop,value in [(unreal.MaterialProperty.MP_ROUGHNESS,.24),(unreal.MaterialProperty.MP_SPECULAR,.6),(unreal.MaterialProperty.MP_METALLIC,.10)]:
        n=mel.create_material_expression(m,unreal.MaterialExpressionConstant,200,300);n.set_editor_property('r',value);mel.connect_material_property(n,'',prop)
    m.set_editor_property('used_with_instanced_static_meshes',True)
    mel.recompile_material(m);eal.save_loaded_asset(m)
    return m


def paving_material():
    eal=unreal.EditorAssetLibrary;mel=unreal.MaterialEditingLibrary
    name='M_PlazaPaving';path='/Game/Japan/Materials/'+name
    m=eal.load_asset(path) if eal.does_asset_exist(path) else unreal.AssetToolsHelpers.get_asset_tools().create_asset(name,'/Game/Japan/Materials',unreal.Material,unreal.MaterialFactoryNew())
    mel.delete_all_material_expressions(m)
    vc=mel.create_material_expression(m,unreal.MaterialExpressionVertexColor,-500,0)
    uv=mel.create_material_expression(m,unreal.MaterialExpressionTextureCoordinate,-500,200)
    tex=mel.create_material_expression(m,unreal.MaterialExpressionTextureObject,-500,400)
    tex.set_editor_property('texture',eal.load_asset('/Game/Japan/Textures/T_Arcade_paving'))
    colour=mel.create_material_expression(m,unreal.MaterialExpressionCustom,-200,0)
    colour.set_editor_property('code','float3 L=lerp(C/12.92,pow((C+.055)/1.055,2.4),step(.04045,C)); float leaf=step(.07,max(L.r,max(L.g,L.b))-min(L.r,min(L.g,L.b))); return lerp(Texture2DSample(Tex,TexSampler,UV/3.2).rgb*float3(.61,.49,.34),L,leaf);')
    colour.set_editor_property('output_type',unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    inputs=[]
    for name in ['C','UV','Tex']:
        a=unreal.CustomInput();a.set_editor_property('input_name',name);inputs.append(a)
    colour.set_editor_property('inputs',inputs)
    for node,pin in [(vc,'C'),(uv,'UV'),(tex,'Tex')]:mel.connect_material_expressions(node,'',colour,pin)
    mel.connect_material_property(colour,'',unreal.MaterialProperty.MP_BASE_COLOR)
    normal=mel.create_material_expression(m,unreal.MaterialExpressionCustom,-200,250)
    normal.set_editor_property('code','float2 p=UV/3.2; float h=dot(Texture2DSample(Tex,TexSampler,p).rgb,float3(.3,.59,.11)); float hx=dot(Texture2DSample(Tex,TexSampler,p+float2(.002,0)).rgb,float3(.3,.59,.11)); float hy=dot(Texture2DSample(Tex,TexSampler,p+float2(0,.002)).rgb,float3(.3,.59,.11)); float leaf=step(.07,max(C.r,max(C.g,C.b))-min(C.r,min(C.g,C.b))); return normalize(float3(float2(h-hx,h-hy)*2.5*(1-leaf),1));')
    normal.set_editor_property('output_type',unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    normal_inputs=[]
    for name in ['C','UV','Tex']:
        a=unreal.CustomInput();a.set_editor_property('input_name',name);normal_inputs.append(a)
    normal.set_editor_property('inputs',normal_inputs)
    for node,pin in [(vc,'C'),(uv,'UV'),(tex,'Tex')]:mel.connect_material_expressions(node,'',normal,pin)
    mel.connect_material_property(normal,'',unreal.MaterialProperty.MP_NORMAL)
    for prop,value in [(unreal.MaterialProperty.MP_ROUGHNESS,.84),(unreal.MaterialProperty.MP_SPECULAR,.16)]:
        n=mel.create_material_expression(m,unreal.MaterialExpressionConstant,200,300);n.set_editor_property('r',value);mel.connect_material_property(n,'',prop)
    m.set_editor_property('used_with_instanced_static_meshes',True)
    mel.recompile_material(m);eal.save_loaded_asset(m)
    return m
