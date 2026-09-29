"""Targeted village + terrain import; preserves level lighting and both characters."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import hashlib,json
from pathlib import Path
import unreal

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
    depth=node(unreal.MaterialExpressionPixelDepth,-650,250)
    sub=node(unreal.MaterialExpressionSubtract,-450,250,const_b=7000.)
    div=node(unreal.MaterialExpressionDivide,-280,250,const_b=220000.)
    sat=node(unreal.MaterialExpressionSaturate,-120,250)
    amp=node(unreal.MaterialExpressionMultiply,40,250,const_b=.5)
    fog=node(unreal.MaterialExpressionConstant3Vector,-280,420,constant=unreal.LinearColor(.64,.68,.76,1))
    mix=node(unreal.MaterialExpressionLinearInterpolate,200,0)
    link(depth,'',sub,'A');link(sub,'',div,'A');link(div,'',sat,'');link(sat,'',amp,'A')
    linear=node(unreal.MaterialExpressionCustom,-430,0,
        code='return lerp(C/12.92,pow((C+0.055)/1.055,2.4),step(0.04045,C));',
        output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    arg=unreal.CustomInput();arg.set_editor_property('input_name','C');linear.set_editor_property('inputs',[arg])
    link(vc,'',linear,'C');link(linear,'',mix,'A');link(fog,'',mix,'B');link(amp,'',mix,'Alpha')
    assert MEL.connect_material_property(mix,'',unreal.MaterialProperty.MP_BASE_COLOR)
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
    MEL.connect_material_property(fill,'',unreal.MaterialProperty.MP_EMISSIVE_COLOR)
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


def import_mesh(path,dest,name):
    if not EAL.does_asset_exist(dest+'/'+name) and Path(path).resolve()!=PLACEHOLDER.resolve():
        _import_mesh(PLACEHOLDER,dest,name)
    return _import_mesh(path,dest,name)


def _import_mesh(path,dest,name):
    task=unreal.AssetImportTask()
    task.filename=str(path);task.destination_path=dest;task.destination_name=name
    task.automated=True;task.replace_existing=True;task.replace_existing_settings=True;task.save=True
    ui=unreal.FbxImportUI()
    ui.automated_import_should_detect_type=False
    ui.import_mesh=True;ui.import_materials=False;ui.import_textures=False;ui.import_animations=False
    ui.import_as_skeletal=False;ui.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH
    d=ui.static_mesh_import_data
    for k,v in dict(combine_meshes=True,generate_lightmap_u_vs=False,auto_generate_collision=False,
        convert_scene=True,convert_scene_unit=True,import_uniform_scale=1.0,build_nanite=False,one_convex_hull_per_ucx=True,
        vertex_color_import_option=unreal.VertexColorImportOption.REPLACE,
        normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS).items():d.set_editor_property(k,v)
    # Legacy reimport reads the stored import-data object before task options.
    # Keep these in sync so unit scale and vertex colours update on every rebuild.
    existing=EAL.load_asset(dest+'/'+name) if EAL.does_asset_exist(dest+'/'+name) else None
    if existing:
        prior=existing.get_editor_property('asset_import_data')
        if isinstance(prior,unreal.FbxStaticMeshImportData):
            for key in ('combine_meshes','generate_lightmap_u_vs','auto_generate_collision','convert_scene',
                        'convert_scene_unit','import_uniform_scale','one_convex_hull_per_ucx',
                        'vertex_color_import_option','normal_import_method'):
                prior.set_editor_property(key,d.get_editor_property(key))
    task.options=ui;AT.import_asset_tasks([task])
    mesh=EAL.load_asset(dest+'/'+name)
    assert mesh and task.imported_object_paths,'FBX import failed: '+name
    return mesh


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
