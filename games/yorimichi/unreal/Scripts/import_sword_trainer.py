"""Import Kaede, the sword trainer (assets/characters/sword-trainer/export_unreal.py), into /Game/SwordTrainer.

    UnrealEditor-Cmd Yorimichi.uproject -run=pythonscript -script=Scripts/import_sword_trainer.py -unattended -nosplash -NullRHI -stdout

SK_SwordTrainer with its skeleton and physics asset, her materials in the game's character look (base colour with a
30% emissive fill, roughness 0.7, specular 0.3, as Cairo's), her own clips (A_Bow, A_Talk) and DA_SwordTrainerBase:
the mesh, the clips and her measurements. Her merged move set comes on top (unreal.sword_trainer_botw:
import_botw_moveset.py with BOTW_CHARACTER=sword-trainer copies the base into DA_SwordTrainer with every move).
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402
import json, sys
from pathlib import Path
import unreal as U
sys.path.insert(0, str(Path(__file__).resolve().parent))
import animation_compression

OUT = yori.OUT / 'sword-trainer'
CONFIG = json.loads((OUT / 'export.json').read_text())
DEST = '/Game/SwordTrainer'
E = U.EditorAssetLibrary; AT = U.AssetToolsHelpers.get_asset_tools(); M = U.MaterialEditingLibrary
E.make_directory(DEST)


def asset(name, cls, factory):
    path = DEST + '/' + name
    return E.load_asset(path) if E.does_asset_exist(path) else AT.create_asset(name, DEST, cls, factory)


materials = {}
for name, cfg in CONFIG['materials'].items():
    mat = asset(name, U.Material, U.MaterialFactoryNew())
    M.delete_all_material_expressions(mat)
    mat.set_editor_property('blend_mode', U.BlendMode.BLEND_OPAQUE)
    mat.set_editor_property('two_sided', cfg['two_sided'])
    mat.set_editor_property('used_with_skeletal_mesh', True)
    if cfg['texture']:
        task = U.AssetImportTask()
        for k, v in dict(filename=str(OUT / cfg['texture']), destination_path=DEST + '/Textures', automated=True, replace_existing=True, save=True).items():
            task.set_editor_property(k, v)
        AT.import_asset_tasks([task])
        node = M.create_material_expression(mat, U.MaterialExpressionTextureSample)
        node.set_editor_property('texture', E.load_asset(task.imported_object_paths[0]))
        assert M.connect_material_property(node, 'RGB', U.MaterialProperty.MP_BASE_COLOR)
    else:
        node = M.create_material_expression(mat, U.MaterialExpressionConstant3Vector)
        node.set_editor_property('constant', U.LinearColor(*cfg['base_color']))
        assert M.connect_material_property(node, '', U.MaterialProperty.MP_BASE_COLOR)
    fill = M.create_material_expression(mat, U.MaterialExpressionMultiply)   # the characters' small albedo fill
    fill.set_editor_property('const_b', .30)
    assert M.connect_material_expressions(node, 'RGB' if cfg['texture'] else '', fill, 'A')
    assert M.connect_material_property(fill, '', U.MaterialProperty.MP_EMISSIVE_COLOR)
    for field, prop in [('roughness', U.MaterialProperty.MP_ROUGHNESS), ('metallic', U.MaterialProperty.MP_METALLIC), ('specular', U.MaterialProperty.MP_SPECULAR)]:
        c = M.create_material_expression(mat, U.MaterialExpressionConstant)
        c.set_editor_property('r', cfg[field])
        assert M.connect_material_property(c, '', prop)
    M.recompile_material(mat)
    E.save_loaded_asset(mat)
    materials[name] = mat


def fbx(filename, name, skeleton=None, fps=30):
    task = U.AssetImportTask()
    for prop, value in dict(filename=str(OUT / 'fbx' / filename), destination_path=DEST, destination_name=name,
                            automated=True, replace_existing=True, save=True).items():
        task.set_editor_property(prop, value)
    options = U.FbxImportUI()
    for prop, value in dict(automated_import_should_detect_type=False, import_materials=False, import_textures=False,
                            import_as_skeletal=True, import_mesh=skeleton is None, import_animations=skeleton is not None).items():
        options.set_editor_property(prop, value)
    if skeleton:
        options.set_editor_property('skeleton', skeleton)
        options.set_editor_property('mesh_type_to_import', U.FBXImportType.FBXIT_ANIMATION)
        data = options.get_editor_property('anim_sequence_import_data')
        for k, v in dict(animation_length=U.FBXAnimationLengthImportType.FBXALIT_EXPORTED_TIME, use_default_sample_rate=False,
                         custom_sample_rate=fps, import_bone_tracks=True).items():
            data.set_editor_property(k, v)
    else:
        options.set_editor_property('mesh_type_to_import', U.FBXImportType.FBXIT_SKELETAL_MESH)
        options.set_editor_property('create_physics_asset', True)
        data = options.get_editor_property('skeletal_mesh_import_data')
        for k, v in dict(normal_import_method=U.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS, use_t0_as_ref_pose=False,
                         update_skeleton_reference_pose=True, import_meshes_in_bone_hierarchy=True).items():
            data.set_editor_property(k, v)
    data.set_editor_property('convert_scene', True)
    task.set_editor_property('options', options)
    AT.import_asset_tasks([task])
    imported = [E.load_asset(p) for p in task.get_editor_property('imported_object_paths')]
    result = next((a for a in imported if isinstance(a, U.AnimSequence if skeleton else U.SkeletalMesh)), None)
    assert result is not None, ('import failed', filename)
    return result


mesh = fbx('SwordTrainer.fbx', 'SK_SwordTrainer')
skeleton = mesh.skeleton
slots = list(mesh.materials)
for slot in slots:
    name = str(slot.get_editor_property('imported_material_slot_name'))
    assert name in materials, ('unknown material', name, list(materials))
    slot.set_editor_property('material_interface', materials[name])
mesh.set_editor_property('materials', slots)
E.save_loaded_asset(mesh)
editor = U.get_editor_subsystem(U.SkeletalMeshEditorSubsystem)
pending, bones = ['root'], []
while pending:
    bone = pending.pop()
    bones.append(bone)
    pending.extend(str(b) for b in editor.get_bone_children(mesh, bone))
assert set(bones) == set(CONFIG['bones'].values()), ('imported skeleton mismatch', sorted(set(bones) ^ set(CONFIG['bones'].values())))
clips = {}
for name, cfg in CONFIG['clips'].items():
    clip = fbx('A_' + name + '.fbx', 'A_' + name, skeleton, cfg['fps'])
    assert abs(clip.get_editor_property('sequence_length') - cfg['duration']) < .002, (name, clip.get_editor_property('sequence_length'), cfg)
    clip.set_editor_property('enable_root_motion', False)
    animation_compression.apply_to(clip)
    E.save_loaded_asset(clip)
    clips[name] = clip
factory = U.DataAssetFactory(); factory.set_editor_property('data_asset_class', U.WandererDefinition)
definition = asset('DA_SwordTrainerBase', U.WandererDefinition, factory)
for k, v in dict(mesh=mesh, actions=clips, use_authored_movement=True,
                 rest_ankle_heights=U.Vector2D(CONFIG['rest_ankles_cm']['L'], CONFIG['rest_ankles_cm']['R']),
                 sole_height=CONFIG['sole_cm'], camera_height=40.).items():
    definition.set_editor_property(k, v)
E.save_loaded_asset(definition)
E.save_loaded_asset(skeleton)
report = {'mesh': mesh.get_path_name(), 'bones': len(bones), 'materials': [str(s.material_slot_name) for s in slots],
          'vertices': editor.get_num_verts(mesh, 0), 'clips': {n: c.get_path_name() for n, c in clips.items()}, 'source': CONFIG['source_sha256']}
(OUT / 'unreal_import.json').write_text(json.dumps(report, indent=2) + '\n')
U.log('SWORD TRAINER IMPORT COMPLETE')
