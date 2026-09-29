"""Import Wanderer V2 into its own compact skeleton, preserving the public selection asset."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import json
import sys
from pathlib import Path
import unreal as U
sys.path.insert(0,str(Path(__file__).resolve().parent))
import animation_compression

ROOT = yori.OUT
sys.path.insert(0,str(yori.ASSETS/'characters/wanderer'))
import importlib.util
spec=importlib.util.spec_from_file_location('wanderer_pipeline',yori.ASSETS/'characters/wanderer/pipeline.py')
pipeline=importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)
BUILD=pipeline.verify()
OUT=pipeline.OUT
DEST='/Game/Wanderer/V2'
E=U.EditorAssetLibrary
AT=U.AssetToolsHelpers.get_asset_tools()
M=U.MaterialEditingLibrary
E.make_directory(DEST)

def asset(name,cls,factory):
    path=DEST+'/'+name
    result=E.load_asset(path) if E.does_asset_exist(path) else AT.create_asset(name,DEST,cls,factory)
    if not isinstance(result,cls): raise RuntimeError('Unexpected asset type: '+path)
    return result

# The reference is flat colour. No grain, normal noise, detail maps or texture fetches.
material=asset('M_Wanderer',U.Material,U.MaterialFactoryNew())
M.delete_all_material_expressions(material)
material.set_editor_property('used_with_skeletal_mesh',True)
material.set_editor_property('two_sided',True)
vc=M.create_material_expression(material,U.MaterialExpressionVertexColor,-500,0)
linear=M.create_material_expression(material,U.MaterialExpressionCustom,-300,0)
linear.set_editor_property('code','return lerp(C/12.92,pow((C+0.055)/1.055,2.4),step(0.04045,C));')
linear.set_editor_property('output_type',U.CustomMaterialOutputType.CMOT_FLOAT3)
ci=U.CustomInput()
ci.set_editor_property('input_name','C')
linear.set_editor_property('inputs',[ci])
assert M.connect_material_expressions(vc,'',linear,'C')
assert M.connect_material_property(linear,'',U.MaterialProperty.MP_BASE_COLOR)
for prop,value,y in [(U.MaterialProperty.MP_ROUGHNESS,1.,100),(U.MaterialProperty.MP_SPECULAR,0.,180)]:
    constant=M.create_material_expression(material,U.MaterialExpressionConstant,-200,y)
    constant.set_editor_property('r',value)
    assert M.connect_material_property(constant,'',prop)
fill=M.create_material_expression(material,U.MaterialExpressionMultiply,-100,280)
fill.set_editor_property('const_b',.30)
assert M.connect_material_expressions(linear,'',fill,'A')
assert M.connect_material_property(fill,'',U.MaterialProperty.MP_EMISSIVE_COLOR)
M.recompile_material(material)
E.save_loaded_asset(material)

def fbx(filename,name,skeleton=None):
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
        data.set_editor_property('custom_sample_rate',60)
        data.set_editor_property('import_bone_tracks',True)
    else:
        options.set_editor_property('mesh_type_to_import',U.FBXImportType.FBXIT_SKELETAL_MESH)
        options.set_editor_property('create_physics_asset',True)
        data=options.get_editor_property('skeletal_mesh_import_data')
        data.set_editor_property('normal_import_method',U.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
        data.set_editor_property('vertex_color_import_option',U.VertexColorImportOption.REPLACE)
        data.set_editor_property('use_t0_as_ref_pose',False)
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

mesh=fbx('Wanderer.fbx','SK_Wanderer')
skeleton=mesh.get_editor_property('skeleton')
slots=list(mesh.get_editor_property('materials'))
assert len(slots)==1,'The reference character should have one palette material'
slots[0].set_editor_property('material_interface',material)
mesh.set_editor_property('materials',slots)
E.save_loaded_asset(mesh)
editor=U.get_editor_subsystem(U.SkeletalMeshEditorSubsystem)
manifest=json.loads((OUT/'model_manifest.json').read_text())
for bone,parent in manifest['bones'].items():
    if parent:
        assert str(editor.get_bone_parent(mesh,bone))==parent,'Bone hierarchy mismatch: '+bone
pending=['root']
bones=[]
while pending:
    bone=pending.pop()
    assert bone not in bones,'Skeleton cycle'
    bones.append(bone)
    pending.extend(str(b) for b in editor.get_bone_children(mesh,bone))
assert set(bones)==set(manifest['bones']),'Imported bone set differs'
settings=json.loads((OUT/'animation_manifest.json').read_text())
clips={}
for name,cfg in settings.items():
    clip=fbx(name+'.fbx','A_'+name,skeleton)
    assert clip.get_editor_property('skeleton')==skeleton
    assert abs(clip.get_editor_property('sequence_length')-cfg['duration'])<.02,(name,'Clip duration mismatch')
    clip.set_editor_property('enable_root_motion',False)
    animation_compression.apply_to(clip)
    E.save_loaded_asset(clip)
    clips[name]=clip

def blendspace(name,names):
    speeds=[settings[n].get('speed',0)*100 for n in names]
    factory=U.BlendSpaceFactory1D()
    factory.set_editor_property('target_skeleton',skeleton)
    blend=asset(name,U.BlendSpace1D,factory)
    params=list(blend.get_editor_property('blend_parameters'))
    for prop,value in dict(display_name='Speed (cm/s)',min=0.,max=max(speeds)).items(): params[0].set_editor_property(prop,value)
    blend.set_editor_property('blend_parameters',params)
    blend.set_editor_property('scale_animation',True)
    smoothing=list(blend.get_editor_property('interpolation_param'))
    # The upright idle pelvis needs a little longer to settle after braking.
    # A 90 ms filter could lift the torso by 2 cm in one 60 Hz frame.
    smoothing[0].set_editor_property('interpolation_time',.14 if name=='BS_Locomotion' else .09)
    blend.set_editor_property('interpolation_param',smoothing)
    assert U.WandererContentLibrary.configure_blend_space(blend,[clips[n] for n in names],speeds)
    E.save_loaded_asset(blend)
    return blend

moving=blendspace('BS_Locomotion',['Idle','Walk','Jog','Run'])
crouching=blendspace('BS_Crouching',['CrouchIdle','CrouchWalk'])
factory=U.DataAssetFactory()
factory.set_editor_property('data_asset_class',U.WandererDefinition)
definition_path='/Game/Wanderer/DA_Wanderer'
definition=E.load_asset(definition_path) if E.does_asset_exist(definition_path) else None
if definition is None: definition=AT.create_asset('DA_Wanderer','/Game/Wanderer',U.WandererDefinition,factory)
old_mesh=definition.get_editor_property('mesh')
if old_mesh is None or old_mesh.get_editor_property('skeleton')!=skeleton:
    definition.set_editor_property('skate_actions',{})
for prop,value in dict(mesh=mesh,locomotion=moving,crouching=crouching,actions=clips,
        camera_height=35.,
        walk_speed=settings['Walk']['speed']*100,jog_speed=settings['Jog']['speed']*100,
        run_speed=settings['Run']['speed']*100,crouch_speed=settings['CrouchWalk']['speed']*100).items():
    definition.set_editor_property(prop,value)
E.save_loaded_asset(definition)
# LOD0 is already small. Preserve its deliberate facial facets;
# blind reduction at gameplay distance would erase the two tiny eyes and hair tips.
report=dict(mesh=mesh.get_path_name(),definition=definition.get_path_name(),bones=len(bones),
    material_slots=len(slots),lod_vertices=[editor.get_num_verts(mesh,i) for i in range(editor.get_lod_count(mesh))],
    clips={name:dict(path=clip.get_path_name(),length=clip.get_editor_property('sequence_length')) for name,clip in clips.items()},
    build_sources=BUILD['sources'])
(OUT/'unreal_import.json').write_text(json.dumps(report,indent=2)+'\n')
U.log('WANDERER IMPORT COMPLETE: '+str(len(clips))+' clips; '+str(len(bones))+' bones')
