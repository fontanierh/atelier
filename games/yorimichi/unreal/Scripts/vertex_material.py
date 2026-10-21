"""Shared vertex-colour material, owned by unreal.materials.

The village, vehicles and skate board load this same saved material.
"""
import unreal
import atmosphere

EAL = unreal.EditorAssetLibrary
MEL = unreal.MaterialEditingLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()


def material():
    path='/Game/Japan/Materials/M_Village'
    m=EAL.load_asset(path) if EAL.does_asset_exist(path) else None
    if not m:m=AT.create_asset('M_Village','/Game/Japan/Materials',unreal.Material,unreal.MaterialFactoryNew())
    MEL.delete_all_material_expressions(m)
    def node(cls,x,y,**kwargs):
        e=MEL.create_material_expression(m,cls,x,y)
        for k,v in kwargs.items():e.set_editor_property(k,v)
        return e
    def link(a,ao,b,bi):assert MEL.connect_material_expressions(a,ao,b,bi)
    vc=node(unreal.MaterialExpressionVertexColor,-650,0)
    linear=node(unreal.MaterialExpressionCustom,-430,0,
        code='return lerp(C/12.92,pow((C+0.055)/1.055,2.4),step(0.04045,C));',
        output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    arg=unreal.CustomInput();arg.set_editor_property('input_name','C');linear.set_editor_property('inputs',[arg])
    link(vc,'',linear,'C')
    rough=node(unreal.MaterialExpressionConstant,200,450,r=1.0)
    spec=node(unreal.MaterialExpressionConstant,200,550,r=0.0)
    MEL.connect_material_property(rough,'',unreal.MaterialProperty.MP_ROUGHNESS)
    MEL.connect_material_property(spec,'',unreal.MaterialProperty.MP_SPECULAR)
    # Only paper lights emit noticeably. A universal fill flattened the timber.
    fill=node(unreal.MaterialExpressionCustom,200,650,
        code='float lamp=step(.80,C.r)*step(.35,C.g)*step(C.g,.72)*step(C.b,.30); return C*(.06+lamp*.8);',
        output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    arg=unreal.CustomInput();arg.set_editor_property('input_name','C');fill.set_editor_property('inputs',[arg])
    link(linear,'',fill,'C')
    # aerial perspective shared with the sea and the land (atmosphere.py)
    base,glow=atmosphere.apply(m,linear,fill,x=420,y=0)
    assert MEL.connect_material_property(base,'',unreal.MaterialProperty.MP_BASE_COLOR)
    assert MEL.connect_material_property(glow,'',unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    wind=node(unreal.MaterialExpressionCustom,400,850,
        code='float phase=T*1.7+P.x*.002+P.y*.003; return float3(sin(phase)*2.2,cos(phase*.81)*1.3,sin(phase*1.3)*.4)*W*W;',
        output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    args=[]
    for key in ('T','P','W'):
        arg=unreal.CustomInput();arg.set_editor_property('input_name',key);args.append(arg)
    wind.set_editor_property('inputs',args)
    time=node(unreal.MaterialExpressionTime,-400,850)
    pos=node(unreal.MaterialExpressionWorldPosition,-400,950)
    link(time,'',wind,'T');link(pos,'',wind,'P');link(vc,'A',wind,'W')
    MEL.connect_material_property(wind,'',unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    m.set_editor_property('used_with_instanced_static_meshes',True)
    MEL.recompile_material(m);EAL.save_loaded_asset(m)
    return m
