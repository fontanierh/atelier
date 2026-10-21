"""Targeted village + terrain import; preserves level lighting and both characters."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import hashlib,json
from pathlib import Path
import unreal
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
import atmosphere  # noqa: E402

ROOT = yori.OUT
OUT=ROOT/'village'
EAL=unreal.EditorAssetLibrary
MEL=unreal.MaterialEditingLibrary
AT=unreal.AssetToolsHelpers.get_asset_tools()


def material():
    value = EAL.load_asset('/Game/Japan/Materials/M_Village')
    assert value, 'M_Village is missing: build unreal.materials first'
    return value


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
    MEL.recompile_material(m);EAL.save_loaded_asset(m)


# The legacy FBX factory opens the Message Log whenever a new mesh has a build warning (nearly zero tangents, for
# instance), which crashes an editor running as a commandlet. An existing asset takes the reimport path instead, which
# only opens it on errors. So a mesh that does not exist yet is first created from a small placeholder that builds
# cleanly, then imported for real as a reimport (the factory points the asset at the new file first).
PLACEHOLDER=yori.OUT/'village'/'assets'/'Village_Sign.fbx'   # small, and builds without warnings


def import_mesh(path, dest, name, fresh_slots=False):
    """Village and legacy callers use the village's small import seed."""
    from mesh_import import import_mesh as import_fbx
    return import_fbx(path, dest, name, seed=PLACEHOLDER, fresh_slots=fresh_slots)


def main(terrain=True,assets=None):
    unreal.SystemLibrary.execute_console_command(None,'Interchange.FeatureFlags.Import.FBX 0')
    identity=json.loads((OUT/'build-identity.json').read_text())
    def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    for source,digest in identity['sources'].items():assert sha(yori.REGIONS/source)==digest,'Rebuild changed village source: '+source
    assert sha(ROOT/'world.json')==identity['world_sha256'],'Rebuild village for current layout'
    assert sha(ROOT/'heightmap.npy')==identity['heightmap_sha256'],'Rebuild village for current terrain'
    for filename,digest in identity['exports'].items():assert sha(OUT/'assets'/filename)==digest,'Incomplete village export: '+filename
    manifest=json.loads((OUT/'manifest.json').read_text())
    mat=material()
    resident_material()
    report=json.loads((OUT/'import-report.json').read_text()) if assets and (OUT/'import-report.json').exists() else {}
    for name,entry in manifest.items():
        if assets and name not in assets:continue
        mesh=import_mesh(OUT/'assets'/f'{name}.fbx','/Game/Japan/Assets',name)
        assert len(mesh.static_materials)==1,(name,'must have one draw material')
        mesh.set_material(0,mat)
        body=mesh.get_editor_property('body_setup');assert body
        body.set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE if name=='Village_Ground' else unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AND_COMPLEX)
        convex=len(body.get_editor_property("agg_geom").get_editor_property("convex_elems"))
        assert convex>=entry['collision_boxes'],(name,convex,entry['collision_boxes'])
        box=mesh.get_bounding_box()
        assert abs(box.max.z-entry['max'][2]*100)<.2,(name,'metres-to-centimetres conversion',box.max.z)
        EAL.save_loaded_asset(mesh)
        report[name]={'collision_hulls':convex,'materials':len(mesh.static_materials),'imported':True,'bounds_min':[mesh.get_bounding_box().min.x,mesh.get_bounding_box().min.y,mesh.get_bounding_box().min.z],'bounds_max':[mesh.get_bounding_box().max.x,mesh.get_bounding_box().max.y,mesh.get_bounding_box().max.z]}
    if terrain:
        mesh=import_mesh(ROOT/'terrain.fbx','/Game/Japan','Terrain')
        for i,slot in enumerate(mesh.static_materials):
            key=str(slot.get_editor_property('imported_material_slot_name')).split('.')[0]
            mat=EAL.load_asset('/Game/Japan/Materials/MI_'+key)
            assert mat,'Missing terrain material '+key
            mesh.set_material(i,mat)
        mesh.get_editor_property('body_setup').set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        EAL.save_loaded_asset(mesh)
    (OUT/'import-report.json').write_text(json.dumps(report,indent=2)+'\n')
    unreal.log('VILLAGE IMPORT COMPLETE')

if __name__=='__main__':main()
