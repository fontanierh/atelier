"""Harbor-only stone/cedar/paint and animated reflective water materials.

Reuses the arcade's generated paving and cedar albedo originals. All shading
is evaluated in the game; no capture colour correction or painted reflections.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
from pathlib import Path
import unreal
import sea_look
import coast_water

EAL=unreal.EditorAssetLibrary
MEL=unreal.MaterialEditingLibrary

# HD_Sea's rectangle in Blender metres (x0, y0, x1, y1: hidamari/build.py sea_mesh) and the width of its calm border (m)
SEA_RECT=coast_water.HARBOR_RECT
EDGE=200
FAR_FADE=(300,900)   # metres: the lit harbour water gives way to the open sea look with distance


def texture(name):
    source=yori.REGIONS/'hidamari/textures'/f'{name}.png'
    task=unreal.AssetImportTask();task.filename=str(source)
    task.destination_path='/Game/Japan/Textures';task.destination_name='T_Harbor_'+name
    task.automated=True;task.replace_existing=True;task.save=True
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    tex=EAL.load_asset('/Game/Japan/Textures/T_Harbor_'+name)
    assert tex,source
    tex.set_editor_property('srgb',True)
    tex.set_editor_property('power_of_two_mode',unreal.TexturePowerOfTwoSetting.STRETCH_TO_POWER_OF_TWO)
    tex.set_editor_property('max_texture_size',1024)
    tex.set_editor_property('mip_gen_settings',unreal.TextureMipGenSettings.TMGS_SIMPLE_AVERAGE)
    tex.set_editor_property('address_x',unreal.TextureAddress.TA_MIRROR)
    tex.set_editor_property('address_y',unreal.TextureAddress.TA_MIRROR)
    EAL.save_loaded_asset(tex)
    return tex


def material(water=False):
    name='M_HarborWater' if water else 'M_Harbor'
    path='/Game/Japan/Materials/'+name
    m=EAL.load_asset(path) if EAL.does_asset_exist(path) else unreal.AssetToolsHelpers.get_asset_tools().create_asset(name,'/Game/Japan/Materials',unreal.Material,unreal.MaterialFactoryNew())
    MEL.delete_all_material_expressions(m)
    def node(cls,**kw):
        e=MEL.create_material_expression(m,cls)
        for k,v in kw.items():e.set_editor_property(k,v)
        return e
    def link(a,out,b,key):assert MEL.connect_material_expressions(a,out,b,key)
    def custom(code,inputs,kind=unreal.CustomMaterialOutputType.CMOT_FLOAT3):
        n=node(unreal.MaterialExpressionCustom,code=code,output_type=kind)
        args=[]
        for key,src,out in inputs:
            a=unreal.CustomInput();a.set_editor_property('input_name',key);args.append(a)
        n.set_editor_property('inputs',args)
        for key,src,out in inputs:link(src,out,n,key)
        return n
    def prop(n,p):assert MEL.connect_material_property(n,'',p)
    vc=node(unreal.MaterialExpressionVertexColor)
    uv=node(unreal.MaterialExpressionTextureCoordinate)
    pos=node(unreal.MaterialExpressionWorldPosition)
    time=node(unreal.MaterialExpressionTime)
    if water:
        FLOAT1=unreal.CustomMaterialOutputType.CMOT_FLOAT1
        S=sea_look
        # Read the same underlying depth as the open sea. A constant "deep"
        # depth here would leave a rectangular blue seam across turquoise bays.
        m.set_editor_property('blend_mode',unreal.BlendMode.BLEND_TRANSLUCENT)
        # Low-tessellation sea planes must evaluate the same fog at every pixel.
        m.set_editor_property('compute_fog_per_pixel',True)
        m.set_editor_property('translucency_lighting_mode',unreal.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
        prop(node(unreal.MaterialExpressionConstant,r=1.),unreal.MaterialProperty.MP_OPACITY)
        # E: 0 on the rectangle's outline .. 1 once EDGE m inside. On the outline this is the open sea (M_Sea, sea_look.py):
        # its waves, its authored emissive colour, black base colour and its roughness and specular. Inward the
        # harbour's own lit water takes over, so the rectangle does not show on the sea around it.
        # Seen from afar (FAR_FADE m) the whole rectangle becomes the open sea: from the hills and the air its lit
        # water, which mirrors the sky differently, showed as a darker rectangle on the sea.
        x0,y0,x1,y1=SEA_RECT
        depth=node(unreal.MaterialExpressionPixelDepth)
        edge=custom(f'''
float x=P.x*.01, y=-P.y*.01;     // Blender metres: Unreal's y is negated
return smoothstep(0,1,saturate(min(min(x-{S.num(x0)},{S.num(x1)}-x),min(y-({S.num(y0)}),{S.num(y1)}-y))/{S.num(EDGE)}))*(1-smoothstep({FAR_FADE[0]*100}.,{FAR_FADE[1]*100}.,D));
''',[('P',pos,''),('D',depth,'')],FLOAT1)
        # H: with distance the lit water gives way to the same haze as the open sea's.
        haze=custom(S.HAZE,[('D',depth,'')],FLOAT1)
        sea=custom(S.WAVES,[('P',pos,''),('T',time,'')])
        # Analytic slope of crossing gravity/capillary waves; world-space normal
        # avoids dependence on huge sea-plane UVs and animates without textures.
        normal=custom('''
float2 p=P.xy*.01;
float2 slope=0;
for(int i=0;i<9;i++) {
    float a=.37+i*1.713;
    float2 d=float2(cos(a),sin(a));
    float k=1.4*pow(1.47,(float)i);
    float footprint=k*max(length(ddx(p)),length(ddy(p)));
    float amp=.14*pow(.84,(float)i)*exp(-footprint*footprint*.35);
    float warp=sin(dot(p,float2(-d.y,d.x))*k*.53+T*.4+i)*2.7;
    slope+=d*cos(dot(p,d)*k+warp+T*sqrt(9.81*k)+i*2.1)*amp;
}
return normalize(float3(-lerp(W.xy,slope,E),1));
''',[('P',pos,''),('T',time,''),('E',edge,''),('W',sea,'')])
        prop(normal,unreal.MaterialProperty.MP_NORMAL)
        m.set_editor_property('tangent_space_normal',False)
        color=custom('''
float2 p=P.xy*.01;
// Four incommensurate swells instead of two: the pair crossed into a visible diamond
// lattice on the open water. A very slow tide term breaks up the remaining large scale.
float swell=.5+.20*sin(p.x*.38+p.y*.61+T*.8)+.17*sin(p.x*.71-p.y*.37-T*.6)
             +.12*sin(p.x*.23-p.y*.17+T*.31)+.09*sin(p.y*1.13+p.x*.29-T*1.05);
float3 water=lerp(float3(.002,.012,.040),float3(.006,.048,.115),saturate(swell));
float tide=sin(p.x*.061-p.y*.048+T*.05)*.5+.5;
return lerp(%s,water*lerp(.90,1.10,tide),E)*(1-H);
''' % S.f3(S.BASE),[('P',pos,''),('T',time,''),('E',edge,''),('H',haze,'')])
        prop(color,unreal.MaterialProperty.MP_BASE_COLOR)
        prop(custom(f'return lerp({S.num(S.ROUGHNESS)},.20,E);',[('E',edge,'')],FLOAT1),unreal.MaterialProperty.MP_ROUGHNESS)
        prop(custom(f'return lerp({S.num(S.SPECULAR)},.5,E)*(1-H);',[('E',edge,''),('H',haze,'')],FLOAT1),unreal.MaterialProperty.MP_SPECULAR)
        prop(node(unreal.MaterialExpressionConstant,r=0.0),unreal.MaterialProperty.MP_METALLIC)
        # Identical depth, surf and shallows on the shared open-water boundary;
        # inward the harbor's calm lit surface keeps the waterline surf, hull/pile foam and shallow tint.
        behind=node(unreal.MaterialExpressionSubtract)
        link(node(unreal.MaterialExpressionSceneDepth),'',behind,'A')
        link(depth,'',behind,'B')
        cam=node(unreal.MaterialExpressionCameraVectorWS)
        look=custom(S.LOOK,[('W',sea,''),('V',cam,''),('D',depth,''),
                            ('L',behind,''),('P',pos,''),('T',time,'')])
        emissive=custom('''
float2 p=P.xy*.01;
float l=max(0,L)*.01*max(V.z,.03);
float fp=max(abs(ddx(l)),abs(ddy(l)));
float w=%(surf_m)s+min(1.5*fp,%(surf_aa_max_m)s);
float wob=.5+.25*sin(p.x*.83+p.y*.37+T*.6)+.25*sin(p.y*1.13-p.x*.51-T*.45);
float s_edge=saturate(1-l/(w*(.55+.9*wob)));
float surf=s_edge*s_edge*(3-2*s_edge)*(.7+.3*sin(T*1.2+l/w*4))*(1-smoothstep(%(far0)s,%(far1)s,D*.01));
float fleck=smoothstep(.58,.84,W.z)*%(fleck)s*.5;
float3 harbor_foam=lerp(%(shallow)s*(1-saturate(l/%(shallow_m)s))*.25,%(foam)s,saturate(max(surf,fleck)));
float3 inner=lerp(harbor_foam,%(far)s,H);
return lerp(C,inner,E);
''' % dict(surf_m=S.num(S.SURF_M),surf_aa_max_m=S.num(S.SURF_AA_MAX_M),far0=S.num(S.SURF_FAR[0]),
           far1=S.num(S.SURF_FAR[1]),fleck=S.num(S.FLECK),shallow=S.f3(S.SHALLOW),
           shallow_m=S.num(S.SHALLOW_M),foam=S.f3(S.FOAM),far=S.f3(S.FAR_COLOUR)),
        [('C',look,''),('E',edge,''),('H',haze,''),('W',sea,''),('V',cam,''),('D',depth,''),('L',behind,''),('P',pos,''),('T',time,'')])
        prop(emissive,unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    else:
        paving=node(unreal.MaterialExpressionTextureObject,texture=texture('paving'))
        timber=node(unreal.MaterialExpressionTextureObject,texture=texture('timber'))
        color=custom('''
float3 L=lerp(C.rgb/12.92,pow((C.rgb+.055)/1.055,2.4),step(.04045,C.rgb));
float wood=1-step(.07,abs(A-.25));
float stone=1-step(.07,abs(A-.5));
float masonry=1-step(.07,abs(A-.75));
float3 slabs=Texture2DSample(Stone,StoneSampler,UV/2.4).rgb;
float3 grain=Texture2DSample(Wood,WoodSampler,UV*.7).rgb;
L*=lerp(1,clamp(dot(grain,float3(.3,.59,.11))/.22,.72,1.3),wood*.8);
L=lerp(L,slabs*float3(.43,.35,.22),stone);
L*=lerp(1,clamp(dot(slabs,float3(.3,.59,.11))/.30,.8,1.2),masonry*.65);
return L;
''',[('C',vc,''),('A',vc,'A'),('UV',uv,''),('Stone',paving,''),('Wood',timber,'')])
        prop(color,unreal.MaterialProperty.MP_BASE_COLOR)
        normal=custom('''
if(abs(A-.5)>.07)return float3(0,0,1);
float2 q=UV/2.4;
float2 e=float2(.0015,0);
float dx=dot(Texture2DSample(Stone,StoneSampler,q+e.xy).rgb-Texture2DSample(Stone,StoneSampler,q-e.xy).rgb,float3(.3,.59,.11));
float dy=dot(Texture2DSample(Stone,StoneSampler,q+e.yx).rgb-Texture2DSample(Stone,StoneSampler,q-e.yx).rgb,float3(.3,.59,.11));
return normalize(float3(-dx*9,-dy*9,1));
''',[('A',vc,'A'),('UV',uv,''),('Stone',paving,'')])
        prop(normal,unreal.MaterialProperty.MP_NORMAL)
        rough=custom('return lerp(.83,.19,step(.95,A));',[('A',vc,'A')],unreal.CustomMaterialOutputType.CMOT_FLOAT1)
        prop(rough,unreal.MaterialProperty.MP_ROUGHNESS)
        prop(node(unreal.MaterialExpressionConstant,r=.35),unreal.MaterialProperty.MP_SPECULAR)
        # Restrained fill keeps readable contact shadows on this sunlit kit.
        fill=node(unreal.MaterialExpressionMultiply,const_b=.025);link(color,'',fill,'A')
        prop(fill,unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    m.set_editor_property('used_with_instanced_static_meshes',True)
    MEL.layout_material_expressions(m);MEL.recompile_material(m);EAL.save_loaded_asset(m)
    return m
