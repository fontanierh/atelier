"""The lenticular cap cloud's materials, /Game/CraterPark/Cloud/M_CraterCloud and M_CraterCloudVeil (ACraterCloud).

Unlit, translucent and two-sided: the game draws the shells of world/regions/craterpark/cloud.py with them, and sets
every parameter from craterpark/cloud.json, so the look is tuned there without rebuilding the material.

- Opacity: the shell's (near, far) opacity, chosen by where the camera is (q, its distance from the envelope's centre
  over the envelope's radii: near at q <= Q.x, far from Q.y out), softened at the shell's silhouette, cleared on
  surfaces nearer the camera than NearFade.x (opaque past NearFade.x + NearFade.y), faded into the ground it meets
  over Soft cm, and broken by long flat striations that drift slowly.
- Colour: sunlit tops Top, shaded undersides Under, and the island's distance haze (atmosphere.py) over both.
- The veil (M_CraterCloudVeil) blends a blurred copy of the scene behind it, tinted toward the cloud's colour by
  Tint (near, far): from inside, the world beyond the crest reads soft and hazy; from afar, the ramps blur away.
"""
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import unreal
import atmosphere

E = unreal.EditorAssetLibrary
M = unreal.MaterialEditingLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
FOLDER = '/Game/CraterPark/Cloud'
F1, F2, F3 = (unreal.CustomMaterialOutputType.CMOT_FLOAT1, unreal.CustomMaterialOutputType.CMOT_FLOAT2,
              unreal.CustomMaterialOutputType.CMOT_FLOAT3)
# The veil's blur: a centre tap, four at half the radius and four at the radius turned by 45 degrees (unit offsets).
TAPS = [(0., 0.)] + [(.5 * math.cos(i * math.pi / 2), .5 * math.sin(i * math.pi / 2)) for i in range(4)] + \
       [(math.cos(math.pi / 4 + i * math.pi / 2), math.sin(math.pi / 4 + i * math.pi / 2)) for i in range(4)]

# The camera term: w, 0 inside the envelope (q <= Q.x) to 1 from Q.y out (needs C, R, Q, Cam).
CAMERA = 'float q=length((Cam-C)/max(R,1.));float w=saturate((q-Q.x)/max(Q.y-Q.x,.001));w=w*w*(3.-2.*w);'
NOISE = '''
const float3 K=float3(127.1,311.7,74.7);
float nz=0.,amp=.65,tot=0.;
float3 sp=(WP+float3(Tm*Dr,Tm*Dr*.37,0.))/max(SZ,1.);
for (int o=0;o<2;o++)
{
    float3 p=sp*(1.+o*2.1)+o*17.3; float3 i=floor(p); float3 f=frac(p); f=f*f*(3.-2.*f);
    float4 h0=frac(sin(float4(dot(i,K),dot(i+float3(1,0,0),K),dot(i+float3(0,1,0),K),dot(i+float3(1,1,0),K)))*43758.5453);
    float4 h1=frac(sin(float4(dot(i+float3(0,0,1),K),dot(i+float3(1,0,1),K),dot(i+float3(0,1,1),K),dot(i+float3(1,1,1),K)))*43758.5453);
    float4 h=lerp(h0,h1,f.z); float2 e=lerp(h.xz,h.yw,f.x);
    nz+=amp*lerp(e.x,e.y,f.y); tot+=amp; amp*=.5;
}
nz/=tot;
'''
OPACITY = CAMERA + NOISE + '''
float a=lerp(O.x,O.y,w);
float3 n=normalize(N); float3 v=normalize(Cam-WP);
float edge=saturate(abs(dot(n,v))*3.); edge=edge*edge*(3.-2.*edge);
float nf=saturate((PD-NF.x)/max(NF.y,1.)); nf=nf*nf*(3.-2.*nf);
float soft=saturate((SD-PD)/max(S,1.));
return saturate(a*edge*nf*soft*(1.+St*(nz-.5)*2.));'''
COLOUR = ('float3 n=normalize(N);float sun=saturate(dot(n,normalize(L))*.5+.5);float up=saturate(n.z*.5+.5);'
          'float3 c=lerp(Un,Tp,saturate(.6*sun+.4*up));')
HAZE = f'float h={atmosphere.SHARE.replace("D", "PD")};return c*(1.-h)+{atmosphere.S.f3(atmosphere.COLOUR)}*h;'


def build(name, veil):
    path = f'{FOLDER}/{name}'
    mat = E.load_asset(path) if E.does_asset_exist(path) else AT.create_asset(name, FOLDER, unreal.Material,
                                                                                unreal.MaterialFactoryNew())
    M.delete_all_material_expressions(mat)
    mat.set_editor_property('blend_mode', unreal.BlendMode.BLEND_TRANSLUCENT)
    mat.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_UNLIT)
    mat.set_editor_property('two_sided', True)
    for key, value in (('use_translucency_vertex_fog', False), ('output_translucent_velocity', False)):
        try:
            mat.set_editor_property(key, value)
        except Exception:
            pass

    def node(cls, x, y, **properties):
        e = M.create_material_expression(mat, cls, x, y)
        for key, value in properties.items():
            e.set_editor_property(key, value)
        return e

    def link(a, out, b, into):
        assert M.connect_material_expressions(a, out, b, into), (name, into)

    def custom(x, y, code, output, inputs):
        e = node(unreal.MaterialExpressionCustom, x, y, code=code, output_type=output)
        args = []
        for key in inputs:
            arg = unreal.CustomInput(); arg.set_editor_property('input_name', key); args.append(arg)
        e.set_editor_property('inputs', args)
        for key, (source, out) in inputs.items():
            link(source, out, e, key)
        return e

    def vector(x, y, parameter, value):
        return node(unreal.MaterialExpressionVectorParameter, x, y, parameter_name=parameter,
                    default_value=unreal.LinearColor(*value, 1.) if len(value) == 3 else unreal.LinearColor(*value))

    def scalar(x, y, parameter, value):
        return node(unreal.MaterialExpressionScalarParameter, x, y, parameter_name=parameter, default_value=value)

    world = node(unreal.MaterialExpressionWorldPosition, -1600, 0)
    camera = node(unreal.MaterialExpressionCameraPositionWS, -1600, 100)
    normal = node(unreal.MaterialExpressionVertexNormalWS, -1600, 200)
    pixel = node(unreal.MaterialExpressionPixelDepth, -1600, 300)
    scene = node(unreal.MaterialExpressionSceneDepth, -1600, 400)
    time = node(unreal.MaterialExpressionTime, -1600, 500)
    # Placeholders near cloud.py's values: the game sets every one from cloud.json.
    centre = vector(-1400, 0, 'Centre', (86000., -244000., 76250.))
    radii = vector(-1400, 100, 'Radii', (86000., 86000., 16250.))
    q = vector(-1400, 200, 'Q', (1., 1.7, 0.))
    opacity = vector(-1400, 300, 'Opacity', (.07, .55, 0.))
    near = vector(-1400, 400, 'NearFade', (4000., 22000., 0.))
    soft = scalar(-1400, 500, 'Soft', 4500.)
    size = vector(-1400, 600, 'StriationSize', (26000., 26000., 2200.))
    striation = scalar(-1400, 700, 'Striation', .35)
    drift = scalar(-1400, 800, 'Drift', 250.)
    top = vector(-1400, 900, 'Top', (.93, .92, .90))
    under = vector(-1400, 1000, 'Under', (.56, .60, .74))
    sun = vector(-1400, 1100, 'SunDir', (-.579, .334, .743))
    cam_in = {'Cam': (camera, ''), 'C': (centre, ''), 'R': (radii, ''), 'Q': (q, '')}
    alpha = custom(-900, 300, OPACITY, F1, {**cam_in, 'WP': (world, ''), 'N': (normal, ''), 'PD': (pixel, ''),
                                             'SD': (scene, ''), 'Tm': (time, ''), 'O': (opacity, ''), 'NF': (near, ''),
                                             'S': (soft, ''), 'SZ': (size, ''), 'St': (striation, ''),
                                             'Dr': (drift, '')})
    colour_in = {'N': (normal, ''), 'L': (sun, ''), 'Un': (under, ''), 'Tp': (top, ''), 'PD': (pixel, '')}
    if not veil:
        glow = custom(-900, 900, COLOUR + HAZE, F3, colour_in)
    else:
        # The blur: SceneColor taps at offsets (a fraction of the screen, round on any aspect), averaged, then tinted
        # toward the cloud's colour by Tint (near, far) through the same camera term.
        blur = scalar(-1400, 1300, 'Blur', .01)
        tint = vector(-1400, 1400, 'Tint', (.10, .55, 0.))
        view = node(unreal.MaterialExpressionViewSize, -1600, 1300)
        reach = custom(-1200, 1300, 'return float2(B,B*V.x/max(V.y,1.));', F2, {'B': (blur, ''), 'V': (view, '')})
        # Each tap counts only where the scene there lies behind the veil (its depth past this pixel's), so the
        # ramps and riders in front of it do not bleed into the blurred world round them.
        taps = {'PD': (pixel, '')}
        for i, (dx, dy) in enumerate(TAPS):
            offset = node(unreal.MaterialExpressionMultiply, -1000, 1300 + 180 * i)
            link(node(unreal.MaterialExpressionConstant2Vector, -1150, 1300 + 180 * i, r=dx, g=dy), '', offset, 'A')
            link(reach, '', offset, 'B')
            mode = unreal.MaterialSceneAttributeInputMode.OFFSET_FRACTION
            colour = node(unreal.MaterialExpressionSceneColor, -850, 1300 + 180 * i, input_mode=mode)
            depth = node(unreal.MaterialExpressionSceneDepth, -850, 1390 + 180 * i, input_mode=mode)
            # The input pin is named after the input mode (UMaterialExpressionSceneColor::GetInputName).
            for sample in (colour, depth):
                assert any(M.connect_material_expressions(offset, '', sample, pin)
                           for pin in ('OffsetFraction', 'Offset Fraction', 'Input', '')), (name, 'scene tap')
            taps[f'B{i}'] = (colour, ''); taps[f'Z{i}'] = (depth, '')
        n = len(TAPS)
        average = custom(-650, 1300, 'float3 s=B0;float k=1.;' + ''.join(
            f'{{float u=step(PD,Z{i});s+=B{i}*u;k+=u;}}' for i in range(1, n)) + 'return s/k;', F3, taps)
        glow = custom(-900, 900, CAMERA + COLOUR + 'float3 cloud=0;{' + HAZE.replace('return ', 'cloud=') + '}'
                      'return lerp(Bl,cloud,saturate(lerp(Ti.x,Ti.y,w)));', F3,
                      {**colour_in, **cam_in, 'Bl': (average, ''), 'Ti': (tint, '')})
    assert M.connect_material_property(glow, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    assert M.connect_material_property(alpha, '', unreal.MaterialProperty.MP_OPACITY)
    M.recompile_material(mat)
    assert E.save_loaded_asset(mat, False), path
    return mat


def main():
    E.make_directory(FOLDER)
    build('M_CraterCloud', False)
    build('M_CraterCloudVeil', True)
    unreal.log('CRATER CLOUD MATERIAL COMPLETE')
    print('CRATER CLOUD MATERIAL COMPLETE', flush=True)


if __name__ == '__main__':
    main()
