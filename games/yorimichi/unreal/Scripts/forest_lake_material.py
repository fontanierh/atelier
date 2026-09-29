"""Opaque stylized lake: jade shallows and calm moving ripples, no heavy translucency.

The ripple field is a sum of nine crossing wavelets at incommensurate directions and
wavelengths, each one faded out as its wavelength approaches the pixel footprint, so the
surface never shows a repeated grid and the far half of the lake goes calm instead of
sparkling. The band runs from a 6 m swell down to 0.5 m ripples, which is what reads at this lake's
size; longer swells are too gentle to see across 60 m of water and shorter ones are eaten by
the footprint filter and then by the painterly pass.

UV on this mesh is the Blender world (x, y) in metres, dominant-plane projected, and Unreal
flips V on FBX import, so world y is `1 - UV.y`. The shipped material read UV.y directly, which
put the shore test 20 radii off the lake and made the whole surface take the shallow colour:
the depth gradient below only appears now that the flip is undone. UV is in world metres on this mesh, so the wave numbers below read directly as
radians per metre.
"""
import unreal

# Slope of the crossing wavelet sum. `SHORE` mirrors the base colour's shallows term so
# ripples ease off in the reeds; `FOOT` is the screen-space wavelength filter.
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


def create():
    E=unreal.EditorAssetLibrary;M=unreal.MaterialEditingLibrary;name='M_ForestLakeWater';path='/Game/Japan/Materials/'+name
    material=E.load_asset(path) if E.does_asset_exist(path) else unreal.AssetToolsHelpers.get_asset_tools().create_asset(name,'/Game/Japan/Materials',unreal.Material,unreal.MaterialFactoryNew())
    M.delete_all_material_expressions(material)
    uv=M.create_material_expression(material,unreal.MaterialExpressionTextureCoordinate,-600,100)
    time=M.create_material_expression(material,unreal.MaterialExpressionTime,-600,300)
    def custom(code,prop,y,scalar=False):
        node=M.create_material_expression(material,unreal.MaterialExpressionCustom,-250,y)
        node.set_editor_property('code',code)
        node.set_editor_property('output_type',unreal.CustomMaterialOutputType.CMOT_FLOAT1 if scalar else unreal.CustomMaterialOutputType.CMOT_FLOAT3)
        inputs=[]
        for name in ['UV','T']:
            pin=unreal.CustomInput();pin.set_editor_property('input_name',name);inputs.append(pin)
        node.set_editor_property('inputs',inputs)
        M.connect_material_expressions(uv,'',node,'UV');M.connect_material_expressions(time,'',node,'T');M.connect_material_property(node,'',prop)
    # Depth reads from the distance to the shore, with two broad drifting tints so the open
    # water is not a flat slab. The same wave slope that drives the normal also lightens the
    # crests here: an opaque lake under a flat sky barely shades from the normal alone, and
    # painting the swell into the albedo is what makes it read at 40 m without microdetail.
    custom(RIPPLE+'''
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
''',unreal.MaterialProperty.MP_BASE_COLOR,0)
    custom(RIPPLE+'return normalize(float3(-slope*calm,1));',unreal.MaterialProperty.MP_NORMAL,200)
    # Wind fetch: broad glassy lanes between rippled water, the same slope field driving the
    # gloss so the highlight sits where the surface is actually moving. Keeps a stylized sheen
    # without turning the lake into a mirror.
    custom(RIPPLE+'''
float fetch=sin(p.x*.16-p.y*.11+T*.05)*.5+.5;
float chop=saturate(length(slope)*3.);
return lerp(.18,.36,saturate(fetch*.5+chop*.6));
''',unreal.MaterialProperty.MP_ROUGHNESS,400,scalar=True)
    for prop,value in [(unreal.MaterialProperty.MP_SPECULAR,.55),(unreal.MaterialProperty.MP_METALLIC,.08)]:
        node=M.create_material_expression(material,unreal.MaterialExpressionConstant,200,400);node.set_editor_property('r',value);M.connect_material_property(node,'',prop)
    material.set_editor_property('used_with_instanced_static_meshes',True)
    M.recompile_material(material);E.save_loaded_asset(material);return material
