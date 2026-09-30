"""Install the sword combat set (game-r13) into the existing Cairo character.

Run after `games/yorimichi/assets/characters/cairo/export_unreal.py -- --revision game-r13 --clips Sword... --clips-only --sword --report export-sword.json`:

    UnrealEditor-Cmd Yorimichi.uproject -run=pythonscript -script=Scripts/import_cairo_sword.py -unattended -nosplash -NullRHI -stdout

Targeted on purpose: it imports only the A_Sword* clips onto the existing SK_Cairo skeleton, the
bokken static mesh and its materials, and adds the sword fields to DA_Cairo. Meshes, the 25
existing clips, blend spaces, movement settings, sounds and materials are untouched (their file digests
are compared before and after).
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import hashlib, json
from pathlib import Path
import unreal as U
ROOT = yori.OUT
OUT = ROOT / 'cairo'
CONTENT = yori.GAME / 'unreal/Content/Cairo'
CONFIG = json.loads((OUT / 'export-sword.json').read_text())
DEST = '/Game/Cairo'
E = U.EditorAssetLibrary; AT = U.AssetToolsHelpers.get_asset_tools(); M = U.MaterialEditingLibrary
import sys; sys.path.insert(0, str(Path(__file__).resolve().parent))
import animation_compression


def protected():
    return {str(p.relative_to(CONTENT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in CONTENT.rglob('*.uasset')
            if p.name.startswith(('A_', 'BS_', 'M_Cairo', 'T_', 'SK_')) and not p.name.startswith(('A_Sword', 'T_M_Bokken'))}


def asset(name, cls, factory, folder=DEST):
    path = folder + '/' + name
    return E.load_asset(path) if E.does_asset_exist(path) else AT.create_asset(name, folder, cls, factory)


before = protected()
mesh = E.load_asset(DEST + '/SK_Cairo'); assert mesh, 'import the full character first'
skeleton = mesh.skeleton
definition = E.load_asset(DEST + '/DA_Cairo'); assert definition

# ---- clips
clips = dict(definition.get_editor_property('actions'))
report = {'clips': {}}
for name, cfg in CONFIG['clips'].items():
    task = U.AssetImportTask()
    for prop, value in dict(filename=str(OUT / 'fbx' / f'A_{name}.fbx'), destination_path=DEST, destination_name='A_' + name, automated=True, replace_existing=True, save=True).items():
        task.set_editor_property(prop, value)
    options = U.FbxImportUI()
    for prop, value in dict(automated_import_should_detect_type=False, import_materials=False, import_textures=False, import_as_skeletal=True, import_mesh=False, import_animations=True, skeleton=skeleton,
                            mesh_type_to_import=U.FBXImportType.FBXIT_ANIMATION).items():
        options.set_editor_property(prop, value)
    data = options.get_editor_property('anim_sequence_import_data')
    for prop, value in dict(animation_length=U.FBXAnimationLengthImportType.FBXALIT_EXPORTED_TIME, use_default_sample_rate=False, custom_sample_rate=cfg.get('sample_rate', 60), import_bone_tracks=True,
                            delete_existing_morph_target_curves=True, do_not_import_curve_with_zero=False, convert_scene=True).items():
        data.set_editor_property(prop, value)
    task.set_editor_property('options', options)
    AT.import_asset_tasks([task])
    clip = next((a for a in (E.load_asset(p) for p in task.get_editor_property('imported_object_paths')) if isinstance(a, U.AnimSequence)), None)
    assert clip, 'import failed: ' + name
    assert clip.get_editor_property('skeleton') == skeleton
    assert abs(clip.get_editor_property('sequence_length') - cfg['duration']) < .001, (name, clip.get_editor_property('sequence_length'), cfg['duration'])
    clip.set_editor_property('enable_root_motion', bool(cfg.get('root_motion')))
    clip.set_editor_property('root_motion_root_lock', U.RootMotionRootLock.REF_POSE)
    animation_compression.apply_to(clip)
    E.save_loaded_asset(clip)
    clips[name] = clip
    report['clips'][name] = {'path': clip.get_path_name(), 'duration': clip.get_editor_property('sequence_length'), 'root_motion': bool(cfg.get('root_motion'))}
    U.log(f'SWORD CLIP {name} {clip.get_editor_property("sequence_length"):.3f}s root_motion={bool(cfg.get("root_motion"))}')

# ---- bokken static mesh + materials
sword_cfg = CONFIG['sword']
materials = {}
for mat_name, cfg in sword_cfg['materials'].items():
    mat = asset(mat_name, U.Material, U.MaterialFactoryNew())
    M.delete_all_material_expressions(mat)
    # Opaque until see_through.py masks it again: the opacity mask may still point at its deleted nodes.
    mat.set_editor_property('blend_mode', U.BlendMode.BLEND_OPAQUE)
    mat.set_editor_property('two_sided', cfg['two_sided'])
    if cfg['texture']:
        task = U.AssetImportTask()
        for k, v in dict(filename=str(OUT / cfg['texture']), destination_path=DEST + '/Textures', automated=True, replace_existing=True, save=True).items(): task.set_editor_property(k, v)
        AT.import_asset_tasks([task])
        texture = E.load_asset(task.imported_object_paths[0])
        node = M.create_material_expression(mat, U.MaterialExpressionTextureSample); node.set_editor_property('texture', texture)
        assert M.connect_material_property(node, 'RGB', U.MaterialProperty.MP_BASE_COLOR)
        fill = M.create_material_expression(mat, U.MaterialExpressionMultiply); fill.set_editor_property('const_b', .30)
        assert M.connect_material_expressions(node, 'RGB', fill, 'A')
    else:
        node = M.create_material_expression(mat, U.MaterialExpressionConstant3Vector); node.set_editor_property('constant', U.LinearColor(*cfg['base_color']))
        assert M.connect_material_property(node, '', U.MaterialProperty.MP_BASE_COLOR)
        fill = M.create_material_expression(mat, U.MaterialExpressionMultiply); fill.set_editor_property('const_b', .30)
        assert M.connect_material_expressions(node, '', fill, 'A')
    # same small albedo fill as the character so the prop reads under the same lighting
    assert M.connect_material_property(fill, '', U.MaterialProperty.MP_EMISSIVE_COLOR)
    for field, prop in [('roughness', U.MaterialProperty.MP_ROUGHNESS), ('metallic', U.MaterialProperty.MP_METALLIC), ('specular', U.MaterialProperty.MP_SPECULAR)]:
        c = M.create_material_expression(mat, U.MaterialExpressionConstant); c.set_editor_property('r', cfg[field]); assert M.connect_material_property(c, '', prop)
    M.recompile_material(mat); E.save_loaded_asset(mat); materials[mat_name] = mat
task = U.AssetImportTask()
for k, v in dict(filename=str(OUT / sword_cfg['mesh']), destination_path=DEST, destination_name='SM_Bokken', automated=True, replace_existing=True, save=True).items(): task.set_editor_property(k, v)
options = U.FbxImportUI()
for prop, value in dict(automated_import_should_detect_type=False, import_materials=False, import_textures=False, import_as_skeletal=False, import_mesh=True, import_animations=False,
                        mesh_type_to_import=U.FBXImportType.FBXIT_STATIC_MESH).items():
    options.set_editor_property(prop, value)
sdata = options.get_editor_property('static_mesh_import_data')
for prop, value in dict(combine_meshes=True, generate_lightmap_u_vs=False, auto_generate_collision=False, convert_scene=True).items(): sdata.set_editor_property(prop, value)
sdata.set_editor_property('normal_import_method', U.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
task.set_editor_property('options', options)
AT.import_asset_tasks([task])
bokken = next((a for a in (E.load_asset(p) for p in task.get_editor_property('imported_object_paths')) if isinstance(a, U.StaticMesh)), None)
assert bokken, 'bokken import failed'
slots = list(bokken.get_editor_property('static_materials'))
for slot in slots:
    name = str(slot.get_editor_property('imported_material_slot_name'))
    if name in materials: slot.set_editor_property('material_interface', materials[name])
    else: U.log_warning('bokken slot without exported material: ' + name)
bokken.set_editor_property('static_materials', slots)
E.save_loaded_asset(bokken)

# ---- attachment: rest sword transform (component space) relative to the hand bone's reference pose
pose = U.AnimPoseExtensions.get_reference_pose(skeleton)
hand = U.AnimPoseExtensions.get_bone_pose(pose, sword_cfg['attach_bone'], U.AnimPoseSpaces.WORLD)
rest = sword_cfg['rest_component_transform']
sword_tf = U.Transform(U.Vector(*rest['location_cm']), U.Quat(*rest['rotation_quat_xyzw']).rotator(), U.Vector(1, 1, 1))
relative = U.MathLibrary.compose_transforms(sword_tf, U.MathLibrary.invert_transform(hand))
# consistency: the exported hand position should coincide with the skeleton's reference pose (both from the same FBX conversion)
exported_hand = U.Vector(*sword_cfg['rest_hand_component_transform']['location_cm'])
hand_gap = (hand.translation - exported_hand).length()
tip = U.MathLibrary.transform_location(sword_tf, U.Vector(*sword_cfg['blade_local_cm']['end']))
tip_gap = (tip - U.Vector(*sword_cfg['rest_tip_cm'])).length()
pelvis = U.AnimPoseExtensions.get_bone_pose(pose, 'pelvis', U.AnimPoseSpaces.WORLD)
U.log(f'SWORD ATTACH hand gap {hand_gap:.3f} cm, tip gap {tip_gap:.3f} cm, relative {relative}')
U.log(f'SWORD ATTACH ue hand {hand.translation} rot {hand.rotation} | exported hand {exported_hand} rot {sword_cfg["rest_hand_component_transform"]["rotation_quat_xyzw"]} | ue pelvis {pelvis.translation}')
def tf_rows(t): return {'location': [t.translation.x, t.translation.y, t.translation.z], 'rotation_xyzw': [t.rotation.x, t.rotation.y, t.rotation.z, t.rotation.w]}
(OUT / 'unreal_sword_attach_debug.json').write_text(json.dumps({'ue_hand': tf_rows(hand), 'ue_pelvis': tf_rows(pelvis), 'ue_root': tf_rows(U.AnimPoseExtensions.get_bone_pose(pose, 'root', U.AnimPoseSpaces.WORLD)),
    'ue_head': tf_rows(U.AnimPoseExtensions.get_bone_pose(pose, 'head', U.AnimPoseSpaces.WORLD)), 'ue_forearm_R': tf_rows(U.AnimPoseExtensions.get_bone_pose(pose, 'forearm_R', U.AnimPoseSpaces.WORLD)),
    'exported_hand': sword_cfg['rest_hand_component_transform'], 'exported_sword': rest, 'hand_gap_cm': hand_gap, 'tip_gap_cm': tip_gap}, indent=1) + '\n')
assert hand_gap < .5, ('hand_R reference pose does not match the export space', hand_gap)
assert tip_gap < .5, ('blade end inconsistent', tip_gap)

# ---- definition
roles = {r['role']: r for r in CONFIG['roles'] if r.get('sword')}
entries = []
for name in CONFIG['clips']:
    r = roles[name]; e = U.WandererSwordClip()
    e.set_editor_property('role', name); e.set_editor_property('duration', float(r['duration_seconds']))
    aw = r.get('active_window_seconds'); lw = r.get('link_window_seconds')
    e.set_editor_property('active_start', float(aw[0]) if aw else -1.); e.set_editor_property('active_end', float(aw[1]) if aw else -1.)
    e.set_editor_property('link_start', float(lw[0]) if lw else -1.); e.set_editor_property('cancel', float(r['cancel_after_seconds']) if 'cancel_after_seconds' in r else -1.)
    e.set_editor_property('counter', float(r['counter_from_seconds']) if 'counter_from_seconds' in r else -1.)
    e.set_editor_property('root_motion', 'root bone' in r['root_motion']); e.set_editor_property('end_yaw', float(r.get('end_yaw_degrees', 0)))
    # combat-r02: where the strike meets a target (degrees to the left of the start facing; armature units -> cm)
    if 'contact_distance' in r:
        e.set_editor_property('contact_yaw', float(r['contact_yaw_degrees'])); e.set_editor_property('contact_distance', float(r['contact_distance']) * 100. * CONFIG['model_scale'])
    entries.append(e)
definition.set_editor_property('actions', clips)
definition.set_editor_property('sword_mesh', bokken)
definition.set_editor_property('sword_attach_bone', sword_cfg['attach_bone'])
definition.set_editor_property('sword_attach', relative)
definition.set_editor_property('sword_blade_start', U.Vector(*sword_cfg['blade_local_cm']['start']))
definition.set_editor_property('sword_blade_end', U.Vector(*sword_cfg['blade_local_cm']['end']))
definition.set_editor_property('sword_clips', entries)
E.save_loaded_asset(definition)
E.save_loaded_asset(skeleton)
after = protected()
changed = sorted(k for k in before if before[k] != after.get(k))
report.update({'sword_mesh': bokken.get_path_name(), 'relative_attach': str(relative), 'hand_gap_cm': hand_gap, 'tip_gap_cm': tip_gap,
               'definition_actions': sorted(str(k) for k in definition.get_editor_property('actions').keys()), 'sword_clip_entries': len(entries),
               'protected_assets_changed': changed, 'protected_assets_checked': len(before)})
(OUT / 'unreal_sword_import.json').write_text(json.dumps(report, indent=2) + '\n')
assert not changed, ('existing assets changed', changed)
U.log('CAIRO SWORD IMPORT COMPLETE')
