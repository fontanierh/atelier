"""Import the verified Cairo FBX/PBR/morph deliverable into its own package."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import json
import sys
from pathlib import Path
import unreal as U
sys.path.insert(0,str(Path(__file__).resolve().parent))
import animation_compression
ROOT = yori.OUT
OUT=ROOT/'cairo'
CONFIG=json.loads((OUT/'export.json').read_text())
DEST='/Game/Cairo'
E=U.EditorAssetLibrary
AT=U.AssetToolsHelpers.get_asset_tools()
M=U.MaterialEditingLibrary
A=U.AnimationLibrary
E.make_directory(DEST)
def asset(name,cls,factory):
    path=DEST+'/'+name
    return E.load_asset(path) if E.does_asset_exist(path) else AT.create_asset(name,DEST,cls,factory)

materials={}
for name,cfg in CONFIG['materials'].items():
    mat=asset(name,U.Material,U.MaterialFactoryNew())
    M.delete_all_material_expressions(mat)
    # Opaque until see_through.py masks it again: the opacity mask may still point at its deleted nodes.
    mat.set_editor_property('blend_mode',U.BlendMode.BLEND_OPAQUE)
    mat.set_editor_property('two_sided',cfg['two_sided'])
    mat.set_editor_property('used_with_skeletal_mesh',True)
    mat.set_editor_property('used_with_morph_targets',True)
    if cfg['texture']:
        file=OUT/cfg['texture']
        task=U.AssetImportTask()
        for k,v in dict(filename=str(file),destination_path=DEST+'/Textures',automated=True,replace_existing=True,save=True).items(): task.set_editor_property(k,v)
        AT.import_asset_tasks([task])
        texture=E.load_asset(task.imported_object_paths[0])
        node=M.create_material_expression(mat,U.MaterialExpressionTextureSample)
        node.set_editor_property('texture',texture)
        assert M.connect_material_property(node,'RGB',U.MaterialProperty.MP_BASE_COLOR)
    else:
        node=M.create_material_expression(mat,U.MaterialExpressionConstant3Vector)
        node.set_editor_property('constant',U.LinearColor(*cfg['base_color']))
        assert M.connect_material_property(node,'',U.MaterialProperty.MP_BASE_COLOR)
    # Match the existing world's character lighting: a small albedo fill keeps
    # the unbaked dynamic character readable against baked/environment-lit art.
    fill=M.create_material_expression(mat,U.MaterialExpressionMultiply)
    fill.set_editor_property('const_b',.30)
    assert M.connect_material_expressions(node,'RGB' if cfg['texture'] else '',fill,'A')
    assert M.connect_material_property(fill,'',U.MaterialProperty.MP_EMISSIVE_COLOR)
    for field,prop in [('roughness',U.MaterialProperty.MP_ROUGHNESS),('metallic',U.MaterialProperty.MP_METALLIC),('specular',U.MaterialProperty.MP_SPECULAR)]:
        node=M.create_material_expression(mat,U.MaterialExpressionConstant)
        node.set_editor_property('r',cfg[field])
        assert M.connect_material_property(node,'',prop)
    M.recompile_material(mat)
    E.save_loaded_asset(mat)
    materials[name]=mat

def fbx(filename,name,skeleton=None,sample_rate=60):
    task=U.AssetImportTask()
    for prop,value in dict(filename=str(OUT/'fbx'/filename),destination_path=DEST,destination_name=name,
            automated=True,replace_existing=True,save=True).items(): task.set_editor_property(prop,value)
    options=U.FbxImportUI()
    for prop,value in dict(automated_import_should_detect_type=False,import_materials=False,import_textures=False,
            import_as_skeletal=True,import_mesh=skeleton is None,import_animations=skeleton is not None).items():
        options.set_editor_property(prop,value)
    if skeleton:
        options.set_editor_property('skeleton',skeleton)
        options.set_editor_property('mesh_type_to_import',U.FBXImportType.FBXIT_ANIMATION)
        data=options.get_editor_property('anim_sequence_import_data')
        data.set_editor_property('animation_length',U.FBXAnimationLengthImportType.FBXALIT_EXPORTED_TIME)
        data.set_editor_property('use_default_sample_rate',False)
        data.set_editor_property('custom_sample_rate',sample_rate)
        data.set_editor_property('import_bone_tracks',True)
        # Revisions can turn a formerly animated morph into a constant zero.
        # Do not leave the previous clip's curve active when FBX omits that track.
        data.set_editor_property('delete_existing_morph_target_curves',True)
        data.set_editor_property('do_not_import_curve_with_zero',False)
    else:
        options.set_editor_property('mesh_type_to_import',U.FBXImportType.FBXIT_SKELETAL_MESH)
        options.set_editor_property('create_physics_asset',True)
        data=options.get_editor_property('skeletal_mesh_import_data')
        data.set_editor_property('normal_import_method',U.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
        data.set_editor_property('vertex_color_import_option',U.VertexColorImportOption.REPLACE)
        data.set_editor_property('use_t0_as_ref_pose',False)
        data.set_editor_property('import_morph_targets',True)
        # The measured head changes eye pivots. This character owns its skeleton
        # and all clips are rebuilt together, so refresh its bind pose on reimport.
        data.set_editor_property('update_skeleton_reference_pose',True)
        data.set_editor_property('import_meshes_in_bone_hierarchy',True)
    data.set_editor_property('convert_scene',True)
    task.set_editor_property('options',options)
    AT.import_asset_tasks([task])
    imported=[E.load_asset(path) for path in task.get_editor_property('imported_object_paths')]
    result=next((a for a in imported if isinstance(a,U.AnimSequence if skeleton else U.SkeletalMesh)),None)
    if result is None: raise RuntimeError('Import failed: '+filename)
    return result

mesh=fbx('Cairo.fbx','SK_Cairo')
skeleton=mesh.skeleton
slots=list(mesh.materials)
for slot in slots:
    name=str(slot.get_editor_property('imported_material_slot_name'))
    assert name in materials,('Unknown material',name,list(materials))
    slot.set_editor_property('material_interface',materials[name])
mesh.set_editor_property('materials',slots)
E.save_loaded_asset(mesh)
editor=U.get_editor_subsystem(U.SkeletalMeshEditorSubsystem)
pending=['root'];bones=[]
while pending:
    bone=pending.pop()
    assert bone not in bones
    bones.append(bone)
    pending.extend(str(b) for b in editor.get_bone_children(mesh,bone))
assert set(bones)==set(CONFIG['bones'].values()),('Imported skeleton mismatch',bones)
clips={};report_clips={}
for name,cfg in CONFIG['clips'].items():
    clip=fbx('A_'+name+'.fbx','A_'+name,skeleton,cfg.get('sample_rate',60))
    assert clip.get_editor_property('skeleton')==skeleton
    assert abs(clip.get_editor_property('sequence_length')-cfg['duration'])<.001,(name,clip.get_editor_property('sequence_length'),cfg)
    clip.set_editor_property('enable_root_motion',False)
    animation_compression.apply_to(clip)
    E.save_loaded_asset(clip)
    curves={}
    for curve in A.get_animation_curve_names(clip,U.RawCurveTrackTypes.RCT_FLOAT):
        times,values=A.get_float_keys(clip,curve)
        curves[str(curve)]={'count':len(values),'min':min(values,default=0),'max':max(values,default=0),'values':list(values)}
    clips[name]=clip
    report_clips[name]={'path':clip.get_path_name(),'duration':clip.get_editor_property('sequence_length'),'curves':curves}
# Run deliberately reuses Sprint at 0.8; there is no independent jog clip. SwordRun (armed, since game-r16) is the same
# kind of alias and is made by import_cairo_armed.py, so neither is exported.
if set(clips)=={r['role'] for r in CONFIG['roles']}-{'Run','SwordRun'}:
    run=fbx('A_Sprint.fbx','A_Run',skeleton,CONFIG['clips']['Sprint'].get('sample_rate',60))
    animation_compression.apply_to(run)
    run.set_editor_property('rate_scale',.8)
    E.save_loaded_asset(run,only_if_is_dirty=False)
    clips['Run']=run
    rolemap={r['role']:r for r in CONFIG['roles']}
    scale=100*CONFIG['model_scale']
    speed=lambda role: float(rolemap[role].get('travel') or 0)*scale
    def blendspace(name,names):
        speeds=[speed(n) for n in names]
        factory=U.BlendSpaceFactory1D();factory.set_editor_property('target_skeleton',skeleton)
        blend=asset(name,U.BlendSpace1D,factory)
        params=list(blend.get_editor_property('blend_parameters'))
        for k,v in dict(display_name='Speed (cm/s)',min=0.,max=max(speeds)).items():params[0].set_editor_property(k,v)
        blend.set_editor_property('blend_parameters',params)
        blend.set_editor_property('scale_animation',True)
        smoothing=list(blend.get_editor_property('interpolation_param'))
        smoothing[0].set_editor_property('interpolation_time',.12)
        blend.set_editor_property('interpolation_param',smoothing)
        assert U.WandererContentLibrary.configure_blend_space(blend,[clips[n] for n in names],speeds)
        E.save_loaded_asset(blend)
        return blend
    moving=blendspace('BS_Locomotion',['Idle','Walk','Run','Sprint'])
    crouching=blendspace('BS_Crouching',['CrouchIdle','CrouchWalk'])
    factory=U.DataAssetFactory();factory.set_editor_property('data_asset_class',U.WandererDefinition)
    definition=asset('DA_Cairo',U.WandererDefinition,factory)
    for k,v in dict(mesh=mesh,locomotion=moving,crouching=crouching,actions=clips,
        skate_actions={},use_authored_movement=True,
        rest_ankle_heights=U.Vector2D(CONFIG['rest_ankles_cm']['L'],CONFIG['rest_ankles_cm']['R']),
        sole_height=CONFIG['sole_cm'],camera_height=35.,walk_speed=speed('Walk'),
        jog_speed=speed('Walk'),run_speed=speed('Run'),sprint_speed=speed('Sprint'),crouch_speed=speed('CrouchWalk'),
        ground_dash_profile=[U.Vector2D(t,v*scale) for t,v in rolemap['DashGround']['travel_profile_units_per_second']],
        air_dash_profile=[U.Vector2D(t,v*scale) for t,v in rolemap['DashAir']['travel_profile_units_per_second']],
        roll_profile=[U.Vector2D(t,v*scale) for t,v in rolemap.get('Roll',{}).get('travel_profile_units_per_second',[])],
        roll_dive_takeoff=rolemap.get('Roll',{}).get('dive_takeoff_seconds',0.),
        roll_dive_touchdown=rolemap.get('Roll',{}).get('dive_touchdown_seconds',0.)).items():definition.set_editor_property(k,v)
    E.save_loaded_asset(definition)
E.save_loaded_asset(skeleton)
report={'mesh':mesh.get_path_name(),'bones':bones,'materials':[str(s.material_slot_name) for s in slots],
    'lod_vertices':[editor.get_num_verts(mesh,i) for i in range(editor.get_lod_count(mesh))],'morphs':[m.get_name() for m in mesh.get_editor_property('morph_targets')],
    'clips':report_clips,'source':CONFIG['source_sha256']}
(OUT/'unreal_import.json').write_text(json.dumps(report,indent=2)+'\n')
U.log('CAIRO IMPORT COMPLETE')

exec(compile((Path(__file__).with_name("verify_cairo.py")).read_text(),str(Path(__file__).with_name("verify_cairo.py")),"exec"))
