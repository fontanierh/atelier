"""Import the fox hunter enemy (animation-r04 export) into its own package, /Game/FoxHunter.

Run after `export_fox_hunter_unreal.py`:

    UnrealEditor-Cmd Yorimichi.uproject -run=pythonscript -script=Scripts/import_fox_hunter.py -unattended -nosplash -NullRHI -stdout

Creates SK_FoxHunter with its skeleton and physics asset, M_FoxHunter_* with the colour map and a HitFlash
parameter, the fifteen A_Fox* clips (root motion enabled where the export says so, root lock at the reference
pose, the shared character compression), BS_FoxLocomotion (idle, creep, run by speed) and DA_FoxHunter. Nothing
under /Game/Cairo or the other character folders is touched.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import json, sys
from pathlib import Path
import unreal as U
sys.path.insert(0, str(Path(__file__).resolve().parent))
import animation_compression
ROOT = yori.OUT
OUT = ROOT / 'fox_hunter'
CONFIG = json.loads((OUT / 'export.json').read_text())
DEST = '/Game/FoxHunter'
E = U.EditorAssetLibrary; AT = U.AssetToolsHelpers.get_asset_tools(); M = U.MaterialEditingLibrary; A = U.AnimationLibrary
E.make_directory(DEST)


def asset(name, cls, factory, folder=DEST):
    path = folder + '/' + name
    return E.load_asset(path) if E.does_asset_exist(path) else AT.create_asset(name, folder, cls, factory)


# ---- material: colour map, the same small albedo fill as the player, plus a HitFlash emissive the game drives
materials = {}
for name, cfg in CONFIG['materials'].items():
    mat = asset(name, U.Material, U.MaterialFactoryNew())
    M.delete_all_material_expressions(mat)
    mat.set_editor_property('two_sided', cfg['two_sided'])
    mat.set_editor_property('used_with_skeletal_mesh', True)
    task = U.AssetImportTask()
    for k, v in dict(filename=str(OUT / cfg['texture']), destination_path=DEST + '/Textures', automated=True, replace_existing=True, save=True).items(): task.set_editor_property(k, v)
    AT.import_asset_tasks([task])
    texture = E.load_asset(task.imported_object_paths[0])
    sample = M.create_material_expression(mat, U.MaterialExpressionTextureSample); sample.set_editor_property('texture', texture)
    assert M.connect_material_property(sample, 'RGB', U.MaterialProperty.MP_BASE_COLOR)
    fill = M.create_material_expression(mat, U.MaterialExpressionMultiply); fill.set_editor_property('const_b', .30)
    assert M.connect_material_expressions(sample, 'RGB', fill, 'A')
    flash = M.create_material_expression(mat, U.MaterialExpressionScalarParameter); flash.set_editor_property('parameter_name', 'HitFlash'); flash.set_editor_property('default_value', 0.)
    tint = M.create_material_expression(mat, U.MaterialExpressionConstant3Vector); tint.set_editor_property('constant', U.LinearColor(1., .45, .25, 1.))
    glow = M.create_material_expression(mat, U.MaterialExpressionMultiply)
    assert M.connect_material_expressions(flash, '', glow, 'A'); assert M.connect_material_expressions(tint, '', glow, 'B')
    total = M.create_material_expression(mat, U.MaterialExpressionAdd)
    assert M.connect_material_expressions(fill, '', total, 'A'); assert M.connect_material_expressions(glow, '', total, 'B')
    # Death: 'Dissolve' 0..1 burns the body away through world-space noise, with a glowing ember edge (FoxHunter.cpp).
    mat.set_editor_property('blend_mode', U.BlendMode.BLEND_MASKED); mat.set_editor_property('opacity_mask_clip_value', .0001)
    noise = M.create_material_expression(mat, U.MaterialExpressionNoise)
    for k, v in dict(scale=.045, levels=3, output_min=0., output_max=1., quality=1).items(): noise.set_editor_property(k, v)
    dissolve = M.create_material_expression(mat, U.MaterialExpressionScalarParameter); dissolve.set_editor_property('parameter_name', 'Dissolve'); dissolve.set_editor_property('default_value', 0.)
    reach = M.create_material_expression(mat, U.MaterialExpressionMultiply); reach.set_editor_property('const_b', 1.25)
    assert M.connect_material_expressions(dissolve, '', reach, 'A')
    front = M.create_material_expression(mat, U.MaterialExpressionSubtract); front.set_editor_property('const_b', .12)
    assert M.connect_material_expressions(reach, '', front, 'A')
    left = M.create_material_expression(mat, U.MaterialExpressionSubtract)
    assert M.connect_material_expressions(noise, '', left, 'A'); assert M.connect_material_expressions(front, '', left, 'B')
    assert M.connect_material_property(left, '', U.MaterialProperty.MP_OPACITY_MASK)
    band = M.create_material_expression(mat, U.MaterialExpressionMultiply); band.set_editor_property('const_b', 14.)
    assert M.connect_material_expressions(left, '', band, 'A')
    near = M.create_material_expression(mat, U.MaterialExpressionOneMinus); assert M.connect_material_expressions(band, '', near, '')
    near_sat = M.create_material_expression(mat, U.MaterialExpressionSaturate); assert M.connect_material_expressions(near, '', near_sat, '')
    burning = M.create_material_expression(mat, U.MaterialExpressionMultiply); burning.set_editor_property('const_b', 40.)
    assert M.connect_material_expressions(dissolve, '', burning, 'A')
    burning_sat = M.create_material_expression(mat, U.MaterialExpressionSaturate); assert M.connect_material_expressions(burning, '', burning_sat, '')
    edge = M.create_material_expression(mat, U.MaterialExpressionMultiply)
    assert M.connect_material_expressions(near_sat, '', edge, 'A'); assert M.connect_material_expressions(burning_sat, '', edge, 'B')
    ember = M.create_material_expression(mat, U.MaterialExpressionConstant3Vector); ember.set_editor_property('constant', U.LinearColor(14., 4., 1., 1.))
    edge_glow = M.create_material_expression(mat, U.MaterialExpressionMultiply)
    assert M.connect_material_expressions(edge, '', edge_glow, 'A'); assert M.connect_material_expressions(ember, '', edge_glow, 'B')
    emissive = M.create_material_expression(mat, U.MaterialExpressionAdd)
    assert M.connect_material_expressions(total, '', emissive, 'A'); assert M.connect_material_expressions(edge_glow, '', emissive, 'B')
    assert M.connect_material_property(emissive, '', U.MaterialProperty.MP_EMISSIVE_COLOR)
    for field, prop in [('roughness', U.MaterialProperty.MP_ROUGHNESS), ('metallic', U.MaterialProperty.MP_METALLIC), ('specular', U.MaterialProperty.MP_SPECULAR)]:
        c = M.create_material_expression(mat, U.MaterialExpressionConstant); c.set_editor_property('r', cfg[field]); assert M.connect_material_property(c, '', prop)
    M.recompile_material(mat); E.save_loaded_asset(mat); materials[name] = mat


def fbx(filename, name, skeleton=None, sample_rate=30):
    task = U.AssetImportTask()
    for prop, value in dict(filename=str(OUT / 'fbx' / filename), destination_path=DEST, destination_name=name, automated=True, replace_existing=True, save=True).items():
        task.set_editor_property(prop, value)
    options = U.FbxImportUI()
    for prop, value in dict(automated_import_should_detect_type=False, import_materials=False, import_textures=False, import_as_skeletal=True,
                            import_mesh=skeleton is None, import_animations=skeleton is not None).items():
        options.set_editor_property(prop, value)
    if skeleton:
        options.set_editor_property('skeleton', skeleton)
        options.set_editor_property('mesh_type_to_import', U.FBXImportType.FBXIT_ANIMATION)
        data = options.get_editor_property('anim_sequence_import_data')
        for prop, value in dict(animation_length=U.FBXAnimationLengthImportType.FBXALIT_EXPORTED_TIME, use_default_sample_rate=False, custom_sample_rate=sample_rate,
                                import_bone_tracks=True, delete_existing_morph_target_curves=True, do_not_import_curve_with_zero=False).items():
            data.set_editor_property(prop, value)
    else:
        options.set_editor_property('mesh_type_to_import', U.FBXImportType.FBXIT_SKELETAL_MESH)
        options.set_editor_property('create_physics_asset', True)
        data = options.get_editor_property('skeletal_mesh_import_data')
        for prop, value in dict(normal_import_method=U.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS, vertex_color_import_option=U.VertexColorImportOption.REPLACE,
                                use_t0_as_ref_pose=False, import_morph_targets=False, update_skeleton_reference_pose=True, import_meshes_in_bone_hierarchy=True).items():
            data.set_editor_property(prop, value)
    data.set_editor_property('convert_scene', True)
    task.set_editor_property('options', options)
    AT.import_asset_tasks([task])
    imported = [E.load_asset(path) for path in task.get_editor_property('imported_object_paths')]
    result = next((a for a in imported if isinstance(a, U.AnimSequence if skeleton else U.SkeletalMesh)), None)
    if result is None: raise RuntimeError('Import failed: ' + filename)
    return result


mesh = fbx(Path(CONFIG['mesh']).name, 'SK_FoxHunter')
skeleton = mesh.skeleton
slots = list(mesh.materials)
for slot in slots:
    name = str(slot.get_editor_property('imported_material_slot_name'))
    assert name in materials, ('Unknown material', name, list(materials))
    slot.set_editor_property('material_interface', materials[name])
mesh.set_editor_property('materials', slots)
E.save_loaded_asset(mesh)
editor = U.get_editor_subsystem(U.SkeletalMeshEditorSubsystem)
pending = ['root']; bones = []
while pending:
    bone = pending.pop(); assert bone not in bones; bones.append(bone)
    pending.extend(str(b) for b in editor.get_bone_children(mesh, bone))
assert set(bones) == set(CONFIG['bones'].values()), ('Imported skeleton mismatch', bones)
pose = U.AnimPoseExtensions.get_reference_pose(skeleton)
root_scale = U.AnimPoseExtensions.get_bone_pose(pose, 'root', U.AnimPoseSpaces.WORLD).scale3d.x
ref = {b: U.AnimPoseExtensions.get_bone_pose(pose, b, U.AnimPoseSpaces.WORLD).translation for b in ('pelvis', 'head', 'hand_R', 'finger_end_1_R', 'foot_R')}
gaps = {b: (ref[b] - U.Vector(*CONFIG['rest_bones_cm'][b])).length() for b in ref}
U.log(f'FOX REF root scale {root_scale:.3f} gaps {gaps}')
assert max(gaps.values()) < .5, ('reference pose does not match the export space', gaps)

clips = {}; report_clips = {}
for name, cfg in CONFIG['clips'].items():
    clip = fbx(f'A_Fox{name}.fbx', 'A_Fox' + name, skeleton, cfg.get('sample_rate', 30))
    assert clip.get_editor_property('skeleton') == skeleton
    assert abs(clip.get_editor_property('sequence_length') - cfg['duration']) < .001, (name, clip.get_editor_property('sequence_length'), cfg['duration'])
    clip.set_editor_property('enable_root_motion', bool(cfg['root_motion']))
    clip.set_editor_property('root_motion_root_lock', U.RootMotionRootLock.REF_POSE)
    animation_compression.apply_to(clip)
    E.save_loaded_asset(clip)
    clips[name] = clip
    report_clips[name] = {'path': clip.get_path_name(), 'duration': clip.get_editor_property('sequence_length'), 'root_motion': bool(cfg['root_motion'])}

speeds = {n: float(CONFIG['clips'][n]['travel_speed_cm_s']) for n in ('Idle', 'Creep', 'Run')}
factory = U.BlendSpaceFactory1D(); factory.set_editor_property('target_skeleton', skeleton)
blend = asset('BS_FoxLocomotion', U.BlendSpace1D, factory)
params = list(blend.get_editor_property('blend_parameters'))
for k, v in dict(display_name='Speed (cm/s)', min=0., max=speeds['Run']).items(): params[0].set_editor_property(k, v)
blend.set_editor_property('blend_parameters', params)
blend.set_editor_property('scale_animation', True)
smoothing = list(blend.get_editor_property('interpolation_param')); smoothing[0].set_editor_property('interpolation_time', .12)
blend.set_editor_property('interpolation_param', smoothing)
assert U.WandererContentLibrary.configure_blend_space(blend, [clips[n] for n in ('Idle', 'Creep', 'Run')], [speeds[n] for n in ('Idle', 'Creep', 'Run')])
E.save_loaded_asset(blend)

entries = []
for name, cfg in CONFIG['clips'].items():
    e = U.FoxHunterClip()
    e.set_editor_property('role', name); e.set_editor_property('duration', float(cfg['duration']))
    hw = cfg.get('hit_window')
    e.set_editor_property('hit_start', float(hw[0]) if hw else -1.); e.set_editor_property('hit_end', float(hw[1]) if hw else -1.)
    e.set_editor_property('strike_bone', cfg.get('strike_bone', 'None')); e.set_editor_property('strike_tip_bone', cfg.get('strike_tip_bone', 'None'))
    e.set_editor_property('reach_cm', float(cfg.get('reach_cm', 0.)))
    e.set_editor_property('root_motion', bool(cfg['root_motion'])); e.set_editor_property('loop', bool(cfg['loop'])); e.set_editor_property('holds_last_pose', bool(cfg['holds_last_pose']))
    e.set_editor_property('travel_cm', float(cfg['travel_cm'][0])); e.set_editor_property('yaw_degrees', float(cfg['yaw_degrees']))
    entries.append(e)
factory = U.DataAssetFactory(); factory.set_editor_property('data_asset_class', U.FoxHunterDefinition)
definition = asset('DA_FoxHunter', U.FoxHunterDefinition, factory)
for k, v in dict(mesh=mesh, locomotion=blend, actions=clips, clips=entries, creep_speed=speeds['Creep'], run_speed=speeds['Run'],
                 capsule_radius=float(CONFIG['capsule']['radius_cm']), capsule_half_height=float(CONFIG['capsule']['half_height_cm']), sole_height=float(CONFIG['sole_cm'])).items():
    definition.set_editor_property(k, v)
E.save_loaded_asset(definition)
E.save_loaded_asset(skeleton)
report = {'mesh': mesh.get_path_name(), 'bones': bones, 'root_scale': root_scale, 'reference_gaps_cm': gaps, 'materials': [str(s.material_slot_name) for s in slots],
          'lod_vertices': [editor.get_num_verts(mesh, i) for i in range(editor.get_lod_count(mesh))], 'clips': report_clips, 'speeds': speeds, 'definition': definition.get_path_name(),
          'source': CONFIG['source_sha256']}
(OUT / 'unreal_import.json').write_text(json.dumps(report, indent=2) + '\n')
U.log('FOX HUNTER IMPORT COMPLETE: %d clips, %d bones' % (len(clips), len(bones)))
