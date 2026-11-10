"""The japan sea masters: the open sea (M_Sea) and the Hidamari harbour water (M_HarborWater), two of the packages that
adopted/japan/materials/base-materials owned (docs/inventory/master-sources.md, section 10). Donor: games/yorimichi at the
V2 source baseline 7eec0f98dd (docs/DECISIONS.md D01): unreal/Scripts/import_southwest.py (sea_material) and
unreal/Scripts/harbor_material.py (material(water=True)).

Both read one shared look, the donor's unreal/Scripts/sea_look.py (blob sha256 ffae53cd...). Its lines 38-150 (num, f3,
the constants and the WAVES, NORMAL, LOOK and HAZE code) are copied below, byte for byte, between the SEA_LOOK markers;
the module docstring above them (lines 1-35, prose) is not. The harbour rectangle is the donor's world/coast_water.py
HARBOR_RECT (blob sha256 a7f9b6f4...). Nothing is imported from the donor.

As in the other master modules: no asset is saved or loaded here (the importer saves the one it accepts, after reading it
back against the saved original), and nothing runs at import, so the module imports without the Unreal editor.
"""
try:
    import unreal
except ImportError:   # outside the editor: the functions are defined but cannot run
    unreal = None


def _material(package):
    """The material at a package path, reused when it exists (donor: _create / E.load_asset, or AT.create_asset)."""
    folder, name = package.rsplit('/', 1)
    if unreal.EditorAssetLibrary.does_asset_exist(package):
        return unreal.EditorAssetLibrary.load_asset(package)
    return unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, folder, unreal.Material, unreal.MaterialFactoryNew())


def _custom_inputs(names):
    args = []
    for key in names:
        arg = unreal.CustomInput()
        arg.set_editor_property('input_name', key)
        args.append(arg)
    return args


# --- SEA_LOOK: sea_look.py lines 38-150, verbatim ------------------------------------------------------------------------
def num(x):
    """HLSL float literal"""
    return repr(float(x))


def f3(c):
    """HLSL float3 literal"""
    return 'float3(%s)' % ','.join(num(x) for x in c)


# The painted sky dome as the camera sees it: gen_textures.sky() `hor` (sRGB .34 .52 .76) and `zen` (.14 .32 .66),
# stored in 8 bits, in linear, times the MI_Sky tint 1.35 (setup_project.py).
HORIZON = (0.126, 0.311, 0.720)
ZENITH = (0.0235, 0.113, 0.531)

# 3-stop Beer-Lambert coastal absorption ramp: luminous jade shallows -> cerulean-teal reef -> ultramarine deep sea.
BODY = (0.004, 0.048, 0.132)
MID_TEAL = (0.011, 0.140, 0.235)
SHALLOW = (0.042, 0.305, 0.255)
SHALLOW_M = 12.0
FOAM = (1.20, 1.25, 1.30)
SLW_SCATTERING = (0.00035, 0.00240, 0.00280)
SLW_ABSORPTION = (0.00950, 0.00220, 0.00075)
SLW_PHASE_G = 0.35

# Share of the dome reflection: water's Fresnel term times REFLECT, rising to GRAZE where the view grazes the sea
# (sin of the view's elevation under ~.01: beyond ~300 m from the beach, and near the horizon from anywhere).
REFLECT = 0.20
GRAZE = 0.48
GRAZE_POWER = 100.0

# Haze with pixel depth D (cm): 1 - exp(-D / HAZE_CM), .1 at 1 km, .36 at 4 km, .9 at 20 km (the dome), toward the
# dome's horizon colour times FAR: the far sea stays a little darker than the sky above the horizon.
HAZE_CM = 900000.0
FAR = 0.74
FAR_COLOUR = tuple(round(c * FAR, 4) for c in HORIZON)

# The engine's lighting: sun glints on the waves only.
BASE = (0.0, 0.0, 0.0)
ROUGHNESS = 0.15
SPECULAR = 0.02

# Waves: nine crossing trains spread +-54 degrees about the world's wind (world.json wind_dir .30,.95 in Blender axes;
# Unreal's y is negated), wavelengths 21 m down to 1.1 m, deep-water speeds (a 21 m swell moves at 5.7 m/s), slopes
# gentle (.1 rms). Each train fades before its phase changes too fast across a pixel, so the far sea goes flat, not
# noisy.
WIND = -1.2645
K0 = 0.30
A0 = 0.065

# Surf: SURF_M vertical metres plus bounded pixel antialiasing. The bound avoids
# treating a submerged terrain edge / sky depth discontinuity as a waterline.
# None beyond SURF_FAR metres (the dome meets the sea at 20 km).
SURF_M = 0.35
SURF_AA_MAX_M = 1.0
SURF_FAR = (2500.0, 4000.0)
FLECK = 0.16

# P: world position (cm), T: time (s), D: depth (cm) -> float3(slope x, slope y, crest).
# Distance LOD fades octaves from 9 near (< 60 m) -> 7 mid -> 6 far (> 220 m).
WAVES = '''
float2 p=P.xy*.01;
float2 gx=ddx(p),gy=ddy(p);
float2 slope=0;
float crest=0;
int nWaves=D<6000.?9:(D<22000.?7:6);
[loop] for(int i=0;i<nWaves;i++)
{
    float a=%(wind)s+.95*sin(i*2.39+.5);
    float2 d=float2(cos(a),sin(a));
    float k=%(k0)s*pow(1.45,(float)i);
    float2 f=k*float2(dot(gx,d),dot(gy,d));
    float aa=exp(-.3*dot(f,f));
    float warp=1.8*sin(dot(p,float2(-d.y,d.x))*k*.41+T*.3+i*1.7);
    float ph=dot(p,d)*k+warp-T*sqrt(9.81*k)+i*2.1;
    slope+=d*(cos(ph)*%(a0)s*pow(.92,(float)i)*aa);
    if(i>2)crest+=sin(ph)*aa;
}
return float3(slope,crest/max((float)(nWaves-3),1.));
''' % dict(wind=num(WIND), k0=num(K0), a0=num(A0))

# W: WAVES -> world-space normal (the material's tangent_space_normal is off)
NORMAL = 'return normalize(float3(-W.xy,1));'

# Shared vertical quay/pier/hull contact foam probe using SceneDepthWithoutWater at world-scaled screen offsets.
QUAY_FOAM_HLSL = '''
float quayFoam=0.;
[branch] if(D<12000. && l>.35)
{
    float2 baseUV=ScreenAlignedPosition(GetScreenPosition(Parameters));
    float2 uvRad=(32./max(D,160.))*float2(.56,1.);
    float qMax=0.;
    float2 offs[4]={float2(1.,0.),float2(-1.,0.),float2(0.,1.),float2(0.,-1.)};
    [unroll] for(int qi=0;qi<4;qi++)
    {
        float zTap=MaterialExpressionSceneDepthWithoutWater(baseUV+offs[qi]*uvRad*(.75+.45*wob),1000000.);
        float nearSurf=1.-saturate((zTap-(D+20.))/38.);
        float notFg=1.-saturate(((D-zTap)-55.)/65.);
        qMax=max(qMax,nearSurf*notFg);
    }
    float lap=.72+.28*sin(T*1.8+p.x*1.3-p.y*.9);
    quayFoam=saturate(smoothstep(.15,.75,qMax)*lap);
}
'''

# W: WAVES, V: camera vector (world, toward the camera), D: pixel depth (cm),
# L: scene depth without water behind the surface (cm), P: world position (cm), T: time (s) -> emissive colour.
LOOK = '''
float2 p=P.xy*.01;
float3 N=normalize(float3(-W.xy,1));
float nv=saturate(dot(N,V));
// gusts: slow, kilometre-wide patches with a little more or less sky in the water and more or fewer flecks
float gust=.5+.25*sin(p.x*.0041+p.y*.0023+T*.021)+.25*sin(p.y*.0052-p.x*.0017-T*.016);
float graze=pow(saturate(1-V.z),%(graze_power)s);
float fres=(.02+.98*pow(1-nv,5))*lerp(%(reflect)s*(.8+.4*gust),%(graze)s,graze);
float3 R=reflect(-V,N);
float3 sky=lerp(%(horizon)s,%(zenith)s,pow(asin(saturate(R.z))/1.5708,.6));
// Convert the view-depth interval into an approximate vertical water column, with 3-stop Beer-Lambert ramp.
float l=max(0,L)*.01*max(V.z,.03);
float3 beer=lerp(%(body)s,lerp(%(mid_teal)s,%(shallow)s,exp(-l*.85)),exp(-l*.18));
float slwVis=1.-smoothstep(8000.,22000.,D);
float bodyWeight=lerp(1.,1.-exp(-l*.45),slwVis);
float3 c=lerp(beer*bodyWeight,sky,fres);
// Stylized Ghibli sun glints: smoothstepped dancing sparkles instead of sub-pixel capillary noise.
float3 sunDir=normalize(ResolvedView.DirectionalLightDirection.xyz+float3(0,0,1e-5));
float sunAlign=dot(R,sunDir);
float glint=(smoothstep(.991,.9975,sunAlign)*1.55+pow(saturate(sunAlign),96.)*.16)*(1.-smoothstep(25000.,180000.,D));
float3 sunTint=lerp(float3(1.,.92,.72),saturate(ResolvedView.DirectionalLightColor.rgb),.35);
c+=glint*sunTint;
// surf: sloped beach wash + vertical quay/pier/hull contact foam
float fp=max(abs(ddx(l)),abs(ddy(l)));
float w=%(surf_m)s+min(1.5*fp,%(surf_aa_max_m)s);
float wob=.5+.25*sin(p.x*.83+p.y*.37+T*.6)+.25*sin(p.y*1.13-p.x*.51-T*.45);
float edge=saturate(1-l/(w*(.55+.9*wob)));
float surf=edge*edge*(3-2*edge)*(.7+.3*sin(T*1.2+l/w*4))*(1-smoothstep(%(far0)s,%(far1)s,D*.01));
''' + QUAY_FOAM_HLSL + '''
float fleck=smoothstep(.58,.84,W.z)*(.6+.8*gust)*%(fleck)s;
float foamMask=saturate(max(max(surf,quayFoam),fleck));
c=lerp(c,%(foam)s,foamMask);
return lerp(c,%(far)s,1-exp(-D/%(haze)s));
''' % dict(graze_power=num(GRAZE_POWER), reflect=num(REFLECT), graze=num(GRAZE), horizon=f3(HORIZON), zenith=f3(ZENITH),
           shallow=f3(SHALLOW), mid_teal=f3(MID_TEAL), body=f3(BODY), surf_m=num(SURF_M), surf_aa_max_m=num(SURF_AA_MAX_M),
           far0=num(SURF_FAR[0]), far1=num(SURF_FAR[1]), fleck=num(FLECK), foam=f3(FOAM), far=f3(FAR_COLOUR), haze=num(HAZE_CM))

# D: pixel depth (cm) -> the haze's share, as in LOOK (the lit harbour water fades by it)
HAZE = 'return 1-exp(-D/%s);' % num(HAZE_CM)


# --- end SEA_LOOK --------------------------------------------------------------------------------------------------------

# world/coast_water.py line 6: HD_Sea's rectangle in Blender metres (x0, y0, x1, y1)
HARBOR_RECT = (300., -1600., 1800., 600.)
# harbor_material.py lines 16-18
SEA_RECT = HARBOR_RECT
EDGE = 200
FAR_FADE = (300, 900)   # metres: the lit harbour water gives way to the open sea look with distance


# --- The open sea (M_Sea) ------------------------------------------------------------------------------------------------

def sea_material(package, reads):
    """donor sea_material(), import_southwest.py 32-70, with its _node and _link (14-19): the waves, the world-space normal,
    the emissive look, the black base colour, roughness, hazed specular and full opacity, translucent and lit per pixel."""
    U = unreal
    MEL = U.MaterialEditingLibrary
    m = _material(package)
    MEL.delete_all_material_expressions(m)
    F1 = U.CustomMaterialOutputType.CMOT_FLOAT1
    F3 = U.CustomMaterialOutputType.CMOT_FLOAT3

    def _node(cls, x, y, **props):
        n = MEL.create_material_expression(m, cls, x, y)
        for k, v in props.items():
            n.set_editor_property(k, v)
        return n

    def link(a, b, key):
        assert MEL.connect_material_expressions(a, '', b, key), key

    def prop(n, p):
        assert MEL.connect_material_property(n, '', p), p

    def custom(code, inputs, x, y, kind=F3):
        n = _node(U.MaterialExpressionCustom, x, y, code=code, output_type=kind)
        n.set_editor_property('inputs', _custom_inputs([key for key, _ in inputs]))
        for key, src in inputs:
            link(src, n, key)
        return n

    po = _node(U.MaterialExpressionWorldPosition, -900, 0)
    ti = _node(U.MaterialExpressionTime, -900, 150)
    cam = _node(U.MaterialExpressionCameraVectorWS, -900, 300)
    pd = _node(U.MaterialExpressionPixelDepth, -900, 450)
    sd = _node(U.MaterialExpressionSceneDepthWithoutWater, -900, 600, fallback_depth=1000000.0)
    behind = _node(U.MaterialExpressionSubtract, -700, 550)
    link(sd, behind, 'A')
    link(pd, behind, 'B')
    waves = custom(WAVES, [('P', po), ('T', ti), ('D', pd)], -600, 0)
    prop(custom(NORMAL, [('W', waves)], -250, 0), U.MaterialProperty.MP_NORMAL)
    m.set_editor_property('tangent_space_normal', False)
    look = custom(LOOK, [('W', waves), ('V', cam), ('D', pd), ('L', behind), ('P', po), ('T', ti)], -250, 250)
    prop(look, U.MaterialProperty.MP_EMISSIVE_COLOR)
    prop(_node(U.MaterialExpressionConstant3Vector, -250, 500, constant=U.LinearColor(*BASE, 1.0)),
         U.MaterialProperty.MP_BASE_COLOR)
    prop(_node(U.MaterialExpressionConstant, -250, 600, r=ROUGHNESS), U.MaterialProperty.MP_ROUGHNESS)
    haze_node = custom(HAZE, [('D', pd)], -600, 700, F1)
    prop(custom('return %s*(1-H);' % num(SPECULAR), [('H', haze_node)], -250, 700, F1),
         U.MaterialProperty.MP_SPECULAR)
    # SingleLayerWater Opacity is BaseMaterialCoverageOverWater (WaterVisibility = 1 - Opacity):
    # 0 within 80 m enables Beer-Lambert seabed transmittance; 1 past 220 m skips 5 bilateral Gather4 reads on far sea!
    prop(custom('return saturate(max(H,smoothstep(8000.,22000.,D)));', [('H', haze_node), ('D', pd)], -250, 800, F1),
         U.MaterialProperty.MP_OPACITY)
    slw = _node(U.MaterialExpressionSingleLayerWaterMaterialOutput, -250, 950)
    scat = _node(U.MaterialExpressionConstant3Vector, -550, 900, constant=U.LinearColor(*SLW_SCATTERING, 1.0))
    abso = _node(U.MaterialExpressionConstant3Vector, -550, 1000, constant=U.LinearColor(*SLW_ABSORPTION, 1.0))
    phg = _node(U.MaterialExpressionConstant, -550, 1100, r=SLW_PHASE_G)
    assert MEL.connect_material_expressions(scat, '', slw, 'ScatteringCoefficients')
    assert MEL.connect_material_expressions(abso, '', slw, 'AbsorptionCoefficients')
    assert MEL.connect_material_expressions(phg, '', slw, 'PhaseG')
    m.set_editor_property('blend_mode', U.BlendMode.BLEND_OPAQUE)
    m.set_editor_property('shading_model', U.MaterialShadingModel.MSM_SINGLE_LAYER_WATER)
    m.set_editor_property('translucency_lighting_mode', U.TranslucencyLightingMode.TLM_VOLUMETRIC_NON_DIRECTIONAL)
    m.set_editor_property('compute_fog_per_pixel', True)
    MEL.recompile_material(m)
    return m


# --- The harbour water (M_HarborWater) -----------------------------------------------------------------------------------

HARBOR_NORMAL = '''
float2 p=P.xy*.01;
float2 gx=ddx(p),gy=ddy(p);
float footBase=max(length(gx),length(gy));
float2 slope=W.xy;
[branch] if(E>.005 && D<22000.) {
    slope=0;
    int nh=D<6000.?9:4;
    [loop] for(int i=0;i<nh;i++) {
        float a=.37+i*1.713;
        float2 d=float2(cos(a),sin(a));
        float k=1.4*pow(1.47,(float)i);
        float footprint=k*footBase;
        float amp=.11*pow(.82,(float)i)*exp(-footprint*footprint*.42);
        float warp=sin(dot(p,float2(-d.y,d.x))*k*.53+T*.4+i)*2.4;
        slope+=d*cos(dot(p,d)*k+warp+T*sqrt(9.81*k)+i*2.1)*amp;
    }
    slope=lerp(W.xy,slope,E);
}
return normalize(float3(-slope,1));
'''
HARBOR_COLOUR = '''
float2 p=P.xy*.01;
// Four incommensurate swells instead of two: the pair crossed into a visible diamond
// lattice on the open water. A very slow tide term breaks up the remaining large scale.
float swell=.5+.20*sin(p.x*.38+p.y*.61+T*.8)+.17*sin(p.x*.71-p.y*.37-T*.6)
             +.12*sin(p.x*.23-p.y*.17+T*.31)+.09*sin(p.y*1.13+p.x*.29-T*1.05);
float3 water=lerp(float3(.004,.028,.075),float3(.010,.085,.165),saturate(swell));
float tide=sin(p.x*.061-p.y*.048+T*.05)*.5+.5;
return lerp(%s,water*lerp(.92,1.08,tide),E)*(1-H);
'''
HARBOR_EMISSIVE = '''
float2 p=P.xy*.01;
float3 N=normalize(N_in);
float nv=saturate(dot(N,V));
float3 R=reflect(-V,N);
float fres=.025+.34*pow(1.-nv,4.);
float3 sky=lerp(%(horizon)s,%(zenith)s,pow(asin(saturate(R.z))/1.5708,.6));
float l=max(0,L)*.01*max(V.z,.03);
float3 beer=lerp(%(body)s,lerp(%(mid_teal)s,%(shallow)s,exp(-l*.85)),exp(-l*.18));
float slwVis=1.-smoothstep(8000.,22000.,D);
float bodyWeight=lerp(1.,1.-exp(-l*.45),slwVis);
float3 baseInner=lerp(beer*bodyWeight*.65,sky,fres);
float3 sunDir=normalize(ResolvedView.DirectionalLightDirection.xyz+float3(0,0,1e-5));
float sunAlign=dot(R,sunDir);
float glint=(smoothstep(.990,.997,sunAlign)*1.45+pow(saturate(sunAlign),84.)*.14)*(1.-smoothstep(22000.,150000.,D));
float3 sunTint=lerp(float3(1.,.92,.72),saturate(ResolvedView.DirectionalLightColor.rgb),.35);
baseInner+=glint*sunTint;
float fp=max(abs(ddx(l)),abs(ddy(l)));
float w=%(surf_m)s+min(1.5*fp,%(surf_aa_max_m)s);
float wob=.5+.25*sin(p.x*.83+p.y*.37+T*.6)+.25*sin(p.y*1.13-p.x*.51-T*.45);
float s_edge=saturate(1-l/(w*(.55+.9*wob)));
float surf=s_edge*s_edge*(3-2*s_edge)*(.7+.3*sin(T*1.2+l/w*4))*(1-smoothstep(%(far0)s,%(far1)s,D*.01));
''' + QUAY_FOAM_HLSL + '''
float fleck=smoothstep(.58,.84,W.z)*%(fleck)s*.5;
float3 harbor_foam=lerp(baseInner,%(foam)s,saturate(max(max(surf,quayFoam),fleck)));
float3 inner=lerp(harbor_foam,%(far)s,H);
return lerp(C,inner,E);
'''


def harbor_water(package, reads):
    """M_HarborWater upgraded to BLEND_Opaque + MSM_SingleLayerWater: 18 wavelet octaves near tapering to 6 far,
    3-stop Beer-Lambert depth absorption, restored sky Fresnel, stylized Ghibli sun glints, and vertical quay contact foam."""
    MEL = unreal.MaterialEditingLibrary
    m = _material(package)
    MEL.delete_all_material_expressions(m)

    def node(cls, **kw):
        e = MEL.create_material_expression(m, cls)
        for k, v in kw.items():
            e.set_editor_property(k, v)
        return e

    def link(a, out, b, key):
        assert MEL.connect_material_expressions(a, out, b, key)

    def custom(code, inputs, kind=unreal.CustomMaterialOutputType.CMOT_FLOAT3):
        n = node(unreal.MaterialExpressionCustom, code=code, output_type=kind)
        n.set_editor_property('inputs', _custom_inputs([key for key, _, _ in inputs]))
        for key, src, out in inputs:
            link(src, out, n, key)
        return n

    def prop(n, p):
        assert MEL.connect_material_property(n, '', p)

    pos = node(unreal.MaterialExpressionWorldPosition)
    time = node(unreal.MaterialExpressionTime)
    FLOAT1 = unreal.CustomMaterialOutputType.CMOT_FLOAT1
    m.set_editor_property('blend_mode', unreal.BlendMode.BLEND_OPAQUE)
    m.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_SINGLE_LAYER_WATER)
    m.set_editor_property('translucency_lighting_mode', unreal.TranslucencyLightingMode.TLM_VOLUMETRIC_NON_DIRECTIONAL)
    m.set_editor_property('compute_fog_per_pixel', True)
    # E: 0 on the rectangle's outline .. 1 once EDGE m inside; 0 again from FAR_FADE m away (harbor_material.py 70-84)
    x0, y0, x1, y1 = SEA_RECT
    depth = node(unreal.MaterialExpressionPixelDepth)
    edge = custom(f'''
float x=P.x*.01, y=-P.y*.01;     // Blender metres: Unreal's y is negated
return smoothstep(0,1,saturate(min(min(x-{num(x0)},{num(x1)}-x),min(y-({num(y0)}),{num(y1)}-y))/{num(EDGE)}))*(1-smoothstep({FAR_FADE[0]*100}.,{FAR_FADE[1]*100}.,D));
''', [('P', pos, ''), ('D', depth, '')], FLOAT1)
    haze = custom(HAZE, [('D', depth, '')], FLOAT1)
    sea = custom(WAVES, [('P', pos, ''), ('T', time, ''), ('D', depth, '')])
    normal = custom(HARBOR_NORMAL, [('P', pos, ''), ('T', time, ''), ('D', depth, ''), ('E', edge, ''), ('W', sea, '')])
    prop(normal, unreal.MaterialProperty.MP_NORMAL)
    m.set_editor_property('tangent_space_normal', False)
    color = custom(HARBOR_COLOUR % f3(BASE), [('P', pos, ''), ('T', time, ''), ('E', edge, ''), ('H', haze, '')])
    prop(color, unreal.MaterialProperty.MP_BASE_COLOR)
    prop(custom(f'return lerp({num(ROUGHNESS)},.28,E);', [('E', edge, '')], FLOAT1), unreal.MaterialProperty.MP_ROUGHNESS)
    prop(custom(f'return lerp({num(SPECULAR)},.24,E)*(1-H);', [('E', edge, ''), ('H', haze, '')], FLOAT1),
         unreal.MaterialProperty.MP_SPECULAR)
    prop(node(unreal.MaterialExpressionConstant, r=0.0), unreal.MaterialProperty.MP_METALLIC)
    prop(custom('return saturate(max(H,smoothstep(8000.,22000.,D)));', [('H', haze, ''), ('D', depth, '')], FLOAT1),
         unreal.MaterialProperty.MP_OPACITY)
    slw = node(unreal.MaterialExpressionSingleLayerWaterMaterialOutput)
    scat = node(unreal.MaterialExpressionConstant3Vector, constant=unreal.LinearColor(*SLW_SCATTERING, 1.0))
    abso = node(unreal.MaterialExpressionConstant3Vector, constant=unreal.LinearColor(*SLW_ABSORPTION, 1.0))
    phg = node(unreal.MaterialExpressionConstant, r=SLW_PHASE_G)
    link(scat, '', slw, 'ScatteringCoefficients')
    link(abso, '', slw, 'AbsorptionCoefficients')
    link(phg, '', slw, 'PhaseG')
    behind = node(unreal.MaterialExpressionSubtract)
    link(node(unreal.MaterialExpressionSceneDepthWithoutWater, fallback_depth=1000000.0), '', behind, 'A')
    link(depth, '', behind, 'B')
    cam = node(unreal.MaterialExpressionCameraVectorWS)
    look = custom(LOOK, [('W', sea, ''), ('V', cam, ''), ('D', depth, ''), ('L', behind, ''), ('P', pos, ''), ('T', time, '')])
    emissive = custom(HARBOR_EMISSIVE % dict(
        horizon=f3(HORIZON), zenith=f3(ZENITH), body=f3(BODY), mid_teal=f3(MID_TEAL),
        surf_m=num(SURF_M), surf_aa_max_m=num(SURF_AA_MAX_M), far0=num(SURF_FAR[0]), far1=num(SURF_FAR[1]),
        fleck=num(FLECK), shallow=f3(SHALLOW), foam=f3(FOAM), far=f3(FAR_COLOUR)),
        [('C', look, ''), ('E', edge, ''), ('H', haze, ''), ('W', sea, ''), ('N_in', normal, ''), ('V', cam, ''),
         ('D', depth, ''), ('L', behind, ''), ('P', pos, ''), ('T', time, '')])
    prop(emissive, unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    m.set_editor_property('used_with_instanced_static_meshes', True)
    MEL.layout_material_expressions(m)
    MEL.recompile_material(m)
    return m
