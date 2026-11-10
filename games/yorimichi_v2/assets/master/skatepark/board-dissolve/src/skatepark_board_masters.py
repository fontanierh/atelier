"""Skateboard dissolve master builder: M_BoardDissolve of the skatepark_board family.

board_dissolve is the module body of the donor generator games/yorimichi/unreal/Scripts/board_dissolve_material.py at the V2
source baseline (docs/DECISIONS.md D01): lines 1-95 of that file, sha256 a201e90d5dc6ccb9fb3f3b4eda753e946d0992a8994518daa2c8259368adaa2e.
The donor ran this body on import; here it is wrapped in one function, in the donor's order, with its constants and positions
unchanged. The graph is M_Village's vertex-colour look, masked by two octaves of value noise in the part's local space against
the scalar parameter Dissolve, with a warm glow along the edge.

Three things move out of the body: the folder creation (donor line 14; the material's own create does that), the save (donor
line 94; the importer saves the rebuild it accepts) and the log line (donor line 95). The material itself is created or reused
by _material, as in the other builders. Nothing runs at import: the module is functions only, so it imports without the
Unreal editor, where `unreal` is None.
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


def board_dissolve(package, reads):
    """donor board_dissolve_material.py lines 1-95, the module body in one function. Takes no reads and no arguments: the
    graph's constants are the donor's, and the Dissolve parameter is a scalar with the donor's default of 0."""
    M = unreal.MaterialEditingLibrary
    mat = _material(package)
    M.delete_all_material_expressions(mat)
    mat.set_editor_property('blend_mode', unreal.BlendMode.BLEND_MASKED)
    mat.set_editor_property('opacity_mask_clip_value', .5)      # the mask below is the noise's margin + .5

    def node(cls, x, y, **properties):
        e = M.create_material_expression(mat, cls, x, y)
        for key, value in properties.items():
            e.set_editor_property(key, value)
        return e

    def link(a, out, b, into):
        assert M.connect_material_expressions(a, out, b, into), (a, out, b, into)

    def custom(x, y, code, output, names):
        e = node(unreal.MaterialExpressionCustom, x, y, code=code, output_type=output)
        inputs = []
        for name in names:
            arg = unreal.CustomInput()
            arg.set_editor_property('input_name', name)
            inputs.append(arg)
        e.set_editor_property('inputs', inputs)
        return e

    # M_Village's look (import_village.py): sRGB vertex colours made linear, the distance haze, roughness 1, no specular
    # and a 0.06 fill.
    vc = node(unreal.MaterialExpressionVertexColor, -900, 0)
    linear = custom(-650, 0, 'return lerp(C/12.92,pow((C+0.055)/1.055,2.4),step(0.04045,C));',
                    unreal.CustomMaterialOutputType.CMOT_FLOAT3, ['C'])
    link(vc, '', linear, 'C')
    depth = node(unreal.MaterialExpressionPixelDepth, -900, 250)
    haze = custom(-650, 250, 'return saturate((D-7000.)/220000.)*.5;', unreal.CustomMaterialOutputType.CMOT_FLOAT1, ['D'])
    link(depth, '', haze, 'D')
    fog = node(unreal.MaterialExpressionConstant3Vector, -650, 400, constant=unreal.LinearColor(.64, .68, .76, 1))
    mix = node(unreal.MaterialExpressionLinearInterpolate, -350, 0)
    link(linear, '', mix, 'A'); link(fog, '', mix, 'B'); link(haze, '', mix, 'Alpha')
    assert M.connect_material_property(mix, '', unreal.MaterialProperty.MP_BASE_COLOR)
    for value, prop in [(1., unreal.MaterialProperty.MP_ROUGHNESS), (0., unreal.MaterialProperty.MP_SPECULAR)]:
        assert M.connect_material_property(node(unreal.MaterialExpressionConstant, -350, 600, r=value), '', prop)

    # The dissolve: two octaves of value noise in the part's local space (it moves with the board), against Dissolve.
    if hasattr(unreal, 'MaterialExpressionLocalPosition'):
        position = node(unreal.MaterialExpressionLocalPosition, -1200, 700)
    else:
        world = node(unreal.MaterialExpressionWorldPosition, -1400, 700)
        position = node(unreal.MaterialExpressionTransformPosition, -1200, 700,
                        transform_source_type=unreal.MaterialPositionTransformSource.TRANSFORMPOSSOURCE_WORLD,
                        transform_type=unreal.MaterialPositionTransformSource.TRANSFORMPOSSOURCE_LOCAL)
        link(world, '', position, '')
    noise = custom(-950, 700, '''
const float3 K=float3(127.1,311.7,74.7);
float n=0,a=.65,t=0;
for (int o=0;o<2;o++)
{
    float3 p=P*(.15*(1+o*1.9)); float3 i=floor(p); float3 f=frac(p); f=f*f*(3-2*f);
    float4 h0=frac(sin(float4(dot(i,K),dot(i+float3(1,0,0),K),dot(i+float3(0,1,0),K),dot(i+float3(1,1,0),K)))*43758.5453);
    float4 h1=frac(sin(float4(dot(i+float3(0,0,1),K),dot(i+float3(1,0,1),K),dot(i+float3(0,1,1),K),dot(i+float3(1,1,1),K)))*43758.5453);
    float4 h=lerp(h0,h1,f.z); float2 e=lerp(h.xz,h.yw,f.x);
    n+=a*lerp(e.x,e.y,f.y); t+=a; a*=.5;
}
return n/t;''', unreal.CustomMaterialOutputType.CMOT_FLOAT1, ['P'])
    link(position, '', noise, 'P')
    dissolve = node(unreal.MaterialExpressionScalarParameter, -950, 950, parameter_name='Dissolve', default_value=0.)
    mask = custom(-650, 800, 'return N-(D*1.1-.05)+.5;', unreal.CustomMaterialOutputType.CMOT_FLOAT1, ['N', 'D'])
    link(noise, '', mask, 'N'); link(dissolve, '', mask, 'D')
    assert M.connect_material_property(mask, '', unreal.MaterialProperty.MP_OPACITY_MASK)

    # The fill, and the warm edge the dissolve eats along.
    glow = custom(-350, 800, 'return C*.06+float3(2.5,2.2,1.6)*(1-saturate((Mask-.5)/.06))*step(.001,D);',
                  unreal.CustomMaterialOutputType.CMOT_FLOAT3, ['C', 'Mask', 'D'])
    link(linear, '', glow, 'C'); link(mask, '', glow, 'Mask'); link(dissolve, '', glow, 'D')
    assert M.connect_material_property(glow, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)

    M.recompile_material(mat)
    return mat
