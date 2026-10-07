"""Import Modori, the rival (assets/characters/modori/export_unreal.py), into /Game/Modori.

    UnrealEditor-Cmd Yorimichi.uproject -run=pythonscript -script=Scripts/import_modori.py -unattended -nosplash -NullRHI -stdout

SK_Modori (body and coat, one skeleton) with its physics asset and CPU access (the skating retargeter samples the
rider's skin), the coat's cloth_pin mask kept as its vertex colours, both materials in the game's character look
(base colour with a 30% emissive fill; matte, as his source) and DA_ModoriBase: the mesh and his measurements. His
merged move set comes on top (unreal.modori_botw: import_cairo_botw.py with BOTW_CHARACTER=modori copies the base into
DA_Modori with every move).
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402
import json, sys
from pathlib import Path
import unreal as U
sys.path.insert(0, str(Path(__file__).resolve().parent))
import animation_compression

OUT = yori.OUT / 'modori'
CONFIG = json.loads((OUT / 'export.json').read_text())
DEST = '/Game/Modori'
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
    mat.set_editor_property('used_with_clothing', True)   # the coat simulates as cloth (without it the engine draws the default material)
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
                         update_skeleton_reference_pose=True, import_meshes_in_bone_hierarchy=True,
                         vertex_color_import_option=U.VertexColorImportOption.REPLACE).items():
            data.set_editor_property(k, v)
    data.set_editor_property('convert_scene', True)
    task.set_editor_property('options', options)
    AT.import_asset_tasks([task])
    imported = [E.load_asset(p) for p in task.get_editor_property('imported_object_paths')]
    result = next((a for a in imported if isinstance(a, U.AnimSequence if skeleton else U.SkeletalMesh)), None)
    assert result is not None, ('import failed', filename)
    return result


mesh = fbx('Modori.fbx', 'SK_Modori')
# The skating retargeter samples the rider skin for bail contact clearance.
U.SkeletalMeshEditorSubsystem.set_allow_cpu_access(mesh, True)
skeleton = mesh.skeleton
slots = list(mesh.materials)
for slot in slots:
    name = str(slot.get_editor_property('imported_material_slot_name'))
    assert name in materials, ('unknown material', name, list(materials))
    slot.set_editor_property('material_interface', materials[name])
mesh.set_editor_property('materials', slots)
# The coat's lower part is Chaos cloth (YorimichiCloth.cpp): pinned where cloth_pin is 1, free up to MAX_DISTANCE below
# the hips, colliding with his physics asset. The import rebuilds the mesh, so the cloth is made again every time.
MAX_DISTANCE = 30.
# It collides with capsules on his hips, spine, thighs and shins sized from his skin (export.json cloth.colliders), a
# physics asset of its own: SK_Modori keeps none, so the skating rider still fits its bodies to his skin.
capsules = CONFIG['cloth']['colliders']
colliders = U.YorimichiClothLibrary.make_capsule_colliders(mesh, DEST + '/PA_Modori_Cloth', [c['bone'] for c in capsules],
                                                           [c['from'] for c in capsules], [c['to'] for c in capsules],
                                                           [c['radius_cm'] for c in capsules])
assert colliders, 'the coat colliders could not be built (see the log)'
E.save_loaded_asset(colliders)
cloth = U.YorimichiClothLibrary.add_section_cloth(mesh, 'M_' + CONFIG['cloth']['mesh'], MAX_DISTANCE, colliders, True)
assert cloth, 'the coat cloth could not be built (see the log)'
U.log('MODORI CLOTH: ' + cloth)
U.log('MODORI CLOTH DATA: ' + U.YorimichiClothLibrary.describe_cloth(mesh))
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
definition = asset('DA_ModoriBase', U.WandererDefinition, factory)
for k, v in dict(mesh=mesh, actions=clips, use_authored_movement=True,
                 rest_ankle_heights=U.Vector2D(CONFIG['rest_ankles_cm']['L'], CONFIG['rest_ankles_cm']['R']),
                 sole_height=CONFIG['sole_cm'], camera_height=42.).items():
    definition.set_editor_property(k, v)
E.save_loaded_asset(definition)
E.save_loaded_asset(skeleton)
report = {'mesh': mesh.get_path_name(), 'cloth': cloth, 'bones': len(bones), 'materials': [str(s.material_slot_name) for s in slots],
          'vertices': editor.get_num_verts(mesh, 0), 'clips': {n: c.get_path_name() for n, c in clips.items()}, 'source': CONFIG['source_sha256']}
(OUT / 'unreal_import.json').write_text(json.dumps(report, indent=2) + '\n')
U.log('MODORI IMPORT COMPLETE')
