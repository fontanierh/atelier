"""Import the south-west detour props (village kit, coconut stand, temple, island) into /Game/Japan/Assets with the
village material, and re-import the revised terrain. Level lighting, characters and preferences are untouched."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import json,sys
from pathlib import Path
import unreal
ROOT = yori.OUT;OUT=ROOT/'southwest'
sys.path.insert(0,str(Path(__file__).resolve().parent))
import import_village as V
import sea_look
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
    """M_Sea: the open sea (sea_look.py). Its colour is emissive: a deep blue-teal body, lighter teal in the shallows,
    a Fresnel reflection of the painted dome on world-space wave normals, white surf where the water meets anything
    (the scene depth behind the surface) and a haze toward a colour a little darker than the dome's horizon. The
    engine lights it for sun glints only (black base colour, specular .02), so its grazing reflection of the sky
    light's capture no longer turns the whole sea the sky's colour."""
    U=unreal;m=_create('M_Sea',U.Material,U.MaterialFactoryNew());MEL.delete_all_material_expressions(m)
    F1=U.CustomMaterialOutputType.CMOT_FLOAT1;F3=U.CustomMaterialOutputType.CMOT_FLOAT3
    def link(a,b,key):assert MEL.connect_material_expressions(a,'',b,key),key
    def prop(n,p):assert MEL.connect_material_property(n,'',p),p
    def custom(code,inputs,x,y,kind=F3):
        n=_node(m,U.MaterialExpressionCustom,x,y,code=code,output_type=kind)
        args=[]
        for key,_ in inputs:
            a=U.CustomInput();a.set_editor_property('input_name',key);args.append(a)
        n.set_editor_property('inputs',args)
        for key,src in inputs:link(src,n,key)
        return n
    po=_node(m,U.MaterialExpressionWorldPosition,-900,0);ti=_node(m,U.MaterialExpressionTime,-900,150)
    cam=_node(m,U.MaterialExpressionCameraVectorWS,-900,300);pd=_node(m,U.MaterialExpressionPixelDepth,-900,450)
    # scene depth is only readable from translucent materials: translucent, fully opaque
    sd=_node(m,U.MaterialExpressionSceneDepth,-900,600)
    behind=_node(m,U.MaterialExpressionSubtract,-700,550);link(sd,behind,'A');link(pd,behind,'B')
    waves=custom(sea_look.WAVES,[('P',po),('T',ti)],-600,0)
    prop(custom(sea_look.NORMAL,[('W',waves)],-250,0),U.MaterialProperty.MP_NORMAL)
    m.set_editor_property('tangent_space_normal',False)
    look=custom(sea_look.LOOK,[('W',waves),('V',cam),('D',pd),('L',behind),('P',po),('T',ti)],-250,250)
    prop(look,U.MaterialProperty.MP_EMISSIVE_COLOR)
    prop(_node(m,U.MaterialExpressionConstant3Vector,-250,500,constant=U.LinearColor(*sea_look.BASE,1.0)),U.MaterialProperty.MP_BASE_COLOR)
    prop(_node(m,U.MaterialExpressionConstant,-250,600,r=sea_look.ROUGHNESS),U.MaterialProperty.MP_ROUGHNESS)
    prop(custom('return %s*(1-H);'%sea_look.num(sea_look.SPECULAR),[('H',custom(sea_look.HAZE,[('D',pd)],-600,700,F1))],-250,700,F1),
         U.MaterialProperty.MP_SPECULAR)
    prop(_node(m,U.MaterialExpressionConstant,-250,800,r=1.0),U.MaterialProperty.MP_OPACITY)
    m.set_editor_property('blend_mode',U.BlendMode.BLEND_TRANSLUCENT)
    # forward shaded: the sun's specular on the wave normals gives the glints
    m.set_editor_property('translucency_lighting_mode',U.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
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
    if sea.get_bounding_box().max.x<100000:
        # The world setup imports the sea through Interchange, and the first FBX reimport over that import data skips
        # the unit conversion (a sea 100 times too small); the second finds FBX data to update and imports in metres.
        sea=V.import_mesh(ROOT/'assets/Sea.fbx','/Game/Japan/Assets','Sea')
    assert sea.get_bounding_box().max.x>100000,'Sea imported at the wrong scale'
    sea.set_material(0,sea_material())
    EAL.save_loaded_asset(sea)
    (OUT/'import-report.json').write_text(json.dumps(report,indent=2));unreal.log('SOUTHWEST IMPORT COMPLETE %d meshes'%len(report))
if __name__=='__main__':main()
