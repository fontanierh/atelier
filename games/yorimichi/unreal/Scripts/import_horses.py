"""Import the hippodrome's horses and riders (assets/characters/horses, export.json) into /Game/Horses/<Name>.

The BOTW characters' import (import_botw.py) for the horse roster: each GLB goes through Interchange's glTF importer,
a coat variant imports its mesh onto the horse's skeleton and uses its clips, and the assets are renamed SK_<Name>,
SKEL_<Name> and A_<Name>_<Clip> with the shared character compression. Materials are reparented onto import_botw.py's
M_BotwCharacter (or its masked twin), so horses and riders are shaded like every other BOTW character.

Writes Content/Data/horses/roster.json, which the race (HorseRace.h) reads: mesh and clip paths, roles, gait speeds and
heights, and build/yorimichi/horses/unreal_import.json. The whole /Game/Horses folder is rebuilt.

When the Cairo rider export is there (assets/characters/horses/cairo_rider.py), its FBX clips import onto
/Game/Cairo/SK_Cairo's skeleton as /Game/Horses/RiderCairo/A_RiderCairo_<Clip>, and the roster gains RiderCairo: the
player in the saddle, in the races and riding about the world.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import json, sys, time
from pathlib import Path
import unreal as U
sys.path.insert(0, str(Path(__file__).resolve().parent))
import animation_compression

OUT = yori.OUT / 'horses'
CONFIG = json.loads((OUT / 'export.json').read_text())
DEST = '/Game/Horses'
MASTERS = '/Game/Botw'
CONTENT = Path(__file__).resolve().parents[1] / 'Content'
DATA = CONTENT / 'Data' / 'horses'
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
    textures.set_editor_property('allow_non_power_of_two', True)
    animation = generic.get_editor_property('animation_pipeline')
    animation.set_editor_property('import_animations', skeleton is None)
    animation.set_editor_property('use30_hz_to_bake_bone_animation', True)
    if skeleton is not None:
        generic.get_editor_property('common_skeletal_meshes_and_animations_properties').set_editor_property('skeleton', skeleton)
    stack = U.InterchangePipelineStackOverride()
    stack.add_pipeline(generic)
    stack.add_pipeline(U.InterchangeGLTFPipeline())
    return stack


def restyle(material, masters):
    """Reparent an Interchange glTF instance to the BOTW master, keeping its albedo and alpha cutoff."""
    masked = 'Opaque' not in material.get_editor_property('parent').get_name()
    albedo = M.get_material_instance_texture_parameter_value(material, 'BaseColorTexture')
    cutoff = M.get_material_instance_scalar_parameter_value(material, 'AlphaCutoff')
    M.clear_all_material_instance_parameters(material)
    M.set_material_instance_parent(material, masters[masked])
    if albedo and albedo.get_name() != 'WhiteSquareTexture':
        M.set_material_instance_texture_parameter_value(material, 'BaseColorTexture', albedo)
    if masked:
        M.set_material_instance_scalar_parameter_value(material, 'AlphaCutoff', cutoff or .5)
    M.update_material_instance(material)
    E.save_loaded_asset(material, False)
    return 'masked' if masked else 'opaque'


def assets_in(folder):
    found = {}
    for data in REGISTRY.get_assets_by_path(folder, recursive=True):
        found.setdefault(str(data.asset_class_path.asset_name), []).append(str(data.package_name))
    return found


def rename(path, name):
    target = f"{path.rsplit('/', 1)[0]}/{name}"
    if path != target:
        assert E.rename_asset(path, target), ('rename failed', path, target)
    return target


def import_glb(path, folder, options):
    task = U.AssetImportTask()
    for key, value in dict(filename=path, destination_path=folder, automated=True, replace_existing=True,
                           save=True).items():
        task.set_editor_property(key, value)
    task.set_editor_property('options', options)
    AT.import_asset_tasks([task])
    return assets_in(folder)


def import_character(character, owners, masters):
    name = character['name']
    folder = f'{DEST}/{name}'
    E.make_directory(folder)
    owner = owners.get(character['skeleton']) if character['skeleton'] != name else None
    started = time.time()
    found = import_glb(str(OUT / character['glb']), folder,   # relative to OUT (older exports: absolute)
                       pipelines(owner['skeleton_asset'] if owner else None))
    meshes = found.get('SkeletalMesh', [])
    assert len(meshes) == 1, (name, 'expected one skeletal mesh', found)
    if owner:
        assert not found.get('Skeleton'), (name, 'imported its own skeleton', found['Skeleton'])
        skeleton = owner['skeleton_asset']
    else:
        skeleton = E.load_asset(rename(found['Skeleton'][0], f'SKEL_{name}'))
    mesh_path = rename(meshes[0], f'SK_{name}')
    mesh = E.load_asset(mesh_path)
    assert mesh.skeleton == skeleton, (name, mesh.skeleton.get_path_name(), skeleton.get_path_name())
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
    looks = [restyle(E.load_asset(path), masters) for path in found.get('MaterialInstanceConstant', [])]
    E.save_loaded_asset(skeleton, False)
    E.save_loaded_asset(mesh, False)
    saved = (CONTENT / Path(mesh_path).relative_to('/Game')).with_suffix('.uasset').read_bytes()
    assert skeleton.get_name().encode() in saved, (name, 'the saved mesh does not name', skeleton.get_name())
    record = {
        'name': name, 'label': character['label'], 'kind': character['kind'], 'coat': character.get('coat', ''),
        'mesh': mesh.get_path_name(), 'skeleton': skeleton.get_path_name(), 'mesh_yaw': MESH_YAW,
        'scale': character['scale'], 'height_cm': round(character['height'] * 100., 1),
        'speeds_cm': {gait: round(speed * 100., 1) for gait, speed in character['speeds'].items()},
        'clips': clips if not owner else owner['record']['clips'], 'roles': character['roles'],
        'materials': [str(slot.material_slot_name) for slot in mesh.materials], 'looks': looks,
        'seconds': round(time.time() - started, 1),
    }
    return {'record': record, 'skeleton_asset': skeleton}


def import_cairo():
    """RiderCairo: cairo_rider.py's clips on Cairo's own mesh and skeleton (the FBX import of import_cairo_botw.py)."""
    report = json.loads((OUT / 'cairo' / 'export.json').read_text())
    mesh = E.load_asset('/Game/Cairo/SK_Cairo')
    assert mesh, 'run unreal.cairo first: RiderCairo rides on its mesh'
    skeleton, folder, started = mesh.skeleton, f'{DEST}/RiderCairo', time.time()
    E.make_directory(folder)
    clips = {}
    for name, clip in report['clips'].items():
        task = U.AssetImportTask()
        for key, value in dict(filename=str(OUT / 'cairo' / 'fbx' / f'A_{name}.fbx'), destination_path=folder,
                               destination_name=f'A_RiderCairo_{name}', automated=True, replace_existing=True,
                               save=True).items():
            task.set_editor_property(key, value)
        options = U.FbxImportUI()
        for key, value in dict(automated_import_should_detect_type=False, import_materials=False, import_textures=False,
                               import_as_skeletal=True, import_mesh=False, import_animations=True, skeleton=skeleton,
                               mesh_type_to_import=U.FBXImportType.FBXIT_ANIMATION).items():
            options.set_editor_property(key, value)
        data = options.get_editor_property('anim_sequence_import_data')
        for key, value in dict(animation_length=U.FBXAnimationLengthImportType.FBXALIT_EXPORTED_TIME,
                               use_default_sample_rate=False, custom_sample_rate=report['fps'], import_bone_tracks=True,
                               convert_scene=True).items():
            data.set_editor_property(key, value)
        task.set_editor_property('options', options)
        AT.import_asset_tasks([task])
        sequence = next((a for a in (E.load_asset(p) for p in task.get_editor_property('imported_object_paths'))
                         if isinstance(a, U.AnimSequence)), None)
        assert sequence and sequence.get_editor_property('skeleton') == skeleton, ('RiderCairo import failed', name)
        length = sequence.get_editor_property('sequence_length')
        assert abs(length - clip['duration']) < .04, ('RiderCairo', name, length, clip['duration'])
        sequence.set_editor_property('enable_root_motion', False)
        animation_compression.apply_to(sequence)
        E.save_loaded_asset(sequence)
        clips[name] = {'path': sequence.get_path_name(), 'length': round(length, 4), 'loop': clip['loop'],
                       'travel_cm': [0., 0., 0.]}
    # SK_Cairo faces +X and is authored in centimetres: no turn and no scale, unlike the glTF characters.
    return {'name': 'RiderCairo', 'label': 'Cairo', 'kind': 'hero', 'coat': '', 'mesh': mesh.get_path_name(),
            'skeleton': skeleton.get_path_name(), 'mesh_yaw': 0., 'scale': 1., 'height_cm': 0.,
            'speeds_cm': {}, 'clips': clips, 'roles': report['roles'],
            'materials': [str(slot.material_slot_name) for slot in mesh.materials], 'looks': [],
            'seconds': round(time.time() - started, 1)}


masters = {masked: E.load_asset(f"{MASTERS}/{'M_BotwCharacterMasked' if masked else 'M_BotwCharacter'}")
           for masked in (False, True)}
assert all(masters.values()), 'run unreal.botw first: its M_BotwCharacter masters shade the horses'
if E.does_directory_exist(DEST):
    E.delete_directory(DEST)
E.make_directory(DEST)
done = {}
ordered = [c for c in CONFIG['characters'] if c['skeleton'] == c['name']] + \
          [c for c in CONFIG['characters'] if c['skeleton'] != c['name']]
for character in ordered:
    done[character['name']] = import_character(character, done, masters)
    record = done[character['name']]['record']
    U.log(f"HORSES {record['name']}: {len(record['clips'])} clips, {record['height_cm']} cm, {record['seconds']} s")

roster = [done[c['name']]['record'] for c in CONFIG['characters']]
if (OUT / 'cairo' / 'export.json').exists():
    roster.append(import_cairo())
    U.log(f"HORSES RiderCairo: {len(roster[-1]['clips'])} clips, {roster[-1]['seconds']} s")
DATA.mkdir(parents=True, exist_ok=True)
(DATA / 'roster.json').write_text(json.dumps({'characters': roster}, indent=1) + '\n')
(OUT / 'unreal_import.json').write_text(json.dumps({'characters': roster}, indent=1) + '\n')
U.log('HORSES IMPORT COMPLETE: %d characters, %d clips' % (len(roster), sum(len(c['clips']) for c in roster)))
