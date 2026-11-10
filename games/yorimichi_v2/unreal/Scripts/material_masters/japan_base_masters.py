"""The japan base masters: the Materials of adopted/japan/materials/base-materials that have a recoverable generator and no
donor helper. Thirteen of the record's 27 packages are here; the rest stay in the record (docs/inventory/master-sources.md,
section 10). Donor: games/yorimichi/unreal/Scripts/ at the V2 source baseline 7eec0f98dd (docs/DECISIONS.md D01). Every
builder carries its donor file and line range in the family's donor_lines, and in its own comment.

The graphs, parameter names and defaults, wiring and settings are the donor's. What moved out of the builders:
no asset is saved or loaded here (the importer saves the one it accepts, after reading it back against the saved original),
no texture is imported (every texture arrives through reads[path]), and the donor's Python-side loops are unchanged.
The donor helpers that these builders use are copied below, with their donor lines pinned in the comments.

Nothing runs at import: the module is functions only, so it imports without the Unreal editor, where `unreal` is None and
a builder cannot run.

A builder takes the destination package path, the loaded reads ({package: asset}) and the recipe's arguments as keyword
arguments, and returns the rebuilt material.
"""
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


def _node(material, cls, x, y, **props):
    """material_assets.py lines 34-38 (node): an expression at (x, y) with its properties set. Copied, not imported."""
    e = unreal.MaterialEditingLibrary.create_material_expression(material, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def _link(a, ao, b, bi):
    """material_assets.py lines 41-42 (link): a connection between two expressions. Copied, not imported."""
    unreal.MaterialEditingLibrary.connect_material_expressions(a, ao, b, bi)


def _custom_inputs(names):
    args = []
    for key in names:
        arg = unreal.CustomInput()
        arg.set_editor_property('input_name', key)
        args.append(arg)
    return args


# --- Arcade (M_Arcade, and M_ArcadePaving with paving) ------------------------------------------------------------------

ARCADE_COLOUR = '''
float3 L=lerp(C/12.92,pow((C+.055)/1.055,2.4),step(.04045,C));
float wood=step(L.g*1.45,L.r)*step(L.b*1.5,L.g)*(1-step(.35,L.r));
float grain=sin(UV.x*67+sin(UV.y*3.1)*1.6)*sin(UV.x*23+UV.y*.6);
float fade=1-saturate((length(ddx(UV))+length(ddy(UV)))*45);
float3 timber=Texture2DSample(Tex,TexSampler,UV*.65).rgb;
float variation=dot(timber,float3(.3,.59,.11));
return L*lerp(1,clamp(variation/.22,.72,1.25),wood*.75)*(1+grain*.03*wood*fade);
'''
ARCADE_PAVING_COLOUR = 'float3 L=lerp(C/12.92,pow((C+.055)/1.055,2.4),step(.04045,C)); float leaf=step(.07,max(L.r,max(L.g,L.b))-min(L.r,min(L.g,L.b))); return lerp(Texture2DSample(Tex,TexSampler,UV/2.1).rgb*.61,L,leaf);'
ARCADE_GLOW = 'float lamp=step(.82,C.r)*step(.45,C.g)*step(C.g,.68)*step(C.b,.30); float canvas=step(.70,C.r)*step(C.r,.79)*step(.55,C.g)*step(.35,C.b); float leaf=step(.4,C.r)*step(.24,C.g)*step(C.b,.07); float shop=step(.18,C.r)*step(C.r,.22)*step(.08,C.g)*step(C.g,.11)*step(.02,C.b)*step(C.b,.04); return C*(.045+lamp*.9+canvas*.20+leaf*.38+shop*.15);'


def arcade_material(package, reads, *, texture, paving):
    """donor material(paving), arcade_material.py 24-63. `texture` is the read of the timber (or, for the paving, the paving)
    texture record's package (donor: texture(), lines 7-21, imported the same file). The paving changes only the colour
    code (donor line 45), so both masters are this one function."""
    MEL = unreal.MaterialEditingLibrary
    m = _material(package)
    MEL.delete_all_material_expressions(m)
    vc = MEL.create_material_expression(m, unreal.MaterialExpressionVertexColor, -600, 0)
    uv = MEL.create_material_expression(m, unreal.MaterialExpressionTextureCoordinate, -600, 200)
    tex = MEL.create_material_expression(m, unreal.MaterialExpressionTextureObject, -600, 400)
    tex.set_editor_property('texture', reads[texture])
    colour = MEL.create_material_expression(m, unreal.MaterialExpressionCustom, -250, 0)
    colour.set_editor_property('code', ARCADE_COLOUR)
    if paving:
        colour.set_editor_property('code', ARCADE_PAVING_COLOUR)
    colour.set_editor_property('output_type', unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    colour.set_editor_property('inputs', _custom_inputs(['C', 'UV', 'Tex']))
    MEL.connect_material_expressions(vc, '', colour, 'C')
    MEL.connect_material_expressions(uv, '', colour, 'UV')
    MEL.connect_material_expressions(tex, '', colour, 'Tex')
    MEL.connect_material_property(colour, '', unreal.MaterialProperty.MP_BASE_COLOR)
    glow = MEL.create_material_expression(m, unreal.MaterialExpressionCustom, 0, 200)
    glow.set_editor_property('code', ARCADE_GLOW)
    glow.set_editor_property('output_type', unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    glow.set_editor_property('inputs', _custom_inputs(['C']))
    MEL.connect_material_expressions(colour, '', glow, 'C')
    MEL.connect_material_property(glow, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    for prop, value in [(unreal.MaterialProperty.MP_ROUGHNESS, .87), (unreal.MaterialProperty.MP_SPECULAR, .12)]:
        n = MEL.create_material_expression(m, unreal.MaterialExpressionConstant, 200, 400)
        n.set_editor_property('r', value)
        MEL.connect_material_property(n, '', prop)
    m.set_editor_property('used_with_instanced_static_meshes', True)
    MEL.recompile_material(m)
    return m


# --- Bike (M_Bike) -----------------------------------------------------------------------------------------------------

def bike_material(package, reads):
    """donor material(), bike_material.py 6-32: the vertex-colour palette and the finish mask (vertex alpha)."""
    M = unreal.MaterialEditingLibrary
    mat = _material(package)
    M.delete_all_material_expressions(mat)

    def custom(code, names, output=unreal.CustomMaterialOutputType.CMOT_FLOAT3):
        n = M.create_material_expression(mat, unreal.MaterialExpressionCustom, -200, 0)
        n.set_editor_property('code', code)
        n.set_editor_property('output_type', output)
        n.set_editor_property('inputs', _custom_inputs(names))
        return n

    vc = M.create_material_expression(mat, unreal.MaterialExpressionVertexColor, -600, 0)
    colour = custom('return lerp(C/12.92,pow((C+.055)/1.055,2.4),step(.04045,C));', ['C'])
    # Same curves as the Blender preview in assets/vehicles/bike/build.py: paint stays dielectric, chrome is metal.
    metal = custom('return saturate((A-.5)*2.5);', ['A'], unreal.CustomMaterialOutputType.CMOT_FLOAT1)
    rough = custom('return lerp(.78,.22,A);', ['A'], unreal.CustomMaterialOutputType.CMOT_FLOAT1)
    assert M.connect_material_expressions(vc, '', colour, 'C')
    assert M.connect_material_expressions(vc, 'A', metal, 'A')
    assert M.connect_material_expressions(vc, 'A', rough, 'A')
    assert M.connect_material_property(colour, '', unreal.MaterialProperty.MP_BASE_COLOR)
    assert M.connect_material_property(metal, '', unreal.MaterialProperty.MP_METALLIC)
    assert M.connect_material_property(rough, '', unreal.MaterialProperty.MP_ROUGHNESS)
    M.recompile_material(mat)
    return mat


# --- Harbor, the non-water branch (M_Harbor) ---------------------------------------------------------------------------

HARBOR_COLOUR = '''
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
'''
HARBOR_NORMAL = '''
if(abs(A-.5)>.07)return float3(0,0,1);
float2 q=UV/2.4;
float2 e=float2(.0015,0);
float dx=dot(Texture2DSample(Stone,StoneSampler,q+e.xy).rgb-Texture2DSample(Stone,StoneSampler,q-e.xy).rgb,float3(.3,.59,.11));
float dy=dot(Texture2DSample(Stone,StoneSampler,q+e.yx).rgb-Texture2DSample(Stone,StoneSampler,q-e.yx).rgb,float3(.3,.59,.11));
return normalize(float3(-dx*9,-dy*9,1));
'''


def harbor_material(package, reads, *, paving, timber):
    """donor material(water=False), harbor_material.py 39-61 (the shared head) and 143-176 (the non-water branch); the water
    branch, 62-142, is not in this builder. `paving` and `timber` are the read packages of the two harbor texture records
    (donor: texture('paving') and texture('timber'), lines 21-36, imported the same files)."""
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

    vc = node(unreal.MaterialExpressionVertexColor)
    uv = node(unreal.MaterialExpressionTextureCoordinate)
    node(unreal.MaterialExpressionWorldPosition)   # donor line 60: created, never wired on this branch
    node(unreal.MaterialExpressionTime)            # donor line 61: likewise
    paving_tex = node(unreal.MaterialExpressionTextureObject, texture=reads[paving])
    timber_tex = node(unreal.MaterialExpressionTextureObject, texture=reads[timber])
    color = custom(HARBOR_COLOUR, [('C', vc, ''), ('A', vc, 'A'), ('UV', uv, ''), ('Stone', paving_tex, ''), ('Wood', timber_tex, '')])
    prop(color, unreal.MaterialProperty.MP_BASE_COLOR)
    normal = custom(HARBOR_NORMAL, [('A', vc, 'A'), ('UV', uv, ''), ('Stone', paving_tex, '')])
    prop(normal, unreal.MaterialProperty.MP_NORMAL)
    rough = custom('return lerp(.83,.19,step(.95,A));', [('A', vc, 'A')], unreal.CustomMaterialOutputType.CMOT_FLOAT1)
    prop(rough, unreal.MaterialProperty.MP_ROUGHNESS)
    prop(node(unreal.MaterialExpressionConstant, r=.35), unreal.MaterialProperty.MP_SPECULAR)
    # Restrained fill keeps readable contact shadows on this sunlit kit.
    fill = node(unreal.MaterialExpressionMultiply, const_b=.025)
    link(color, '', fill, 'A')
    prop(fill, unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    m.set_editor_property('used_with_instanced_static_meshes', True)
    MEL.layout_material_expressions(m)
    MEL.recompile_material(m)
    return m


# --- Plaza: the paving and the fountain and pond water (M_PlazaPaving, M_PlazaWater, M_PondWater) ----------------------

PLAZA_WATER_COLOUR = 'return lerp(C/12.92,pow((C+.055)/1.055,2.4),step(.04045,C));'
PLAZA_POND_COLOUR = 'return float3(.006,.048,.042);'
PLAZA_WATER_NORMAL = 'float r=length(UV); float a=sin(r*20-T*2.5)*.055; return normalize(float3(sin(UV.x*11+UV.y*7+T)*.07+a,cos(UV.y*13-UV.x*4-T*1.2)*.07+a,1));'
PLAZA_POND_NORMAL = 'return normalize(float3(sin(UV.x*.8+UV.y*.6+sin(UV.y*.23+UV.x*.19)*.5+T*.45)*.075+sin(UV.y*2.1-T*.65)*.018,cos(UV.y*.9-UV.x*.5+sin(UV.x*.27)*.4-T*.35)*.075,1));'


def plaza_water(package, reads, *, pond):
    """donor water_material(name), plaza_material.py 5-34: the fountain (pond=False) and the pond (pond=True, the donor's
    `name == 'M_PondWater'`), with the donor's colour and normal overrides on lines 16 and 22."""
    MEL = unreal.MaterialEditingLibrary
    m = _material(package)
    MEL.delete_all_material_expressions(m)
    vc = MEL.create_material_expression(m, unreal.MaterialExpressionVertexColor, -500, 0)
    uv = MEL.create_material_expression(m, unreal.MaterialExpressionTextureCoordinate, -500, 200)
    time = MEL.create_material_expression(m, unreal.MaterialExpressionTime, -500, 400)
    colour = MEL.create_material_expression(m, unreal.MaterialExpressionCustom, -200, 0)
    colour.set_editor_property('code', PLAZA_WATER_COLOUR)
    if pond:
        colour.set_editor_property('code', PLAZA_POND_COLOUR)
    colour.set_editor_property('output_type', unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    colour.set_editor_property('inputs', _custom_inputs(['C']))
    MEL.connect_material_expressions(vc, '', colour, 'C')
    MEL.connect_material_property(colour, '', unreal.MaterialProperty.MP_BASE_COLOR)
    normal = MEL.create_material_expression(m, unreal.MaterialExpressionCustom, -200, 200)
    normal.set_editor_property('code', PLAZA_WATER_NORMAL)
    if pond:
        normal.set_editor_property('code', PLAZA_POND_NORMAL)
    normal.set_editor_property('output_type', unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    normal.set_editor_property('inputs', _custom_inputs(['UV', 'T']))
    MEL.connect_material_expressions(uv, '', normal, 'UV')
    MEL.connect_material_expressions(time, '', normal, 'T')
    MEL.connect_material_property(normal, '', unreal.MaterialProperty.MP_NORMAL)
    for prop, value in [(unreal.MaterialProperty.MP_ROUGHNESS, .24), (unreal.MaterialProperty.MP_SPECULAR, .6),
                        (unreal.MaterialProperty.MP_METALLIC, .10)]:
        n = MEL.create_material_expression(m, unreal.MaterialExpressionConstant, 200, 300)
        n.set_editor_property('r', value)
        MEL.connect_material_property(n, '', prop)
    m.set_editor_property('used_with_instanced_static_meshes', True)
    MEL.recompile_material(m)
    return m


PLAZA_PAVING_COLOUR = 'float3 L=lerp(C/12.92,pow((C+.055)/1.055,2.4),step(.04045,C)); float leaf=step(.07,max(L.r,max(L.g,L.b))-min(L.r,min(L.g,L.b))); return lerp(Texture2DSample(Tex,TexSampler,UV/3.2).rgb*float3(.61,.49,.34),L,leaf);'
PLAZA_PAVING_NORMAL = 'float2 p=UV/3.2; float h=dot(Texture2DSample(Tex,TexSampler,p).rgb,float3(.3,.59,.11)); float hx=dot(Texture2DSample(Tex,TexSampler,p+float2(.002,0)).rgb,float3(.3,.59,.11)); float hy=dot(Texture2DSample(Tex,TexSampler,p+float2(0,.002)).rgb,float3(.3,.59,.11)); float leaf=step(.07,max(C.r,max(C.g,C.b))-min(C.r,min(C.g,C.b))); return normalize(float3(float2(h-hx,h-hy)*2.5*(1-leaf),1));'


def plaza_paving(package, reads, *, texture):
    """donor paving_material(), plaza_material.py 37-68: the arcade's paving texture (donor line 45, T_Arcade_paving) through
    a colour and a height-derived normal. `texture` is the read package of that texture record."""
    MEL = unreal.MaterialEditingLibrary
    m = _material(package)
    MEL.delete_all_material_expressions(m)
    vc = MEL.create_material_expression(m, unreal.MaterialExpressionVertexColor, -500, 0)
    uv = MEL.create_material_expression(m, unreal.MaterialExpressionTextureCoordinate, -500, 200)
    tex = MEL.create_material_expression(m, unreal.MaterialExpressionTextureObject, -500, 400)
    tex.set_editor_property('texture', reads[texture])
    colour = MEL.create_material_expression(m, unreal.MaterialExpressionCustom, -200, 0)
    colour.set_editor_property('code', PLAZA_PAVING_COLOUR)
    colour.set_editor_property('output_type', unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    colour.set_editor_property('inputs', _custom_inputs(['C', 'UV', 'Tex']))
    for node, pin in [(vc, 'C'), (uv, 'UV'), (tex, 'Tex')]:
        MEL.connect_material_expressions(node, '', colour, pin)
    MEL.connect_material_property(colour, '', unreal.MaterialProperty.MP_BASE_COLOR)
    normal = MEL.create_material_expression(m, unreal.MaterialExpressionCustom, -200, 250)
    normal.set_editor_property('code', PLAZA_PAVING_NORMAL)
    normal.set_editor_property('output_type', unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    normal.set_editor_property('inputs', _custom_inputs(['C', 'UV', 'Tex']))
    for node, pin in [(vc, 'C'), (uv, 'UV'), (tex, 'Tex')]:
        MEL.connect_material_expressions(node, '', normal, pin)
    MEL.connect_material_property(normal, '', unreal.MaterialProperty.MP_NORMAL)
    for prop, value in [(unreal.MaterialProperty.MP_ROUGHNESS, .84), (unreal.MaterialProperty.MP_SPECULAR, .16)]:
        n = MEL.create_material_expression(m, unreal.MaterialExpressionConstant, 200, 300)
        n.set_editor_property('r', value)
        MEL.connect_material_property(n, '', prop)
    m.set_editor_property('used_with_instanced_static_meshes', True)
    MEL.recompile_material(m)
    return m


# --- Sailboat: the cloth and the wake (M_SailboatCloth, M_SailboatWake) ------------------------------------------------

def sailboat_material(package, reads, *, wake):
    """donor material(wake), sailboat_material.py 5-40: the sail's flutter (cloth) or the wake's foam (wake), with the
    runtime fill and speed parameters the donor names."""
    U = unreal
    M = U.MaterialEditingLibrary
    mat = _material(package)
    M.delete_all_material_expressions(mat)

    def node(cls, **props):
        n = M.create_material_expression(mat, cls, 0, 0)
        for k, v in props.items():
            n.set_editor_property(k, v)
        return n

    def link(a, ao, b, bi):
        assert M.connect_material_expressions(a, ao, b, bi)

    def custom(code, inputs, output=U.CustomMaterialOutputType.CMOT_FLOAT3):
        n = node(U.MaterialExpressionCustom, code=code, output_type=output)
        n.set_editor_property('inputs', _custom_inputs(list(inputs)))
        for key, (src, out) in inputs.items():
            link(src, out, n, key)
        return n

    def prop(n, p):
        assert M.connect_material_property(n, '', p)

    vc = node(U.MaterialExpressionVertexColor)
    t = node(U.MaterialExpressionTime)
    p = node(U.MaterialExpressionWorldPosition)
    col = custom('return lerp(C/12.92,pow((C+.055)/1.055,2.4),step(.04045,C));', {'C': (vc, '')})
    prop(col, U.MaterialProperty.MP_BASE_COLOR)
    prop(node(U.MaterialExpressionConstant, r=.95), U.MaterialProperty.MP_ROUGHNESS)
    prop(node(U.MaterialExpressionConstant, r=.1), U.MaterialProperty.MP_SPECULAR)
    mat.set_editor_property('two_sided', True)
    if wake:
        mat.set_editor_property('blend_mode', U.BlendMode.BLEND_TRANSLUCENT)
        mat.set_editor_property('translucency_lighting_mode', U.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
        amount = node(U.MaterialExpressionScalarParameter, parameter_name='WakeAmount', default_value=0.)
        op = custom('return A*S*(.70+.20*sin(T*3.4+P.x*.019+P.y*.023));',
                    {'A': (vc, 'A'), 'S': (amount, ''), 'T': (t, ''), 'P': (p, '')}, U.CustomMaterialOutputType.CMOT_FLOAT1)
        prop(op, U.MaterialProperty.MP_OPACITY)
        prop(custom('return float3(0,0,sin(T*1.8+P.x*.008+P.y*.006)*.7);', {'T': (t, ''), 'P': (p, '')}),
             U.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    else:
        fill = node(U.MaterialExpressionScalarParameter, parameter_name='SailFill', default_value=1.)
        direction = node(U.MaterialExpressionVectorParameter, parameter_name='FlutterDirection',
                         default_value=U.LinearColor(0, 1, 0, 0))
        flutter = custom('float wave=sin(T*2.5+P.z*.023)+.28*sin(T*5.1+P.x*.018);return D*A*(1.0+S*2.0)*wave;',
                         {'A': (vc, 'A'), 'S': (fill, ''), 'D': (direction, ''), 'T': (t, ''), 'P': (p, '')})
        prop(flutter, U.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    M.recompile_material(mat)
    return mat


# --- Zeppelin fabric (M_ZeppelinFabric) --------------------------------------------------------------------------------

def fabric_material(package, reads):
    """donor fabric_material(), import_zeppelin.py 13-30: the unlit fabric, lit by the sun direction parameter."""
    M = unreal.MaterialEditingLibrary
    m = _material(package)
    M.delete_all_material_expressions(m)
    m.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_UNLIT)
    color = M.create_material_expression(m, unreal.MaterialExpressionVertexColor, -500, 0)
    normal = M.create_material_expression(m, unreal.MaterialExpressionPixelNormalWS, -500, 200)
    depth = M.create_material_expression(m, unreal.MaterialExpressionPixelDepth, -500, 600)
    sun = M.create_material_expression(m, unreal.MaterialExpressionVectorParameter, -500, 400)
    sun.set_editor_property('parameter_name', 'SunDirection')
    sun.set_editor_property('default_value', unreal.LinearColor(-.646, -.173, .743, 0))
    shade = M.create_material_expression(m, unreal.MaterialExpressionCustom, -150, 0)
    shade.set_editor_property('code', 'float3 Base=lerp(C/12.92,pow((C+.055)/1.055,2.4),step(.04045,C)); float light=.72+.58*smoothstep(-1.,1.,dot(normalize(N),normalize(D))); return lerp(Base*light,float3(.64,.68,.76),saturate((Z-7000.)/220000.)*.5);')
    shade.set_editor_property('output_type', unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    shade.set_editor_property('inputs', _custom_inputs(['C', 'N', 'D', 'Z']))
    for source, name in [(color, 'C'), (normal, 'N'), (sun, 'D'), (depth, 'Z')]:
        M.connect_material_expressions(source, '', shade, name)
    M.connect_material_property(shade, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    M.recompile_material(m)
    return m


# --- Forest lake water (M_ForestLakeWater) -----------------------------------------------------------------------------

# donor RIPPLE, forest_lake_material.py 20-36: the nine-wavelet slope field, with its own UV and time inputs.
RIPPLE = '''
float2 p=float2(UV.x,1.-UV.y);
float2 sp=(p-float2(-90,235))/float2(34,23);
float ang=atan2(sp.y,sp.x);
float rim=length(sp)/(1+.045*sin(ang*3)+.035*cos(ang*5));
float calm=1-.5*smoothstep(.72,1.,rim);
float2 slope=0;
for(int i=0;i<7;i++) {
    float a=.61+i*1.9;
    float2 d=float2(cos(a),sin(a));
    float k=1.05*pow(1.55,(float)i);
    float foot=k*max(length(ddx(p)),length(ddy(p)));
    float amp=.075*pow(.85,(float)i)*exp(-foot*foot*.45);
    float warp=sin(dot(p,float2(-d.y,d.x))*k*.41+T*.35+i)*2.2;
    slope+=d*cos(dot(p,d)*k+warp+T*sqrt(3.4*k)+i*2.1)*amp;
}
'''


def forest_lake_water(package, reads):
    """donor create(), forest_lake_material.py 39-86, with RIPPLE (20-36): the jade shallows and the calm ripples, from
    the UV and the time, as three custom nodes (base colour, normal, roughness) and two constants."""
    M = unreal.MaterialEditingLibrary
    material = _material(package)
    M.delete_all_material_expressions(material)
    uv = M.create_material_expression(material, unreal.MaterialExpressionTextureCoordinate, -600, 100)
    time = M.create_material_expression(material, unreal.MaterialExpressionTime, -600, 300)

    def custom(code, prop, y, scalar=False):
        node = M.create_material_expression(material, unreal.MaterialExpressionCustom, -250, y)
        node.set_editor_property('code', code)
        node.set_editor_property('output_type', unreal.CustomMaterialOutputType.CMOT_FLOAT1 if scalar
                                 else unreal.CustomMaterialOutputType.CMOT_FLOAT3)
        node.set_editor_property('inputs', _custom_inputs(['UV', 'T']))
        M.connect_material_expressions(uv, '', node, 'UV')
        M.connect_material_expressions(time, '', node, 'T')
        M.connect_material_property(node, '', prop)

    custom(RIPPLE + '''
float shallows=smoothstep(.72,1.,rim);
float drift=sin(p.x*.21+p.y*.13+T*.06)*.5+sin(p.x*.09-p.y*.24-T*.045)*.5;
float3 deep=lerp(float3(.004,.043,.059),float3(.006,.055,.066),drift*.5+.5);
float3 base=lerp(deep,float3(.035,.13,.105),shallows);
float facing=dot(slope,float2(.26,-.97))/.12*calm;
base*=1+facing*.14;
// Fewer, softer highlights. The Sunburst target for this camera reads as calm sheltered water with
// a broad deep-to-shore structure and only a few soft glints; the shipped streaks were bright
// enough to make the surface look busy from the shore.
float glint=smoothstep(.74,1.15,facing)*calm;
base+=glint*float3(.012,.018,.021);
return base+drift*.004*float3(.1,.3,.25);
''', unreal.MaterialProperty.MP_BASE_COLOR, 0)
    custom(RIPPLE + 'return normalize(float3(-slope*calm,1));', unreal.MaterialProperty.MP_NORMAL, 200)
    custom(RIPPLE + '''
float fetch=sin(p.x*.16-p.y*.11+T*.05)*.5+.5;
float chop=saturate(length(slope)*3.);
return lerp(.18,.36,saturate(fetch*.5+chop*.6));
''', unreal.MaterialProperty.MP_ROUGHNESS, 400, scalar=True)
    for prop, value in [(unreal.MaterialProperty.MP_SPECULAR, .55), (unreal.MaterialProperty.MP_METALLIC, .08)]:
        node = M.create_material_expression(material, unreal.MaterialExpressionConstant, 200, 400)
        node.set_editor_property('r', value)
        M.connect_material_property(node, '', prop)
    material.set_editor_property('used_with_instanced_static_meshes', True)
    M.recompile_material(material)
    return material


# --- Village resident (M_VillageResident) ------------------------------------------------------------------------------

def village_resident(package, reads):
    """donor resident_material(), import_village.py 63-85: the cloth tint (a parameter), the emissive fill and the
    skeletal-mesh usage. The donor's save (line 84) is the importer's."""
    MEL = unreal.MaterialEditingLibrary
    m = _material(package)
    MEL.delete_all_material_expressions(m)
    vc = MEL.create_material_expression(m, unreal.MaterialExpressionVertexColor, -600, 0)
    tint = MEL.create_material_expression(m, unreal.MaterialExpressionVectorParameter, -600, 160)
    tint.set_editor_property('parameter_name', 'ClothTint')
    tint.set_editor_property('default_value', unreal.LinearColor(.07, .13, .2, 1))
    c = MEL.create_material_expression(m, unreal.MaterialExpressionCustom, -250, 0)
    c.set_editor_property('code', 'float3 L=lerp(C/12.92,pow((C+.055)/1.055,2.4),step(.04045,C)); float cloth=step(L.r*1.01,L.g)*step(L.b*1.25,L.g); return lerp(L,Tint*max(.4,L.g/.30),cloth);')
    c.set_editor_property('output_type', unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    c.set_editor_property('inputs', _custom_inputs(['C', 'Tint']))
    MEL.connect_material_expressions(vc, '', c, 'C')
    MEL.connect_material_expressions(tint, '', c, 'Tint')
    MEL.connect_material_property(c, '', unreal.MaterialProperty.MP_BASE_COLOR)
    fill = MEL.create_material_expression(m, unreal.MaterialExpressionMultiply, 0, 200)
    fill.set_editor_property('const_b', .25)
    MEL.connect_material_expressions(c, '', fill, 'A')
    MEL.connect_material_property(fill, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    for prop, value in [(unreal.MaterialProperty.MP_ROUGHNESS, 1.), (unreal.MaterialProperty.MP_SPECULAR, 0.)]:
        n = MEL.create_material_expression(m, unreal.MaterialExpressionConstant, 0, 350)
        n.set_editor_property('r', value)
        MEL.connect_material_property(n, '', prop)
    m.set_editor_property('used_with_skeletal_mesh', True)
    m.set_editor_property('two_sided', True)
    MEL.recompile_material(m)
    return m


# --- Cloud shadow (M_CloudShadow) --------------------------------------------------------------------------------------

def cloud_shadow(package, reads, *, texture):
    """donor cloud_shadow_material(tex), shared_materials.py 84-100: a light function that drifts the cloud mask over the
    world, its inverse as emissive. `texture` is the read package of the cloud mask (donor: T["T_cloudmask"])."""
    U = unreal
    m = _material(package)
    MEL = U.MaterialEditingLibrary
    MEL.delete_all_material_expressions(m)
    m.set_editor_property("material_domain", U.MaterialDomain.MD_LIGHT_FUNCTION)
    WP = _node(m, U.MaterialExpressionWorldPosition, -1200, 0)
    T = _node(m, U.MaterialExpressionTime, -1200, 300)
    xy = _node(m, U.MaterialExpressionComponentMask, -1000, 0, r=True, g=True, b=False, a=False)
    _link(WP, "", xy, "")
    sc = _node(m, U.MaterialExpressionMultiply, -800, 0, const_b=0.000022)
    _link(xy, "", sc, "A")
    tx = _node(m, U.MaterialExpressionMultiply, -1000, 300, const_b=0.0045)
    _link(T, "", tx, "A")
    ty = _node(m, U.MaterialExpressionMultiply, -1000, 400, const_b=0.0016)
    _link(T, "", ty, "A")
    tv = _node(m, U.MaterialExpressionAppendVector, -800, 350)
    _link(tx, "", tv, "A")
    _link(ty, "", tv, "B")
    uv = _node(m, U.MaterialExpressionAdd, -600, 150)
    _link(sc, "", uv, "A")
    _link(tv, "", uv, "B")
    ts = _node(m, U.MaterialExpressionTextureSample, -400, 100, texture=reads[texture])
    _link(uv, "", ts, "UVs")
    mul = _node(m, U.MaterialExpressionMultiply, -200, 100, const_b=0.4)
    _link(ts, "R", mul, "A")
    om = _node(m, U.MaterialExpressionOneMinus, -50, 100)
    _link(mul, "", om, "")
    MEL.connect_material_property(om, "", U.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.recompile_material(m)
    return m
