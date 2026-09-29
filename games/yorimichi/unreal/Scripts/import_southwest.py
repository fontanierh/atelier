"""Import the south-west detour props (village kit, coconut stand, temple, island) into /Game/Japan/Assets with the
village material, and re-import the revised terrain. Level lighting, characters and preferences are untouched."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import json,sys
from pathlib import Path
import unreal
ROOT = yori.OUT;OUT=ROOT/'southwest'
sys.path.insert(0,str(Path(__file__).resolve().parent))
import import_village as V
EAL=unreal.EditorAssetLibrary

MEL=unreal.MaterialEditingLibrary
def _node(m,cls,x,y,**props):
    n=MEL.create_material_expression(m,cls,x,y)
    for k,v in props.items():n.set_editor_property(k,v)
    return n
def _link(a,ao,b,bi):MEL.connect_material_expressions(a,ao,b,bi)
def _create(name,cls,factory):
    # reuse an existing asset (deleting one that the terrain or sea still references fails); the caller resets it
    path='/Game/Japan/Materials/'+name
    if EAL.does_asset_exist(path):return EAL.load_asset(path)
    return unreal.AssetToolsHelpers.get_asset_tools().create_asset(name,'/Game/Japan/Materials',cls,factory)
def sand_material():
    """MI_Sand: the painted master with the white texture and a warm pale-sand tint (linear values stay dark: exposure lifts them)."""
    parent=EAL.load_asset('/Game/Japan/Materials/M_Painted');white=EAL.load_asset('/Game/Japan/Textures/T_white')
    mi=_create('MI_Sand',unreal.MaterialInstanceConstant,unreal.MaterialInstanceConstantFactoryNew())
    MEL.set_material_instance_parent(mi,parent);MEL.set_material_instance_texture_parameter_value(mi,'Tex',white)
    MEL.set_material_instance_vector_parameter_value(mi,'Tint',unreal.LinearColor(0.24,0.185,0.10,1.0))
    MEL.update_material_instance(mi);EAL.save_loaded_asset(mi);return mi
def sea_material():
    """M_Sea: flat painterly water. Deep blue-teal base that turns lighter teal where the water is shallow (scene depth
    behind the surface), a white foam band right at the shoreline, low roughness for a sky sheen, and the same
    aerial-perspective haze as the painted master so the horizon softens."""
    U=unreal;m=_create('M_Sea',U.Material,U.MaterialFactoryNew());MEL.delete_all_material_expressions(m)
    deep=_node(m,U.MaterialExpressionConstant3Vector,-900,-100,constant=U.LinearColor(0.006,0.030,0.078,1))
    shallow=_node(m,U.MaterialExpressionConstant3Vector,-900,100,constant=U.LinearColor(0.022,0.115,0.135,1))
    depth=_node(m,U.MaterialExpressionDepthFade,-900,300);depth.set_editor_property('fade_distance_default',900.0)
    inv=_node(m,U.MaterialExpressionOneMinus,-700,300);_link(depth,'',inv,'')
    col=_node(m,U.MaterialExpressionLinearInterpolate,-550,0);_link(deep,'',col,'A');_link(shallow,'',col,'B');_link(inv,'',col,'Alpha')
    foamd=_node(m,U.MaterialExpressionDepthFade,-900,500);foamd.set_editor_property('fade_distance_default',12.0)
    foam=_node(m,U.MaterialExpressionOneMinus,-700,500);_link(foamd,'',foam,'')
    foamc=_node(m,U.MaterialExpressionConstant3Vector,-700,650,constant=U.LinearColor(0.55,0.58,0.58,1))
    col2=_node(m,U.MaterialExpressionLinearInterpolate,-350,100);_link(col,'',col2,'A');_link(foamc,'',col2,'B');_link(foam,'',col2,'Alpha')
    pd=_node(m,U.MaterialExpressionPixelDepth,-350,550)
    hz0=_node(m,U.MaterialExpressionSubtract,-200,550,const_b=7000.0);_link(pd,'',hz0,'A')
    hz1=_node(m,U.MaterialExpressionDivide,-80,550,const_b=220000.0);_link(hz0,'',hz1,'A')
    hz2=_node(m,U.MaterialExpressionSaturate,40,550);_link(hz1,'',hz2,'')
    hz3=_node(m,U.MaterialExpressionMultiply,140,550,const_b=0.35);_link(hz2,'',hz3,'A')
    hcol=_node(m,U.MaterialExpressionConstant3Vector,-80,700,constant=U.LinearColor(0.60,0.66,0.78,1.0))
    lerp=_node(m,U.MaterialExpressionLinearInterpolate,260,300);_link(col2,'',lerp,'A');_link(hcol,'',lerp,'B');_link(hz3,'',lerp,'Alpha')
    MEL.connect_material_property(lerp,'',U.MaterialProperty.MP_BASE_COLOR)
    rough=_node(m,U.MaterialExpressionConstant,260,450,r=0.32);MEL.connect_material_property(rough,'',U.MaterialProperty.MP_ROUGHNESS)
    spec=_node(m,U.MaterialExpressionConstant,260,520,r=0.6);MEL.connect_material_property(spec,'',U.MaterialProperty.MP_SPECULAR)
    # scene depth is only readable from translucent materials: translucent, fully opaque, forward shaded for the specular sheen
    m.set_editor_property('blend_mode',U.BlendMode.BLEND_TRANSLUCENT)
    m.set_editor_property('translucency_lighting_mode',U.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
    op=_node(m,U.MaterialExpressionConstant,260,600,r=1.0);MEL.connect_material_property(op,'',U.MaterialProperty.MP_OPACITY)
    # Low, travelling ripples keep the broad sea calm without looking like a solid plane.
    normal=_node(m,U.MaterialExpressionCustom,450,800,
        code='float a=T*.85+P.x*.022+P.y*.015; float b=T*1.25-P.x*.017+P.y*.027; float fade=1/(1+pow(D/4500,2)); return normalize(float3((.025*cos(a)+.012*cos(b))*fade,(.018*cos(a)-.015*cos(b))*fade,1));',
        output_type=U.CustomMaterialOutputType.CMOT_FLOAT3)
    args=[]
    for key in ('T','P','D'):
        a=U.CustomInput();a.set_editor_property('input_name',key);args.append(a)
    normal.set_editor_property('inputs',args)
    ti=_node(m,U.MaterialExpressionTime,0,800);po=_node(m,U.MaterialExpressionWorldPosition,0,950)
    _link(ti,'',normal,'T');_link(po,'',normal,'P');_link(pd,'',normal,'D');MEL.connect_material_property(normal,'',U.MaterialProperty.MP_NORMAL)
    MEL.recompile_material(m);EAL.save_loaded_asset(m);return m
def main():
    unreal.SystemLibrary.execute_console_command(None,'Interchange.FeatureFlags.Import.FBX 0')
    manifest=json.loads((OUT/'manifest.json').read_text());mat=V.material();report={}
    for fbx in sorted((OUT/'fbx').glob('*.fbx')):
        name=fbx.stem;mesh=V.import_mesh(fbx,'/Game/Japan/Assets',name)
        mesh.set_material(0,mat)
        body=mesh.get_editor_property('body_setup')
        if body:body.set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        EAL.save_loaded_asset(mesh);report[name]=mesh.get_path_name();unreal.log('SOUTHWEST imported '+name)
    # terrain: same path as the world setup
    terrain=V.import_mesh(ROOT/'terrain.fbx','/Game/Japan','Terrain')
    sand_material()
    for i,slot in enumerate(terrain.static_materials):
        key=str(slot.get_editor_property('imported_material_slot_name')).split('.')[0]
        m=EAL.load_asset('/Game/Japan/Materials/MI_'+key);assert m,'Missing terrain material '+key
        terrain.set_material(i,m)
    body=terrain.get_editor_property('body_setup')
    if body:body.set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    EAL.save_loaded_asset(terrain)
    # the sea plane (re-exported by build_terrain): a real water material instead of the painted tile
    sea=V.import_mesh(ROOT/'assets/Sea.fbx','/Game/Japan/Assets','Sea')
    sea.set_material(0,sea_material())
    EAL.save_loaded_asset(sea)
    (OUT/'import-report.json').write_text(json.dumps(report,indent=2));unreal.log('SOUTHWEST IMPORT COMPLETE %d meshes'%len(report))
if __name__=='__main__':main()
