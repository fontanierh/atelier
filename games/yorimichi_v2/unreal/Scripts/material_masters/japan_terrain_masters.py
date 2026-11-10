"""The japan terrain masters: the forest crown impostor (M_ForestImpostor), the forest floor (M_ForestGround), the coastal
rock (M_CoastRock) and the Mega Park gate ground (M_NorthGate), four of the packages that adopted/japan/materials/
base-materials owned (docs/inventory/master-sources.md, section 10). Donor: games/yorimichi/unreal/Scripts at the V2
source baseline 7eec0f98dd (docs/DECISIONS.md D01): forest_impostor_material.py, forest_ground.py and mountain_material.py.

All four take the shared aerial perspective of the donor's atmosphere.py (blob sha256 b59478df...), whose constants come
from sea_look.py (HAZE_CM, FAR_COLOUR); the separately pinned master_haze helper owns that graph. forest_ground uses
ground_grain.py (5c06a2e0...) and coast_rock_look.py (its code(), without the donor's contract docstring). Generated
values the donor read from its build output (north_snow.json south_join_m) arrive as recipe arguments.

As in the other master modules: no asset is saved, loaded or imported here (every texture arrives through reads[path],
and the importer saves the one it accepts), and nothing runs at import, so the module imports without the Unreal editor.
"""
from . import master_haze as haze

try:
    import unreal
except ImportError:   # outside the editor: the functions are defined but cannot run
    unreal = None


def _material(package):
    """The material at a package path, reused when it exists (donor: E.load_asset, or AT.create_asset when it does not)."""
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


# --- atmosphere.py (lines 17-62): the haze every lit land material shares, from the pinned master_haze helper

SHARE = haze.SHARE   # the haze share of pixel depth D, which the gate and mountain HLSL also take out


# --- The forest crown impostor (M_ForestImpostor) -----------------------------------------------------------------------

IMPOSTOR_NORMAL = ('float3 n=Texture2DSample(Tex,TexSampler,UV).rgb*2-1;'
                   'return normalize(T*n.x-cross(N,T)*n.y+N*n.z);')


def forest_impostor(package, reads, *, white, default_normal):
    """donor parent(default_normal), forest_impostor_material.py 6-53: the lit crown atlas (Tex, NormalTex and the
    per-species Tint), its haze, the subsurface tint, the per-instance fade mask, two-sided foliage, masked at .4.
    `white` is the engine WhiteSquareTexture the donor loaded; `default_normal` is T_ForestNormalDefault, which the
    donor's caller (import_forest.py 43-51) imported and passed in."""
    U = unreal
    M = U.MaterialEditingLibrary
    m = _material(package)
    M.delete_all_material_expressions(m)

    def node(cls, **props):
        n = M.create_material_expression(m, cls)
        for k, v in props.items():
            n.set_editor_property(k, v)
        return n

    colour = node(U.MaterialExpressionTextureSampleParameter2D, parameter_name='Tex', texture=reads[white])
    normal = node(U.MaterialExpressionTextureObjectParameter, parameter_name='NormalTex',
                  texture=reads[default_normal], sampler_type=U.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    uv = node(U.MaterialExpressionTextureCoordinate)
    tangent = node(U.MaterialExpressionVertexTangentWS)
    vertex = node(U.MaterialExpressionVertexNormalWS)
    mapped = node(U.MaterialExpressionCustom, output_type=U.CustomMaterialOutputType.CMOT_FLOAT3, code=IMPOSTOR_NORMAL)
    values = [('Tex', normal, ''), ('UV', uv, ''), ('T', tangent, ''), ('N', vertex, '')]
    mapped.set_editor_property('inputs', _custom_inputs([name for name, _, _ in values]))
    # Connect again after publishing the named inputs.
    for name, expression, output in values:
        assert M.connect_material_expressions(expression, output, mapped, name)
    assert M.connect_material_property(mapped, '', U.MaterialProperty.MP_NORMAL)
    # Per-species tint (TINTS): a baked atlas keeps the leaf texture's own colour, which reads pale from afar.
    tint = node(U.MaterialExpressionVectorParameter, parameter_name='Tint', default_value=U.LinearColor(1, 1, 1, 1))
    tinted = node(U.MaterialExpressionMultiply)
    M.connect_material_expressions(colour, 'RGB', tinted, 'A')
    M.connect_material_expressions(tint, '', tinted, 'B')
    fill = node(U.MaterialExpressionMultiply, const_b=.015)
    M.connect_material_expressions(tinted, '', fill, 'A')
    base, emit = haze.apply(unreal, m, tinted, fill)
    M.connect_material_property(base, '', U.MaterialProperty.MP_BASE_COLOR)
    M.connect_material_property(emit, '', U.MaterialProperty.MP_EMISSIVE_COLOR)
    subsurface = node(U.MaterialExpressionMultiply, const_b=.22)
    M.connect_material_expressions(tinted, '', subsurface, 'A')
    M.connect_material_property(subsurface, '', U.MaterialProperty.MP_SUBSURFACE_COLOR)
    fade = node(U.MaterialExpressionPerInstanceFadeAmount)
    mask = node(U.MaterialExpressionMultiply)
    M.connect_material_expressions(colour, 'A', mask, 'A')
    M.connect_material_expressions(fade, '', mask, 'B')
    M.connect_material_property(mask, '', U.MaterialProperty.MP_OPACITY_MASK)
    M.connect_material_property(node(U.MaterialExpressionConstant, r=1.), '', U.MaterialProperty.MP_ROUGHNESS)
    M.connect_material_property(node(U.MaterialExpressionConstant, r=0.), '', U.MaterialProperty.MP_SPECULAR)
    m.set_editor_property('blend_mode', U.BlendMode.BLEND_MASKED)
    m.set_editor_property('two_sided', True)
    m.set_editor_property('opacity_mask_clip_value', .4)
    m.set_editor_property('shading_model', U.MaterialShadingModel.MSM_TWO_SIDED_FOLIAGE)
    m.set_editor_property('tangent_space_normal', False)
    m.set_editor_property('dithered_lod_transition', True)
    m.set_editor_property('used_with_instanced_static_meshes', True)
    M.recompile_material(m)
    return m


# --- The forest floor (M_ForestGround) ----------------------------------------------------------------------------------

def _ground_grain(texture, sampler, position, result='groundDetail'):
    """ground_grain.py code: the same Sunburst detail, coordinates and field scale on both sides of every ground join."""
    return f'''float3 floorFine=Texture2DSample({texture},{sampler},{position}.xy/900.).rgb*2;
float3 floorStand=Texture2DSample({texture},{sampler},{position}.xy/4500.+.31).rgb*2;
float3 floorField=Texture2DSample({texture},{sampler},{position}.xy/16000.+.67).rgb*2;
float3 {result}=floorFine*lerp(float3(1,1,1),floorStand,.55)*lerp(float3(1,1,1),floorField,.35);'''


FOREST_GROUND = '''
float3 colour=lerp(float3(.055,.11,.035),float3(.105,.145,.055),n);
float3 nearColour=Texture2DSample(NearTex,NearTexSampler,float2(P.x,-P.y)/600.).rgb;
colour=lerp(colour,nearColour,Near);
float3 coast=lerp(C.rgb/12.92,pow((C.rgb+.055)/1.055,2.4),step(.04045,C.rgb));
colour=lerp(colour,coast,Alpha);
'''


def forest_ground(package, reads, *, near, detail, south_join_m):
    """donor material(rock=False), forest_ground.py 16-59: the forest floor colour (brightening over the 300 m north of
    Belmonte's southern join), the near-ground texture by NearGround, the coast's vertex colour by its alpha, the
    meadow grain, the haze, matte. `near` and `detail` are T_ground and T_ground_detail; `south_join_m` is the donor
    build's hidamari/north_snow.json south_join_m, which the donor read at build time."""
    U = unreal
    M = U.MaterialEditingLibrary
    m = _material(package)
    M.delete_all_material_expressions(m)

    def node(cls, **props):
        n = M.create_material_expression(m, cls)
        for k, v in props.items():
            n.set_editor_property(k, v)
        return n

    p = node(U.MaterialExpressionWorldPosition)
    vc = node(U.MaterialExpressionVertexColor)
    near_param = node(U.MaterialExpressionScalarParameter, parameter_name='NearGround', default_value=0.)
    near_tex = node(U.MaterialExpressionTextureObject, texture=reads[near])
    tex = node(U.MaterialExpressionTextureObject, texture=reads[detail])
    # The forest floor brightens over the 300 m north of Belmonte's southern join (belmonte/appearance.py far_palette).
    join = south_join_m * 100
    base = node(U.MaterialExpressionCustom, output_type=U.CustomMaterialOutputType.CMOT_FLOAT3,
                code=f'float n=smoothstep({join:.0f}.,{join + 30000:.0f}.,-P.y);' + FOREST_GROUND
                + _ground_grain('Tex', 'TexSampler', 'P') + '\nreturn colour*lerp(groundDetail,1,Near*(1-Alpha));')
    base.set_editor_property('inputs', _custom_inputs(['P', 'Tex', 'NearTex', 'Near', 'C', 'Alpha']))
    assert M.connect_material_expressions(p, '', base, 'P')
    assert M.connect_material_expressions(tex, '', base, 'Tex')
    for src, out, key in [(near_tex, '', 'NearTex'), (near_param, '', 'Near'), (vc, '', 'C'), (vc, 'A', 'Alpha')]:
        assert M.connect_material_expressions(src, out, base, key)
    fill = node(U.MaterialExpressionConstant, r=0.)
    shaded, emission = haze.apply(unreal, m, base, fill)
    M.connect_material_property(shaded, '', U.MaterialProperty.MP_BASE_COLOR)
    M.connect_material_property(emission, '', U.MaterialProperty.MP_EMISSIVE_COLOR)
    M.connect_material_property(node(U.MaterialExpressionConstant, r=1.), '', U.MaterialProperty.MP_ROUGHNESS)
    M.connect_material_property(node(U.MaterialExpressionConstant, r=0.), '', U.MaterialProperty.MP_SPECULAR)
    m.set_editor_property('used_with_instanced_static_meshes', True)
    M.recompile_material(m)
    return m


# --- The coastal rock (M_CoastRock) -------------------------------------------------------------------------------------

ROCK_LINEAR_LUMINANCE = .0908408217639082   # coast_rock_look.py: the texture's mean, after the sRGB transfer
ROCK_TILE_METRES = 24.
ROCK_NORMAL = ('float3 n=cross(ddx(P),ddy(P)); float l2=dot(n,n); '
               'n=l2>1.e-16?n*rsqrt(max(l2,1.e-16)):N; '
               'return dot(n,N)<0.?-n:n;')
ROCK_COLOUR = f'''
float3 colour=lerp(C.rgb/12.92,pow((C.rgb+.055)/1.055,2.4),step(.04045,C.rgb));
float3 weights=pow(abs(N),4.);
weights/=max(weights.x+weights.y+weights.z,1.e-5);
float3 q=P/{ROCK_TILE_METRES*100.:.1f};
float3 stone=Texture2DSample(Rock,RockSampler,q.yz).rgb*weights.x
            +Texture2DSample(Rock,RockSampler,q.xz).rgb*weights.y
            +Texture2DSample(Rock,RockSampler,q.xy).rgb*weights.z;
float grain=dot(stone,float3(.2126,.7152,.0722))/{ROCK_LINEAR_LUMINANCE:.12f};
return colour*lerp(1.,clamp(grain,.35,1.75),.65);
'''


def coast_rock(package, reads, *, texture):
    """donor rock_material(), forest_ground.py 62-112, with coast_rock_look.code (the colour detail): the vertex geology
    colour times the triplanar rock grain, its own world-space geometric normal against the vertex normal, the haze,
    matte. `texture` is T_CoastRock (the donor imported and pinned it in the same function, lines 68-78)."""
    U = unreal
    M = U.MaterialEditingLibrary
    m = _material(package)
    M.delete_all_material_expressions(m)   # material_assets.create, on an existing material

    def node(cls, **props):
        n = M.create_material_expression(m, cls)
        for key, value in props.items():
            n.set_editor_property(key, value)
        return n

    def custom(code, connections):
        n = node(U.MaterialExpressionCustom, output_type=U.CustomMaterialOutputType.CMOT_FLOAT3, code=code)
        n.set_editor_property('inputs', _custom_inputs([key for key, _, _ in connections]))
        for key, source, output in connections:
            assert M.connect_material_expressions(source, output, n, key)
        return n

    p = node(U.MaterialExpressionWorldPosition)
    vc = node(U.MaterialExpressionVertexColor)
    vertex_normal = node(U.MaterialExpressionVertexNormalWS)
    normal = custom(ROCK_NORMAL, [('P', p, ''), ('N', vertex_normal, '')])
    base = custom(ROCK_COLOUR, [('P', p, ''), ('N', normal, ''), ('C', vc, ''),
                                ('Rock', node(U.MaterialExpressionTextureObject, texture=reads[texture]), '')])
    shaded, emission = haze.apply(unreal, m, base, node(U.MaterialExpressionConstant, r=0.))
    for prop, n in [(U.MaterialProperty.MP_BASE_COLOR, shaded), (U.MaterialProperty.MP_EMISSIVE_COLOR, emission),
                    (U.MaterialProperty.MP_NORMAL, normal),
                    (U.MaterialProperty.MP_ROUGHNESS, node(U.MaterialExpressionConstant, r=1.)),
                    (U.MaterialProperty.MP_SPECULAR, node(U.MaterialExpressionConstant, r=0.))]:
        assert M.connect_material_property(n, '', prop)
    m.set_editor_property('tangent_space_normal', False)
    m.set_editor_property('used_with_instanced_static_meshes', True)
    errors = M.recompile_material(m)   # material_assets.save_material, without its save
    if errors:
        raise RuntimeError(f'{m.get_path_name()}: material compile failed: {errors}')
    return m


# --- The Mega Park gate ground (M_NorthGate) ----------------------------------------------------------------------------

def _seamless(p):
    """mountain_material.py 249-255: add to s the ground texture at p with no tile edges, four samples half a tile apart,
    each weighted away from its own edges."""
    taps = ['Texture2DSample(Tex,TexSampler,p+float2(%s)).rgb' % o for o in ('0,0', '.5,0', '0,.5', '.5,.5')]
    return ('p=%s;w=smoothstep(.3,.9,abs(frac(p)-.5)*2);a=lerp(%s,%s,w.x);b=lerp(%s,%s,w.x);s+=lerp(a,b,w.y);'
            % (p, *taps))


def north_gate(package, reads, *, ground):
    """donor gate_material(), mountain_material.py 257-296: the vertex colour times T_ground (`ground`) by the vertex
    alpha, sampled without tile edges at two scales and divided by its mean, the haze taken out of the base colour and
    given back as emission (atmosphere.glow), matte."""
    U = unreal
    l = U.MaterialEditingLibrary
    m = _material(package)
    l.delete_all_material_expressions(m)
    vc = l.create_material_expression(m, U.MaterialExpressionVertexColor, -700, 0)
    depth = l.create_material_expression(m, U.MaterialExpressionPixelDepth, -700, 400)
    uv = l.create_material_expression(m, U.MaterialExpressionTextureCoordinate, -700, 200)
    tex = l.create_material_expression(m, U.MaterialExpressionTextureObject, -700, 300)
    tex.set_editor_property('texture', reads[ground])
    c = l.create_material_expression(m, U.MaterialExpressionCustom, -300, 0)
    c.set_editor_property('code', 'float3 base=lerp(C/12.92,pow((C+.055)/1.055,2.4),step(.04045,C));'
                          'float3 M=float3(.163,.183,.036);float3 s=float3(0,0,0);float2 p,w;float3 a,b;'
                          + _seamless('UV') + _seamless('float2(UV.x*.8-UV.y*.6,UV.x*.6+UV.y*.8)*.37+.3') +
                          'float3 T=max(M+(s*.5-M)*1.8,0);float3 g=lerp(float3(1,1,1),T/M,saturate(A));'
                          'return base*g*(1-' + SHARE + ');')
    c.set_editor_property('output_type', U.CustomMaterialOutputType.CMOT_FLOAT3)
    c.set_editor_property('inputs', _custom_inputs(('C', 'A', 'UV', 'Tex', 'D')))
    l.connect_material_expressions(vc, '', c, 'C')
    l.connect_material_expressions(vc, 'A', c, 'A')
    l.connect_material_expressions(uv, '', c, 'UV')
    l.connect_material_expressions(tex, '', c, 'Tex')
    l.connect_material_expressions(depth, '', c, 'D')
    l.connect_material_property(c, '', U.MaterialProperty.MP_BASE_COLOR)
    l.connect_material_property(haze.glow(unreal, m), '', U.MaterialProperty.MP_EMISSIVE_COLOR)
    for prop, value in [(U.MaterialProperty.MP_ROUGHNESS, 1.), (U.MaterialProperty.MP_SPECULAR, 0.)]:
        n = l.create_material_expression(m, U.MaterialExpressionConstant, 100, 300)
        n.set_editor_property('r', value)
        l.connect_material_property(n, '', prop)
    m.set_editor_property('used_with_instanced_static_meshes', True)     # AJapanWorld draws HD_NorthGate as an instance
    l.recompile_material(m)
    return m


# --- The northern mountains and volcano (M_NorthMountains) --------------------------------------------------------------

# mountain_material.py lines 14-40, verbatim
# The caldera floor reads as the painting (tools/craterpark_textures.py 'crater_floor'): the vertex colour times its
# variation about its mean, and this share of the painting's own colour.
CRATER_PAINT=.5

def crater_hlsl(meta):
    """HLSL setting `crater`: how much of the painted floor lies at P (the mask, north_crater.json's texel-centred
    footprint), on flat enough ground, never on a loose rock (Caps)."""
    x0,y0,_,_=meta['bounds']
    return (f'float2 craterUV=((float2(P.x,-P.y)/100.-float2({x0},{y0}))/{meta["step_m"]}+.5)/{meta["size"][0]}.;'
            'float crater=Texture2DSampleLevel(Crater,CraterSampler,craterUV,0.).r*saturate((N.z-.72)/.16)*(1-Caps);')


def floor_hlsl(metres,mean):
    """HLSL laying the painting (Floor, sRGB mean `mean`) over `ground` by `crater`: on three axes at its own tile
    (P/800 for 8 m), varied by a second, larger sample about its mean so its repeats do not show across the floor;
    the vertex colour times the painting's variation about its mean, with CRATER_PAINT of the painting's own colour."""
    lin=[c/255./12.92 if c/255.<=.04045 else ((c/255.+.055)/1.055)**2.4 for c in mean]
    def sample(q):
        return ('(Texture2DSample(Floor,FloorSampler,%s.yz).rgb*cw.x+Texture2DSample(Floor,FloorSampler,%s.xz).rgb*cw.y'
                '+Texture2DSample(Floor,FloorSampler,%s.xy).rgb*cw.z)'%(q,q,q))
    return ('float3 cw=pow(abs(N),4);cw/=max(cw.x+cw.y+cw.z,.001);'
            'float3 cp=P/%.1f;float3 cq=P/%.1f+.41;'%(metres*100,metres*100*2.9)
            +'float3 CFM=float3(%.5f,%.5f,%.5f);'%tuple(lin)
            +'float3 floorTex=%s*sqrt(max(%s/CFM,.05));'%(sample('cp'),sample('cq'))
            +'float3 painted=lerp(base*floorTex/CFM,floorTex,%s);'%CRATER_PAINT
            +'ground=lerp(ground,painted,crater);')



def north_mountains(package, reads, *, rock, ground_detail, snow_mask, crater_mask, crater_floor, collection,
                    bounds_x0_m, bounds_y0_m, bounds_x1_m, bounds_y1_m, step_m, mask_size, volcano_x_m, volcano_y_m,
                    rock_radius_inner_m, rock_radius_outer_m, rock_prominence_low_m, rock_prominence_high_m, south_join_m,
                    floor_metres, floor_mean_r, floor_mean_g, floor_mean_b):
    """donor material(), mountain_material.py 42-233: the vertex-colour landscape with triplanar volcanic rock grain on
    the exposed band, meadow grain, Voronoi facets lit by the MPC_Wind sun, strata, the painted caldera floor, the snow
    mask and the rock caps, the neutral sky bounce and the haze; matte, dithered LOD.

    The reads are T_VolcanicRock, T_ground_detail, T_NorthSnowMask, T_NorthCraterMask, T_NorthCraterFloor (the donor
    imported all but the detail in this function) and MPC_Wind. The donor read the rest from its build output, and it
    arrives as scalar arguments, regathered here into the donor's own shapes: hidamari/north_snow.json (bounds, step_m,
    volcano_m, rock_radius_m, rock_prominence_m, south_join_m), hidamari/north_crater.json (the same bounds and step, its
    size: mask_size), craterpark/textures/textures.json world_aligned.crater_floor.metres (floor_metres) and
    tools/craterpark_textures.py WORLD_ALIGNED['crater_floor'][2] (floor_mean_r, _g, _b)."""
    snow={'bounds':[bounds_x0_m,bounds_y0_m,bounds_x1_m,bounds_y1_m],'step_m':step_m,'volcano_m':[volcano_x_m,volcano_y_m],
          'rock_radius_m':[rock_radius_inner_m,rock_radius_outer_m],
          'rock_prominence_m':[rock_prominence_low_m,rock_prominence_high_m],'south_join_m':south_join_m}
    crater={'bounds':snow['bounds'],'step_m':step_m,'size':[mask_size,mask_size]}
    floor_mean=(floor_mean_r,floor_mean_g,floor_mean_b)
    l=unreal.MaterialEditingLibrary
    m=_material(package)
    l.delete_all_material_expressions(m)
    assert crater['size']==[1024,1024]   # the donor's check (mountain_material.py 89): the shaders' texel size
    step=snow['step_m']
    x0,y0,_,_=snow['bounds']
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
    crater_code=crater_hlsl(crater)
    floor_code=floor_hlsl(float(floor_metres),floor_mean)
    # The volcano's exposed-rock band and the join to Belmonte's palette, in centimetres (hidamari/mountains.py).
    (vx,vy),(r0,r1),(p0,p1),join=snow['volcano_m'],snow['rock_radius_m'],snow['rock_prominence_m'],snow['south_join_m']
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
'''+_ground_grain('Ground','GroundSampler','P')+'''
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
float3 facet=(.28+1.15*litFacet)/(.28+1.15*litSmooth)*lerp(float3(.92,.94,1.06),float3(1.08,1.02,.92),saturate(litFacet*1.4-.2));
ground*=lerp(float3(1.,1.,1.),facet,high*(1-smoothstep(60000.,250000.,D)));
float strata=1.-.08*sin(P.z*.0021+sin(P.x*.0007)*2.)*(1-abs(N.z))*(1-smoothstep(35000.,100000.,D))*(1-join);
'''+crater_code+floor_code+'''
float3 snow=float3(.80,.83,.89)*lerp(.9,1.05,saturate((g3-.6)/.9))*lerp(1.,.92,saturate(1-N.z));
'''+snow_code+'''
return lerp(ground*strata,snow,snowMask)*(1-'''+SHARE+');')
    c.set_editor_property('output_type',unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    args=[]
    for key in ('C','D','A','P','N','Tex','Ground','Snow','Sun','Caps','Crater','Floor'):
        a=unreal.CustomInput();a.set_editor_property('input_name',key);args.append(a)
    c.set_editor_property('inputs',args)
    l.connect_material_expressions(vc,'',c,'C');l.connect_material_expressions(depth,'',c,'D')
    l.connect_material_expressions(vc,'A',c,'A')
    p=l.create_material_expression(m,unreal.MaterialExpressionWorldPosition,-600,400)
    n=l.create_material_expression(m,unreal.MaterialExpressionVertexNormalWS,-600,500)
    tex=l.create_material_expression(m,unreal.MaterialExpressionTextureObject,-600,600);tex.set_editor_property('texture',reads[rock])
    detail=reads[ground_detail]
    ground=l.create_material_expression(m,unreal.MaterialExpressionTextureObject,-600,700);ground.set_editor_property('texture',detail)
    snow_object=l.create_material_expression(m,unreal.MaterialExpressionTextureObject,-600,800)
    snow_object.set_editor_property('texture',reads[snow_mask])
    snow_object.set_editor_property('sampler_type',unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_GRAYSCALE)
    l.connect_material_expressions(p,'',c,'P');l.connect_material_expressions(n,'',c,'N');l.connect_material_expressions(tex,'',c,'Tex')
    l.connect_material_expressions(ground,'',c,'Ground')
    l.connect_material_expressions(snow_object,'',c,'Snow')
    crater_object=l.create_material_expression(m,unreal.MaterialExpressionTextureObject,-600,1100)
    crater_object.set_editor_property('texture',reads[crater_mask])
    crater_object.set_editor_property('sampler_type',unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_GRAYSCALE)
    floor_object=l.create_material_expression(m,unreal.MaterialExpressionTextureObject,-600,1200)
    floor_object.set_editor_property('texture',reads[crater_floor])
    l.connect_material_expressions(crater_object,'',c,'Crater');l.connect_material_expressions(floor_object,'',c,'Floor')
    l.connect_material_property(c,'',unreal.MaterialProperty.MP_BASE_COLOR)
    # Exposed volcanic rock has a neutral sky-bounce floor. It is zero at the
    # woodland/collar joins, and snow retains its existing physical lighting.
    ambient=l.create_material_expression(m,unreal.MaterialExpressionCustom,200,150)
    ambient.set_editor_property('output_type',unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    ambient.set_editor_property('code',snow_code+rock_band+crater_code+'''
float bounce=dot(Base,float3(.299,.587,.114))*.25*high*(1-snowMask)*(1-crater)*(1-saturate(dot(N,normalize(Sun.xyz))))*Sun.w;
return float3(bounce,bounce,bounce);''')
    inputs=[]
    for key in ('Base','P','N','D','Snow','Tex','Sun','Caps','Crater'):
        value=unreal.CustomInput();value.set_editor_property('input_name',key);inputs.append(value)
    ambient.set_editor_property('inputs',inputs)
    l.connect_material_expressions(c,'',ambient,'Base');l.connect_material_expressions(p,'',ambient,'P')
    l.connect_material_expressions(snow_object,'',ambient,'Snow')
    l.connect_material_expressions(crater_object,'',ambient,'Crater')
    l.connect_material_expressions(n,'',ambient,'N');l.connect_material_expressions(depth,'',ambient,'D')
    l.connect_material_expressions(tex,'',ambient,'Tex')
    wind=reads[collection]
    sun=l.create_material_expression(m,unreal.MaterialExpressionCollectionParameter,-600,900)
    sun.set_editor_property('collection',wind);sun.set_editor_property('parameter_name','SunDirection')
    l.connect_material_expressions(sun,'',ambient,'Sun');l.connect_material_expressions(sun,'',c,'Sun')
    caps=l.create_material_expression(m,unreal.MaterialExpressionScalarParameter,-600,1000)
    caps.set_editor_property('parameter_name','Caps');caps.set_editor_property('default_value',0.)
    l.connect_material_expressions(caps,'',ambient,'Caps');l.connect_material_expressions(caps,'',c,'Caps')
    emission=l.create_material_expression(m,unreal.MaterialExpressionAdd,400,150)
    l.connect_material_expressions(haze.glow(unreal, m),'',emission,'A')
    l.connect_material_expressions(ambient,'',emission,'B')
    l.connect_material_property(emission,'',unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    for prop,value in [(unreal.MaterialProperty.MP_ROUGHNESS,1.),(unreal.MaterialProperty.MP_SPECULAR,0.)]:
        n=l.create_material_expression(m,unreal.MaterialExpressionConstant,100,300);n.set_editor_property('r',value)
        l.connect_material_property(n,'',prop)
    m.set_editor_property('used_with_instanced_static_meshes',True)
    m.set_editor_property('dithered_lod_transition',True)
    l.recompile_material(m)
    return m


