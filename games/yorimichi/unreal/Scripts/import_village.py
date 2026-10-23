"""Complete independent Village owner; island map and terrain have their own owner."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import hashlib,json
from pathlib import Path
import unreal
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
_sys.path.insert(0, str(yori.GAME))
import atmosphere  # noqa: E402

ROOT = yori.OUT
OUT=ROOT/'village'
EAL=unreal.EditorAssetLibrary
MEL=unreal.MaterialEditingLibrary
AT=unreal.AssetToolsHelpers.get_asset_tools()


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
    MEL.recompile_material(m);assert EAL.save_loaded_asset(m), 'Village material save failed'
    return m


def resident_material():
    path='/Game/Japan/Materials/M_VillageResident'
    m=EAL.load_asset(path) if EAL.does_asset_exist(path) else AT.create_asset('M_VillageResident','/Game/Japan/Materials',unreal.Material,unreal.MaterialFactoryNew())
    MEL.delete_all_material_expressions(m)
    vc=MEL.create_material_expression(m,unreal.MaterialExpressionVertexColor,-600,0)
    tint=MEL.create_material_expression(m,unreal.MaterialExpressionVectorParameter,-600,160)
    tint.set_editor_property('parameter_name','ClothTint');tint.set_editor_property('default_value',unreal.LinearColor(.07,.13,.2,1))
    c=MEL.create_material_expression(m,unreal.MaterialExpressionCustom,-250,0)
    c.set_editor_property('code','float3 L=lerp(C/12.92,pow((C+.055)/1.055,2.4),step(.04045,C)); float cloth=step(L.r*1.01,L.g)*step(L.b*1.25,L.g); return lerp(L,Tint*max(.4,L.g/.30),cloth);')
    c.set_editor_property('output_type',unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    args=[]
    for key in ('C','Tint'):
        a=unreal.CustomInput();a.set_editor_property('input_name',key);args.append(a)
    c.set_editor_property('inputs',args)
    MEL.connect_material_expressions(vc,'',c,'C');MEL.connect_material_expressions(tint,'',c,'Tint')
    MEL.connect_material_property(c,'',unreal.MaterialProperty.MP_BASE_COLOR)
    fill=MEL.create_material_expression(m,unreal.MaterialExpressionMultiply,0,200);fill.set_editor_property('const_b',.25)
    MEL.connect_material_expressions(c,'',fill,'A');MEL.connect_material_property(fill,'',unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    for prop,value in [(unreal.MaterialProperty.MP_ROUGHNESS,1.),(unreal.MaterialProperty.MP_SPECULAR,0.)]:
        n=MEL.create_material_expression(m,unreal.MaterialExpressionConstant,0,350);n.set_editor_property('r',value);MEL.connect_material_property(n,'',prop)
    m.set_editor_property('used_with_skeletal_mesh',True);m.set_editor_property('two_sided',True)
    MEL.recompile_material(m);assert EAL.save_loaded_asset(m), 'Village resident material save failed'
    return m


# Compatibility only: mesh_import accepts the old seed keyword without reading it.
# Migration and final source passes always use the requested actual FBX bytes.
PLACEHOLDER=yori.OUT/'village'/'assets'/'Village_Sign.fbx'   # small, and builds without warnings


def import_mesh(path, dest, name, fresh_slots=False):
    """Village and legacy callers use the village's small import seed."""
    from mesh_import import import_mesh as import_fbx
    return import_fbx(path, dest, name, seed=PLACEHOLDER, fresh_slots=fresh_slots)


def main(terrain=False, assets=None):
    """Own the complete current Village; island terrain belongs to unreal.island.

    The historical terrain keyword remains accepted without recreating a combined
    parent. A partial diagnostic must call the bounded receiver explicitly and
    cannot certify or retire the full production owner.
    """
    if type(terrain) is not bool or assets is not None:
        raise ValueError('Village owner requires its complete explicit current roster')
    from village_atomic_products import read
    from import_village_atomic import receive, retire
    # Refuse incomplete source/placement membership before changing any native asset.
    groups = read(ROOT)
    runtime = json.loads((OUT / 'pieces.json').read_text())
    if (runtime.get('schema') != 1 or runtime.get('complete') is not True
            or set(runtime.get('parents', {})) != set(groups)):
        raise ValueError('Incomplete Village runtime placement inventory')
    members = {parent: group['assets'] for parent, group in runtime['parents'].items()}
    expected = {parent: ['/Game/Experiments/VillageAtomic/v1_atomic/' + row['name']
                         for row in group['pieces']] for parent, group in groups.items()}
    if members != expected:
        raise ValueError('Village source/runtime membership differs')
    material()
    resident_material()
    received = receive(ROOT)
    retire(received, runtime_members=members)
    unreal.log('VILLAGE IMPORT COMPLETE')

if __name__=='__main__':main()
