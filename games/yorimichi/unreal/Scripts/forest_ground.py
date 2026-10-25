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


def material(*, rock=False, south_join_m=None):
    """@cc [owner:fontanierh,label:correctness] explicit-forest-join-input
    A provided south_join_m MUST determine the original graph without reading
    ambient generated metadata. The no-argument owner MUST retain its existing
    generated metadata read and graph behavior.
    """
    if rock:return rock_material()
    E=U.EditorAssetLibrary;M=U.MaterialEditingLibrary;AT=U.AssetToolsHelpers.get_asset_tools()
    name='M_ForestGround'
    path='/Game/Japan/Materials/'+name
    m=E.load_asset(path) if E.does_asset_exist(path) else AT.create_asset(name,'/Game/Japan/Materials',U.Material,U.MaterialFactoryNew())
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
    if south_join_m is None:
        south_join_m=json.loads((yori.OUT/'hidamari/north_snow.json').read_text())['south_join_m']
    join=south_join_m*100
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


def rock_material(*, texture=None):
    """@cc [owner:fontanierh,label:correctness] explicit-finished-coast-texture
    A provided texture MUST be consumed without importing, mutating or saving it.
    Only the owned rock material may be saved. The no-argument authoring owner
    retains its original texture preparation and graph construction.
    """
    import hashlib
    import coast_rock_look as look
    from material_assets import create,save_material
    E=U.EditorAssetLibrary;M=U.MaterialEditingLibrary
    if texture is None:
        source=yori.ASSETS/look.TEXTURE
        assert hashlib.sha256(source.read_bytes()).hexdigest()==look.TEXTURE_SHA256
        task=U.AssetImportTask();task.filename=str(source)
        task.destination_path='/Game/Japan/Textures';task.destination_name='T_CoastRock'
        task.automated=True;task.replace_existing=True;task.save=True
        U.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        texture=E.load_asset('/Game/Japan/Textures/T_CoastRock');assert texture
        texture.set_editor_property('srgb',True)
        texture.set_editor_property('max_texture_size',1024)
        texture.set_editor_property('mip_gen_settings',U.TextureMipGenSettings.TMGS_SIMPLE_AVERAGE)
        E.save_loaded_asset(texture)
    m=create('M_CoastRock',U.Material,U.MaterialFactoryNew())

    def node(cls,**props):
        n=M.create_material_expression(m,cls)
        for key,value in props.items():n.set_editor_property(key,value)
        return n

    def custom(code,connections):
        n=node(U.MaterialExpressionCustom,output_type=U.CustomMaterialOutputType.CMOT_FLOAT3,code=code)
        inputs=[]
        for key,_,_ in connections:
            arg=U.CustomInput();arg.set_editor_property('input_name',key);inputs.append(arg)
        n.set_editor_property('inputs',inputs)
        for key,source,output in connections:assert M.connect_material_expressions(source,output,n,key)
        return n

    p=node(U.MaterialExpressionWorldPosition)
    vc=node(U.MaterialExpressionVertexColor)
    vertex_normal=node(U.MaterialExpressionVertexNormalWS)
    normal=custom('float3 n=cross(ddx(P),ddy(P)); float l2=dot(n,n); '
                  'n=l2>1.e-16?n*rsqrt(max(l2,1.e-16)):N; '
                  'return dot(n,N)<0.?-n:n;',[('P',p,''),('N',vertex_normal,'')])
    base=custom(look.code(),[('P',p,''),('N',normal,''),('C',vc,''),
                            ('Rock',node(U.MaterialExpressionTextureObject,texture=texture),'')])
    shaded,emission=atmosphere.apply(m,base,node(U.MaterialExpressionConstant,r=0.))
    for prop,n in [(U.MaterialProperty.MP_BASE_COLOR,shaded),(U.MaterialProperty.MP_EMISSIVE_COLOR,emission),
                   (U.MaterialProperty.MP_NORMAL,normal),
                   (U.MaterialProperty.MP_ROUGHNESS,node(U.MaterialExpressionConstant,r=1.)),
                   (U.MaterialProperty.MP_SPECULAR,node(U.MaterialExpressionConstant,r=0.))]:
        assert M.connect_material_property(n,'',prop)
    m.set_editor_property('tangent_space_normal',False)
    m.set_editor_property('used_with_instanced_static_meshes',True)
    save_material(m)
    return m


def coast_instance(parent=None):
    from material_assets import instance
    mi=instance('MI_Coast',parent or material())
    U.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(mi,'NearGround',1.)
    U.MaterialEditingLibrary.update_material_instance(mi)
    U.EditorAssetLibrary.save_loaded_asset(mi)
    return mi


def coast_rock_instance():
    """@cc [owner:fontanierh,label:correctness] coastal-face-normal-isolation
    CoastRock MUST have its own world-space geometric normal, oriented against
    the vertex normal with a finite degenerate-derivative fallback. It MUST NOT
    read PixelNormalWS or change the shared ground material's normal path.
    """
    from material_assets import instance
    mi=instance('MI_CoastRock',material(rock=True))
    U.MaterialEditingLibrary.update_material_instance(mi)
    U.EditorAssetLibrary.save_loaded_asset(mi)
    return mi
