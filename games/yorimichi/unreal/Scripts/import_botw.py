"""Import the BOTW characters (assets/characters/botw, export.json) into /Game/Botw/<Name>.

Each GLB goes through Interchange's glTF importer: the skinned mesh with its glTF materials and textures, the skeleton
and the clips at 30 fps. A colour variant imports its mesh onto its owner's skeleton and uses the owner's clips. The
assets are renamed SK_<Name>, SKEL_<Name> and A_<Name>_<Clip>, and the clips get the shared character compression.
Their glTF materials are reparented to M_BotwCharacter (or its masked twin), shaded like the game's own characters:
albedo with a small emissive fill of itself, no normal map, low specular. The glTF PBR defaults read pale and
lavender in the island's light.

A character with a skate bone map also becomes a rider (BotwRider.h, -rider=<Name>): DA_<Name>Rider, a
UWandererDefinition with a locomotion blend of its idle, walk and run clips and the bone map, on a mesh with CPU access
(the board's bail clearance reads its vertices).

Writes Content/Data/botw/roster.json, which the game's ABotwCreature reads (mesh and clip paths, roles, speeds, height),
and build/yorimichi/botw/unreal_import.json. The whole /Game/Botw folder is rebuilt, so a character removed from the
roster disappears.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import json, sys, time
from pathlib import Path
import unreal as U
sys.path.insert(0, str(Path(__file__).resolve().parent))
import animation_compression

OUT = yori.OUT / 'botw'
CONFIG = json.loads((OUT / 'export.json').read_text())
DEST = '/Game/Botw'
CONTENT = Path(__file__).resolve().parents[1] / 'Content'
DATA = CONTENT / 'Data' / 'botw'
MESH_YAW = -90.   # glTF faces +Z, which Interchange turns into Unreal +Y; the actor faces +X
E = U.EditorAssetLibrary; AT = U.AssetToolsHelpers.get_asset_tools(); M = U.MaterialEditingLibrary
REGISTRY = U.AssetRegistryHelpers.get_asset_registry()


def pipelines(skeleton=None):
    generic = U.InterchangeGenericAssetsPipeline()
    mesh = generic.get_editor_property('mesh_pipeline')
    mesh.set_editor_property('import_static_meshes', False)
    mesh.set_editor_property('import_skeletal_meshes', True)
    mesh.set_editor_property('create_physics_asset', False)
    mesh.set_editor_property('import_morph_targets', False)
    textures = generic.get_editor_property('material_pipeline').get_editor_property('texture_pipeline')
    textures.set_editor_property('allow_non_power_of_two', True)   # Sidon's body maps
    animation = generic.get_editor_property('animation_pipeline')
    animation.set_editor_property('import_animations', skeleton is None)
    animation.set_editor_property('use30_hz_to_bake_bone_animation', True)
    if skeleton is not None:
        generic.get_editor_property('common_skeletal_meshes_and_animations_properties').set_editor_property('skeleton', skeleton)
    stack = U.InterchangePipelineStackOverride()
    stack.add_pipeline(generic)
    stack.add_pipeline(U.InterchangeGLTFPipeline())
    return stack


def master(name, masked):
    """The game's character look for a BOTW material: its albedo, a 0.3 albedo fill (as import_cairo.py) plus its own
    emissive map, roughness .7, specular .3; masked twin cuts at the glTF alpha cutoff."""
    mat = AT.create_asset(name, DEST, U.Material, U.MaterialFactoryNew())
    mat.set_editor_property('blend_mode', U.BlendMode.BLEND_MASKED if masked else U.BlendMode.BLEND_OPAQUE)
    mat.set_editor_property('opacity_mask_clip_value', .5)     # the mask below is alpha - cutoff + .5
    mat.set_editor_property('two_sided', True)
    mat.set_editor_property('used_with_skeletal_mesh', True)
    expression = lambda cls, x, y: M.create_material_expression(mat, cls, x, y)
    base = expression(U.MaterialExpressionTextureSampleParameter2D, -900, 0)
    base.set_editor_property('parameter_name', 'BaseColorTexture')
    base.set_editor_property('texture', E.load_asset('/Engine/EngineResources/WhiteSquareTexture'))
    assert M.connect_material_property(base, 'RGB', U.MaterialProperty.MP_BASE_COLOR)
    fill = expression(U.MaterialExpressionMultiply, -500, 200)
    fill.set_editor_property('const_b', .30)
    assert M.connect_material_expressions(base, 'RGB', fill, 'A')
    glow = expression(U.MaterialExpressionTextureSampleParameter2D, -900, 400)
    glow.set_editor_property('parameter_name', 'EmissiveTexture')
    glow.set_editor_property('texture', E.load_asset('/Engine/EngineResources/Black'))
    factor = expression(U.MaterialExpressionVectorParameter, -900, 650)
    factor.set_editor_property('parameter_name', 'EmissiveFactor')
    factor.set_editor_property('default_value', U.LinearColor(0, 0, 0, 0))
    rgb = expression(U.MaterialExpressionComponentMask, -650, 650)
    for channel in 'rgb':
        rgb.set_editor_property(channel, True)
    assert M.connect_material_expressions(factor, '', rgb, '')
    lit = expression(U.MaterialExpressionMultiply, -500, 450)
    assert M.connect_material_expressions(glow, 'RGB', lit, 'A')
    assert M.connect_material_expressions(rgb, '', lit, 'B')
    emissive = expression(U.MaterialExpressionAdd, -300, 300)
    assert M.connect_material_expressions(fill, '', emissive, 'A')
    assert M.connect_material_expressions(lit, '', emissive, 'B')
    assert M.connect_material_property(emissive, '', U.MaterialProperty.MP_EMISSIVE_COLOR)
    for value, prop in [(.7, U.MaterialProperty.MP_ROUGHNESS), (0., U.MaterialProperty.MP_METALLIC), (.3, U.MaterialProperty.MP_SPECULAR)]:
        node = expression(U.MaterialExpressionConstant, -300, 600)
        node.set_editor_property('r', value)
        assert M.connect_material_property(node, '', prop)
    if masked:
        cutoff = expression(U.MaterialExpressionScalarParameter, -900, 900)
        cutoff.set_editor_property('parameter_name', 'AlphaCutoff')
        cutoff.set_editor_property('default_value', .5)
        cut = expression(U.MaterialExpressionSubtract, -600, 850)
        assert M.connect_material_expressions(base, 'A', cut, 'A')
        assert M.connect_material_expressions(cutoff, '', cut, 'B')
        mask = expression(U.MaterialExpressionAdd, -400, 850)
        mask.set_editor_property('const_b', .5)
        assert M.connect_material_expressions(cut, '', mask, 'A')
        assert M.connect_material_property(mask, '', U.MaterialProperty.MP_OPACITY_MASK)
    M.recompile_material(mat)
    E.save_loaded_asset(mat, False)
    return mat


def restyle(material, masters):
    """Reparent an Interchange glTF instance to the BOTW master, keeping its albedo, emissive and alpha cutoff."""
    masked = 'Opaque' not in material.get_editor_property('parent').get_name()
    keep = {
        'BaseColorTexture': M.get_material_instance_texture_parameter_value(material, 'BaseColorTexture'),
        'EmissiveTexture': M.get_material_instance_texture_parameter_value(material, 'EmissiveTexture'),
        'EmissiveFactor': M.get_material_instance_vector_parameter_value(material, 'EmissiveFactor'),
        'AlphaCutoff': M.get_material_instance_scalar_parameter_value(material, 'AlphaCutoff'),
    }
    M.clear_all_material_instance_parameters(material)
    M.set_material_instance_parent(material, masters[masked])
    for name in ('BaseColorTexture', 'EmissiveTexture'):
        if keep[name] and keep[name].get_name() not in ('WhiteSquareTexture', 'Black'):
            M.set_material_instance_texture_parameter_value(material, name, keep[name])
    M.set_material_instance_vector_parameter_value(material, 'EmissiveFactor', keep['EmissiveFactor'])
    if masked:
        M.set_material_instance_scalar_parameter_value(material, 'AlphaCutoff', keep['AlphaCutoff'] or .5)
    M.update_material_instance(material)
    E.save_loaded_asset(material, False)
    return 'masked' if masked else 'opaque'


def assets_in(folder):
    found = {}
    for data in REGISTRY.get_assets_by_path(folder, recursive=True):
        found.setdefault(str(data.asset_class_path.asset_name), []).append(str(data.package_name))
    return found


def rename(path, name):
    folder = path.rsplit('/', 1)[0]
    target = f'{folder}/{name}'
    if path != target:
        assert E.rename_asset(path, target), ('rename failed', path, target)
    return target


def make_rider(name, folder, character, mesh, skeleton, clips):
    """DA_<Name>Rider: the player definition for a character with a skate bone map. Returns its path."""
    U.SkeletalMeshEditorSubsystem.set_allow_cpu_access(mesh, True)
    roles, speeds = character['roles'], character['speeds']
    sequence = lambda role: E.load_asset(clips[roles[role]]['path'])
    walk, run = speeds['walk'] * 100., speeds['run'] * 100.
    # A variant shares its owner's blend space.
    blend_path = f"{DEST}/{character['skeleton']}/BS_{character['skeleton']}Locomotion"
    if E.does_asset_exist(blend_path):
        blend = E.load_asset(blend_path)
    else:
        factory = U.BlendSpaceFactory1D()
        factory.set_editor_property('target_skeleton', skeleton)
        blend = AT.create_asset(f"BS_{name}Locomotion", folder, U.BlendSpace1D, factory)
        params = list(blend.get_editor_property('blend_parameters'))
        for key, value in dict(display_name='Speed (cm/s)', min=0., max=run).items():
            params[0].set_editor_property(key, value)
        blend.set_editor_property('blend_parameters', params)
        blend.set_editor_property('scale_animation', True)
        smoothing = list(blend.get_editor_property('interpolation_param'))
        smoothing[0].set_editor_property('interpolation_time', .12)
        blend.set_editor_property('interpolation_param', smoothing)
        assert U.WandererContentLibrary.configure_blend_space(
            blend, [sequence('idle'), sequence('walk'), sequence('run')], [0., walk, run])
        E.save_loaded_asset(blend, False)
    factory = U.DataAssetFactory()
    factory.set_editor_property('data_asset_class', U.WandererDefinition)
    definition = AT.create_asset(f'DA_{name}Rider', folder, U.WandererDefinition, factory)
    bones = {U.Name(role): U.Name(bone) for role, bone in character['skate'].items()}
    for key, value in dict(mesh=mesh, locomotion=blend, crouching=blend, actions={'Idle': sequence('idle')},
                           skate_bones=bones, skate_board_scale=character.get('board', 1.), camera_height=max(35., character['height'] * 100. - 140.),
                           walk_speed=walk, jog_speed=walk, run_speed=run, crouch_speed=walk * .5).items():
        definition.set_editor_property(key, value)
    E.save_loaded_asset(definition, False)
    return definition.get_path_name()


def import_character(character, owners, masters):
    name = character['name']
    folder = f'{DEST}/{name}'
    E.make_directory(folder)
    owner = owners.get(character['skeleton']) if character['skeleton'] != name else None
    task = U.AssetImportTask()
    for key, value in dict(filename=character['glb'], destination_path=folder, automated=True, replace_existing=True,
                           save=True).items():
        task.set_editor_property(key, value)
    task.set_editor_property('options', pipelines(owner['skeleton_asset'] if owner else None))
    started = time.time()
    AT.import_asset_tasks([task])
    found = assets_in(folder)
    meshes = found.get('SkeletalMesh', [])
    assert len(meshes) == 1, (name, 'expected one skeletal mesh', found)
    # The skeleton first: the mesh is saved after it, so its package names the skeleton's final path.
    if owner:
        assert not found.get('Skeleton'), (name, 'imported its own skeleton', found['Skeleton'])
        skeleton = owner['skeleton_asset']
    else:
        skeleton = E.load_asset(rename(found['Skeleton'][0], f'SKEL_{name}'))
    mesh_path = rename(meshes[0], f'SK_{name}')
    mesh = E.load_asset(mesh_path)
    assert mesh.skeleton == skeleton, (name, mesh.skeleton.get_path_name(), skeleton.get_path_name())
    # Interchange names a clip <file stem><glTF animation name>.
    imported = {Path(path).name[len(name):]: path for path in found.get('AnimSequence', [])}
    clips = {}
    for clip in character['clips']:
        path = imported.get(clip['name'])
        assert path, (name, 'missing clip', clip['name'], sorted(imported)[:10])
        sequence = E.load_asset(rename(path, f"A_{name}_{clip['name']}"))
        assert sequence.get_editor_property('skeleton') == skeleton
        length = sequence.get_editor_property('sequence_length')
        assert abs(length - clip['frames'] / CONFIG['fps']) < .002, (name, clip['name'], length, clip['frames'])
        sequence.set_editor_property('enable_root_motion', False)
        animation_compression.apply_to(sequence)
        E.save_loaded_asset(sequence)
        clips[clip['name']] = {'path': sequence.get_path_name(), 'length': round(length, 4), 'loop': clip['loop'],
                               'travel_cm': [round(v * 100. * character['scale'], 2) for v in clip['travel']]}
    unused = set(imported) - {clip['name'] for clip in character['clips']}
    assert not unused, (name, 'unexpected clips', sorted(unused)[:10])
    all_clips = clips if not owner else owner['record']['clips']
    looks = [restyle(E.load_asset(path), masters) for path in found.get('MaterialInstanceConstant', [])]
    rider = make_rider(name, folder, character, mesh, skeleton, all_clips) if character.get('skate') else None
    E.save_loaded_asset(skeleton, False)
    E.save_loaded_asset(mesh, False)
    # Saved unconditionally: a mesh not dirtied by the skeleton's rename would keep the old skeleton path on disk.
    saved = (CONTENT / Path(mesh_path).relative_to('/Game')).with_suffix('.uasset').read_bytes()
    assert skeleton.get_name().encode() in saved, (name, 'the saved mesh does not name', skeleton.get_name())
    bounds = mesh.get_bounds()
    record = {
        'name': name, 'label': character['label'], 'kind': character['kind'], 'mesh': mesh.get_path_name(),
        'skeleton': skeleton.get_path_name(), 'mesh_yaw': MESH_YAW, 'scale': character['scale'],
        'height_cm': round(character['height'] * 100., 1),
        'radius_cm': round(min(bounds.box_extent.x, bounds.box_extent.y) * .5 * character['scale'], 1),
        'speeds_cm': {gait: round(speed * 100., 1) for gait, speed in character['speeds'].items()},
        'clips': all_clips, 'roles': character['roles'], 'rider': rider,
        'materials': [str(slot.material_slot_name) for slot in mesh.materials], 'looks': looks,
        'seconds': round(time.time() - started, 1),
    }
    return {'record': record, 'skeleton_asset': skeleton}


if E.does_directory_exist(DEST):
    E.delete_directory(DEST)
E.make_directory(DEST)
masters = {False: master('M_BotwCharacter', False), True: master('M_BotwCharacterMasked', True)}
done = {}
ordered = [c for c in CONFIG['characters'] if c['skeleton'] == c['name']] + \
          [c for c in CONFIG['characters'] if c['skeleton'] != c['name']]
for character in ordered:
    done[character['name']] = import_character(character, done, masters)
    record = done[character['name']]['record']
    U.log(f"BOTW {record['name']}: {len(record['clips'])} clips, {record['height_cm']} cm, {record['seconds']} s")

roster = [done[c['name']]['record'] for c in CONFIG['characters']]
DATA.mkdir(parents=True, exist_ok=True)
(DATA / 'roster.json').write_text(json.dumps({'characters': roster}, indent=1) + '\n')
(OUT / 'unreal_import.json').write_text(json.dumps({'characters': roster}, indent=1) + '\n')
U.log('BOTW IMPORT COMPLETE: %d characters, %d clips' % (len(roster), sum(len(c['clips']) for c in CONFIG['characters'])))
