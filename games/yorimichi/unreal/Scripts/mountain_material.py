"""Opaque vertex-colour landscape, with the shared aerial perspective (atmosphere.py)."""
import unreal
import atmosphere
import ground_grain
import json
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
    rock.set_editor_property('srgb',True);rock.set_editor_property('max_texture_size',2048);e.save_loaded_asset(rock)
    snow_meta=json.loads((yori.OUT/'hidamari/north_snow.json').read_text())
    assert snow_meta['linear'] and snow_meta['size']==[1024,1024]
    step=snow_meta['step_m']
    task=unreal.AssetImportTask();task.filename=str(yori.OUT/'hidamari/north_snow.png')
    task.destination_path='/Game/Japan/Textures';task.destination_name='T_NorthSnowMask'
    task.automated=True;task.replace_existing=True;task.save=True
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    snow_texture=e.load_asset('/Game/Japan/Textures/T_NorthSnowMask');assert snow_texture
    snow_texture.set_editor_property('srgb',False)
    snow_texture.set_editor_property('compression_settings',unreal.TextureCompressionSettings.TC_GRAYSCALE)
    snow_texture.set_editor_property('mip_gen_settings',unreal.TextureMipGenSettings.TMGS_SIMPLE_AVERAGE)
    snow_texture.set_editor_property('address_x',unreal.TextureAddress.TA_CLAMP)
    snow_texture.set_editor_property('address_y',unreal.TextureAddress.TA_CLAMP)
    snow_texture.set_editor_property('never_stream',True);e.save_loaded_asset(snow_texture)
    x0,y0,_,_=snow_meta['bounds']
    snow_code=(f'float2 snowUV=(float2(P.x,-P.y)/100.-float2({x0},{y0}))/{step};'
               'snowUV=(snowUV+.5)/1024.;'
               'float mip=clamp(log2(max(1e-6,max(max(abs(ddx(snowUV)).x,abs(ddy(snowUV)).x),'
               'max(abs(ddx(snowUV)).y,abs(ddy(snowUV)).y)))*1024.),0.,3.);'
               'float snowAlpha=Texture2DSampleLevel(Snow,SnowSampler,snowUV,mip).r;')
    snow_code+=('float3 snowLum=float3(.299,.587,.114);'
                'float edgeNoise=clamp(dot(Texture2DSampleLevel(Tex,TexSampler,P.xy/2600.+.61,6.5).rgb,snowLum)/.092-1.,-1.,1.);'
                'float edge=lerp(5.,1.5,smoothstep(50000.,200000.,D));'
                'float snowMask=saturate((snowAlpha-.5+edgeNoise*.15)*edge+.5);'
                # A rock (Caps 1, rock_material) wears snow on its upward faces wherever snow lies round it, not the
                # ground's mask cut across it: white blocks on snow and bare grey ones beside it read as no rock at all.
                'float around=Texture2DSampleLevel(Snow,SnowSampler,snowUV,4.).r;'
                'snowMask=lerp(snowMask,saturate((N.z-.88)/.07)*saturate((around-.3)*2.5)*saturate(edgeNoise*2.+1.2),Caps);')
    # The volcano's exposed-rock band and the join to Belmonte's palette, in centimetres (hidamari/mountains.py).
    (vx,vy),(r0,r1),(p0,p1),join=snow_meta['volcano_m'],snow_meta['rock_radius_m'],snow_meta['rock_prominence_m'],snow_meta['south_join_m']
    rock_band=(f'float join=smoothstep({(join-420)*100:.0f}.,{join*100:.0f}.,-P.y);'
               'float prominence=P.z-(4700.+max(-P.y-50000.,0)*.020);'
               f'float radius=length(P.xy-float2({vx*100:.0f}.,{-vy*100:.0f}.));'
               f'float high=smoothstep({p0*100:.0f}.,{p1*100:.0f}.,prominence)*(1-smoothstep({r0*100:.0f}.,{r1*100:.0f}.,radius))*(1-join);')
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
float3 q=P/2310.+.37;
float3 mid=Texture2DSample(Tex,TexSampler,q.yz).rgb*w.x
         +Texture2DSample(Tex,TexSampler,q.xz).rgb*w.y
         +Texture2DSample(Tex,TexSampler,q.xy).rgb*w.z;
float3 lum=float3(.299,.587,.114);
float g1=max(dot(rock,lum)/.092,.05),g2=max(dot(mid,lum)/.092,.05),g3=max(dot(macro,lum)/.092,.05);
float3 fineP=P/240.;
float3 fine=Texture2DSample(Tex,TexSampler,fineP.yz).rgb*w.x
           +Texture2DSample(Tex,TexSampler,fineP.xz).rgb*w.y
           +Texture2DSample(Tex,TexSampler,fineP.xy).rgb*w.z;
float gFine=clamp(dot(fine,lum)/.092,.35,1.8);
float distanceBlend=smoothstep(12000.,90000.,D);
float grain=clamp(lerp(pow(g1,.55)*pow(g2,.45),pow(g2,.4)*pow(g3,.6),distanceBlend),.45,1.6);
'''+rock_band+'''
'''+ground_grain.code('Ground','GroundSampler','P')+'''
float3 ground=base*lerp(groundDetail,float3(grain,grain,grain),high*.85);
ground*=lerp(1.,pow(gFine,1.6),(1-smoothstep(3000.,15000.,D))*high*.45);
float3 an=abs(N);
float2 fp=an.z>max(an.x,an.y)?P.xy/2200.:(an.x>an.y?P.yz:P.xz)/float2(1500.,6000.);
float2 fc=floor(fp);float best=9.;float2 id=fc;
for(int j=-1;j<=1;j++)for(int i=-1;i<=1;i++){
  float2 cell=fc+float2(i,j);
  float2 o=frac(sin(float2(dot(cell,float2(127.1,311.7)),dot(cell,float2(269.5,183.3))))*43758.5453);
  float2 d=cell+o-fp;float dd=dot(d,d);
  if(dd<best){best=dd;id=cell;}
}
float3 h=frac(sin(float3(dot(id,float2(12.9898,78.233)),dot(id,float2(39.346,11.135)),dot(id,float2(73.156,52.235))))*43758.5453)-.5;
float2 fp2=fp*3.1+.37;float2 fc2=floor(fp2);float best2=9.;float2 id2=fc2;
for(int j2=-1;j2<=1;j2++)for(int i2=-1;i2<=1;i2++){
  float2 cell=fc2+float2(i2,j2);
  float2 o=frac(sin(float2(dot(cell,float2(127.1,311.7)),dot(cell,float2(269.5,183.3))))*43758.5453);
  float2 d=cell+o-fp2;float dd=dot(d,d);
  if(dd<best2){best2=dd;id2=cell;}
}
float3 h2=frac(sin(float3(dot(id2,float2(12.9898,78.233)),dot(id2,float2(39.346,11.135)),dot(id2,float2(73.156,52.235))))*43758.5453)-.5;
float3 sunDir=normalize(Sun.xyz);
float litFacet=saturate(dot(normalize(N+h*float3(1.1,1.1,.55)+h2*float3(.8,.8,.4)),sunDir)),litSmooth=saturate(dot(N,sunDir));
float3 facet=(.4+1.*litFacet)/(.4+1.*litSmooth)*lerp(float3(.95,.97,1.03),float3(1.06,1.02,.94),saturate(litFacet*1.4-.2));
ground*=lerp(float3(1.,1.,1.),facet,high*(1-smoothstep(60000.,250000.,D)));
float strata=1.-.08*sin(P.z*.0021+sin(P.x*.0007)*2.)*(1-abs(N.z))*(1-smoothstep(35000.,100000.,D))*(1-join);
float3 snow=float3(.80,.83,.89)*lerp(.9,1.05,saturate((g3-.6)/.9))*lerp(1.,.92,saturate(1-N.z));
'''+snow_code+'''
return lerp(ground*strata,snow,snowMask)*(1-'''+atmosphere.SHARE+');')
    c.set_editor_property('output_type',unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    args=[]
    for key in ('C','D','A','P','N','Tex','Ground','Snow','Sun','Caps'):
        a=unreal.CustomInput();a.set_editor_property('input_name',key);args.append(a)
    c.set_editor_property('inputs',args)
    l.connect_material_expressions(vc,'',c,'C');l.connect_material_expressions(depth,'',c,'D')
    l.connect_material_expressions(vc,'A',c,'A')
    p=l.create_material_expression(m,unreal.MaterialExpressionWorldPosition,-600,400)
    n=l.create_material_expression(m,unreal.MaterialExpressionVertexNormalWS,-600,500)
    tex=l.create_material_expression(m,unreal.MaterialExpressionTextureObject,-600,600);tex.set_editor_property('texture',rock)
    detail=e.load_asset('/Game/Japan/Textures/T_ground_detail');assert detail
    ground=l.create_material_expression(m,unreal.MaterialExpressionTextureObject,-600,700);ground.set_editor_property('texture',detail)
    snow_object=l.create_material_expression(m,unreal.MaterialExpressionTextureObject,-600,800)
    snow_object.set_editor_property('texture',snow_texture)
    snow_object.set_editor_property('sampler_type',unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_GRAYSCALE)
    l.connect_material_expressions(p,'',c,'P');l.connect_material_expressions(n,'',c,'N');l.connect_material_expressions(tex,'',c,'Tex')
    l.connect_material_expressions(ground,'',c,'Ground')
    l.connect_material_expressions(snow_object,'',c,'Snow')
    l.connect_material_property(c,'',unreal.MaterialProperty.MP_BASE_COLOR)
    # Exposed volcanic rock has a neutral sky-bounce floor. It is zero at the
    # woodland/collar joins, and snow retains its existing physical lighting.
    ambient=l.create_material_expression(m,unreal.MaterialExpressionCustom,200,150)
    ambient.set_editor_property('output_type',unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    ambient.set_editor_property('code',snow_code+rock_band+'''
float bounce=dot(Base,float3(.299,.587,.114))*.25*high*(1-snowMask)*(1-saturate(dot(N,normalize(Sun.xyz))))*Sun.w;
return float3(bounce,bounce,bounce);''')
    inputs=[]
    for key in ('Base','P','N','D','Snow','Tex','Sun','Caps'):
        value=unreal.CustomInput();value.set_editor_property('input_name',key);inputs.append(value)
    ambient.set_editor_property('inputs',inputs)
    l.connect_material_expressions(c,'',ambient,'Base');l.connect_material_expressions(p,'',ambient,'P')
    l.connect_material_expressions(snow_object,'',ambient,'Snow')
    l.connect_material_expressions(n,'',ambient,'N');l.connect_material_expressions(depth,'',ambient,'D')
    l.connect_material_expressions(tex,'',ambient,'Tex')
    wind=e.load_asset('/Game/Japan/Materials/MPC_Wind');assert wind
    sun=l.create_material_expression(m,unreal.MaterialExpressionCollectionParameter,-600,900)
    sun.set_editor_property('collection',wind);sun.set_editor_property('parameter_name','SunDirection')
    l.connect_material_expressions(sun,'',ambient,'Sun');l.connect_material_expressions(sun,'',c,'Sun')
    caps=l.create_material_expression(m,unreal.MaterialExpressionScalarParameter,-600,1000)
    caps.set_editor_property('parameter_name','Caps');caps.set_editor_property('default_value',0.)
    l.connect_material_expressions(caps,'',ambient,'Caps');l.connect_material_expressions(caps,'',c,'Caps')
    emission=l.create_material_expression(m,unreal.MaterialExpressionAdd,400,150)
    l.connect_material_expressions(atmosphere.glow(m),'',emission,'A')
    l.connect_material_expressions(ambient,'',emission,'B')
    l.connect_material_property(emission,'',unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    for prop,value in [(unreal.MaterialProperty.MP_ROUGHNESS,1.),(unreal.MaterialProperty.MP_SPECULAR,0.)]:
        n=l.create_material_expression(m,unreal.MaterialExpressionConstant,100,300);n.set_editor_property('r',value)
        l.connect_material_property(n,'',prop)
    m.set_editor_property('used_with_instanced_static_meshes',True)
    m.set_editor_property('dithered_lod_transition',True)
    l.recompile_material(m);e.save_loaded_asset(m)
    return m


def rock_material(parent):
    """The volcano's loose rocks (HD_NorthRock*): the mountain material with snow caps."""
    e=unreal.EditorAssetLibrary;path='/Game/Japan/Materials/MI_NorthRockCaps'
    mi=e.load_asset(path) if e.does_asset_exist(path) else unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        'MI_NorthRockCaps','/Game/Japan/Materials',unreal.MaterialInstanceConstant,unreal.MaterialInstanceConstantFactoryNew())
    l=unreal.MaterialEditingLibrary
    l.set_material_instance_parent(mi,parent)
    # The setter's return value is not a reliable success flag; read the value back instead.
    l.set_material_instance_scalar_parameter_value(mi,'Caps',1.)
    l.update_material_instance(mi)
    assert l.get_material_instance_scalar_parameter_value(mi,'Caps')==1.,'MI_NorthRockCaps: Caps not set'
    e.save_loaded_asset(mi)
    return mi


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
