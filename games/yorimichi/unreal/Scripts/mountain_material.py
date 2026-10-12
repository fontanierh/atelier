"""Opaque vertex-colour landscape, with the shared aerial perspective (atmosphere.py)."""
import unreal
import atmosphere
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'world'))
import yori  # noqa: E402

def material():
    e=unreal.EditorAssetLibrary;l=unreal.MaterialEditingLibrary
    path='/Game/Japan/Materials';name='M_NorthMountains'
    m=e.load_asset(path+'/'+name) if e.does_asset_exist(path+'/'+name) else unreal.AssetToolsHelpers.get_asset_tools().create_asset(name,path,unreal.Material,unreal.MaterialFactoryNew())
    l.delete_all_material_expressions(m)
    # Sunburst's generated rock texture is colour only; actual light and relief come from
    # the surface normals. World-space projection works on cliffs and gullies.
    task=unreal.AssetImportTask();task.filename=str(yori.ASSETS/'environment/textures/volcanic-rock.jpg')
    task.destination_path='/Game/Japan/Textures';task.destination_name='T_VolcanicRock'
    task.automated=True;task.replace_existing=True;task.save=True
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    rock=e.load_asset('/Game/Japan/Textures/T_VolcanicRock');assert rock
    rock.set_editor_property('srgb',True);rock.set_editor_property('max_texture_size',1024);e.save_loaded_asset(rock)
    vc=l.create_material_expression(m,unreal.MaterialExpressionVertexColor,-500,0)
    depth=l.create_material_expression(m,unreal.MaterialExpressionPixelDepth,-500,200)
    c=l.create_material_expression(m,unreal.MaterialExpressionCustom,-100,0)
    c.set_editor_property('code','''float3 base=lerp(C/12.92,pow((C+.055)/1.055,2.4),step(.04045,C));
float3 w=pow(abs(N),4);w/=max(w.x+w.y+w.z,.001);
float3 p=P/950.;
float3 rock=Texture2DSample(Tex,TexSampler,p.yz).rgb*w.x
          +Texture2DSample(Tex,TexSampler,p.xz).rgb*w.y
          +Texture2DSample(Tex,TexSampler,p.xy).rgb*w.z;
float3 macro=Texture2DSample(Tex,TexSampler,p.yz*.137+.23).rgb*w.x
           +Texture2DSample(Tex,TexSampler,p.xz*.137+.23).rgb*w.y
           +Texture2DSample(Tex,TexSampler,p.xy*.137+.23).rgb*w.z;
rock=lerp(rock,macro,smoothstep(12000.,90000.,D)*.45);
float grain=clamp(dot(rock,float3(.299,.587,.114))/.092,.45,1.6);
float high=smoothstep(16000.,26000.,P.z);
float3 ground=base*lerp(1.,grain,high*.85);
float strata=1.-.08*sin(P.z*.0021+sin(P.x*.0007)*2.)*(1-abs(N.z))*(1-smoothstep(35000.,100000.,D));
float3 snow=float3(.86,.85,.81)*(1.+(grain-1.)*.06);
return lerp(ground*strata,snow,saturate(A))*(1-'''+atmosphere.SHARE+');')
    c.set_editor_property('output_type',unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    args=[]
    for key in ('C','D','A','P','N','Tex'):
        a=unreal.CustomInput();a.set_editor_property('input_name',key);args.append(a)
    c.set_editor_property('inputs',args)
    l.connect_material_expressions(vc,'',c,'C');l.connect_material_expressions(depth,'',c,'D')
    l.connect_material_expressions(vc,'A',c,'A')
    p=l.create_material_expression(m,unreal.MaterialExpressionWorldPosition,-600,400)
    n=l.create_material_expression(m,unreal.MaterialExpressionVertexNormalWS,-600,500)
    tex=l.create_material_expression(m,unreal.MaterialExpressionTextureObject,-600,600);tex.set_editor_property('texture',rock)
    l.connect_material_expressions(p,'',c,'P');l.connect_material_expressions(n,'',c,'N');l.connect_material_expressions(tex,'',c,'Tex')
    l.connect_material_property(c,'',unreal.MaterialProperty.MP_BASE_COLOR)
    l.connect_material_property(atmosphere.glow(m),'',unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    for prop,value in [(unreal.MaterialProperty.MP_ROUGHNESS,1.),(unreal.MaterialProperty.MP_SPECULAR,0.)]:
        n=l.create_material_expression(m,unreal.MaterialExpressionConstant,100,300);n.set_editor_property('r',value)
        l.connect_material_property(n,'',prop)
    m.set_editor_property('used_with_instanced_static_meshes',True)
    m.set_editor_property('dithered_lod_transition',True)
    l.recompile_material(m);e.save_loaded_asset(m)
    return m


def _seamless(p):
    """HLSL adding to s the ground texture at p with no tile edges: four samples half a tile apart, each weighted
    away from its own edges."""
    taps=['Texture2DSample(Tex,TexSampler,p+float2(%s)).rgb'%o for o in ('0,0','.5,0','0,.5','.5,.5')]
    return ('p=%s;w=smoothstep(.3,.9,abs(frac(p)-.5)*2);a=lerp(%s,%s,w.x);b=lerp(%s,%s,w.x);s+=lerp(a,b,w.y);'
            %(p,*taps))


def gate_material():
    """M_NorthGate, the ground where the Mega Park meets its air station (world/regions/megapark/gate.py): the
    vertex colour (sRGB-encoded linear RGB) times the island's ground texture (T_ground) by the amount in the vertex
    alpha, the texture divided by its mean so the colour stays the vertex's; matte, with the foothills' haze, so it
    meets them without a seam. T_ground does not tile, so it is sampled without tile edges (_seamless), at its 6 m
    and again turned and at 16 m, so neither edges nor repeats show on the open meadow; the mean of the two gets back
    the contrast the blending takes out."""
    e=unreal.EditorAssetLibrary;l=unreal.MaterialEditingLibrary
    path='/Game/Japan/Materials';name='M_NorthGate'
    m=e.load_asset(path+'/'+name) if e.does_asset_exist(path+'/'+name) else unreal.AssetToolsHelpers.get_asset_tools().create_asset(name,path,unreal.Material,unreal.MaterialFactoryNew())
    l.delete_all_material_expressions(m)
    vc=l.create_material_expression(m,unreal.MaterialExpressionVertexColor,-700,0)
    depth=l.create_material_expression(m,unreal.MaterialExpressionPixelDepth,-700,400)
    uv=l.create_material_expression(m,unreal.MaterialExpressionTextureCoordinate,-700,200)
    tex=l.create_material_expression(m,unreal.MaterialExpressionTextureObject,-700,300)
    ground=e.load_asset('/Game/Japan/Textures/T_ground')
    assert ground,'T_ground'
    tex.set_editor_property('texture',ground)
    c=l.create_material_expression(m,unreal.MaterialExpressionCustom,-300,0)
    c.set_editor_property('code','float3 base=lerp(C/12.92,pow((C+.055)/1.055,2.4),step(.04045,C));'
                          'float3 M=float3(.163,.183,.036);float3 s=float3(0,0,0);float2 p,w;float3 a,b;'
                          +_seamless('UV')+_seamless('float2(UV.x*.8-UV.y*.6,UV.x*.6+UV.y*.8)*.37+.3')+
                          'float3 T=max(M+(s*.5-M)*1.8,0);float3 g=lerp(float3(1,1,1),T/M,saturate(A));'
                          'return base*g*(1-'+atmosphere.SHARE+');')
    c.set_editor_property('output_type',unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    args=[]
    for key in ('C','A','UV','Tex','D'):
        a=unreal.CustomInput();a.set_editor_property('input_name',key);args.append(a)
    c.set_editor_property('inputs',args)
    l.connect_material_expressions(vc,'',c,'C');l.connect_material_expressions(vc,'A',c,'A')
    l.connect_material_expressions(uv,'',c,'UV');l.connect_material_expressions(tex,'',c,'Tex')
    l.connect_material_expressions(depth,'',c,'D')
    l.connect_material_property(c,'',unreal.MaterialProperty.MP_BASE_COLOR)
    l.connect_material_property(atmosphere.glow(m),'',unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    for prop,value in [(unreal.MaterialProperty.MP_ROUGHNESS,1.),(unreal.MaterialProperty.MP_SPECULAR,0.)]:
        n=l.create_material_expression(m,unreal.MaterialExpressionConstant,100,300);n.set_editor_property('r',value)
        l.connect_material_property(n,'',prop)
    m.set_editor_property('used_with_instanced_static_meshes',True)     # AJapanWorld draws HD_NorthGate as an instance
    l.recompile_material(m);e.save_loaded_asset(m)
    return m
