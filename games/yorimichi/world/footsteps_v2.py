"""Native bodies for the footstep attenuation and FootstepSet, one declared package per job.

Scripts/import_footsteps.py runs everything at import time; these bodies never execute its top level or main.
They take its original definitions by name from the keyed source (``asset``, ``log``, ``build_attenuation`` and
``MATERIAL_SURFACES``) and run them with module globals rebuilt for the job. ``args.action`` selects
- ``attenuation``: /Game/Japan/Audio/A_Footstep, by the original build_attenuation;
- ``library``: /Game/Japan/Audio/DA_Footsteps, the UJapanFootstepSet main() fills, over each surface's
  declared finished waves in the original sorted-file order.
"""
import ast
import importlib.util
from pathlib import Path
import re
from types import SimpleNamespace

ORIGINAL = 'games/yorimichi/unreal/Scripts/import_footsteps.py'
SAVE = 'platform/studio/atelier/native_packages.py'
DEST = '/Game/Japan/Audio'
ATTENUATION = DEST + '/A_Footstep'
LIBRARY = DEST + '/DA_Footsteps'
DEFINITIONS = ('log', 'asset', 'build_attenuation')
SURFACE = re.compile(r'[a-z][a-z_]*\Z')
PIECE = re.compile(r'[A-Za-z0-9_.-]+\Z')


def _keyed(context, relative):
    path = Path(context.job_dir) / relative
    if path.is_symlink() or not path.is_file():
        raise ValueError('Footstep code is not staged keyed code: ' + relative)
    return path


def _save(context):
    spec = importlib.util.spec_from_file_location('atelier_footstep_native_packages', _keyed(context, SAVE))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.save


def original(context, unreal):
    """The original importer's named definitions and MATERIAL_SURFACES, without its top level."""
    path = _keyed(context, ORIGINAL)
    tree = ast.parse(path.read_text(), str(path))
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in DEFINITIONS]
    surfaces = [node.value for node in tree.body if isinstance(node, ast.Assign)
                and [getattr(target, 'id', None) for target in node.targets] == ['MATERIAL_SURFACES']]
    if sorted(node.name for node in nodes) != sorted(DEFINITIONS) or len(surfaces) != 1:
        raise ValueError('The original footstep importer lacks a required definition')
    save = _save(context)
    editor = unreal.EditorAssetLibrary
    # The original saves under yori.GAME/unreal/Content; the job's declared Content root replaces it.
    namespace = {'U': unreal, 'E': editor, 'AT': unreal.AssetToolsHelpers.get_asset_tools(), 'DEST': DEST,
                 'save_native_package': lambda asset, library, _content: save(asset, library, context.content),
                 'yori': SimpleNamespace(GAME=Path(context.content).parent.parent),
                 'MATERIAL_SURFACES': ast.literal_eval(surfaces[0])}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


def _owns(context, unreal, package):
    if list(context.outputs) != [package]:
        raise ValueError('Footstep job owns exactly its declared package: ' + package)
    if unreal.EditorAssetLibrary.does_asset_exist(package):
        raise ValueError('Footstep destination must be fresh: ' + package)


def _one(context, slot):
    if not isinstance(slot, str) or slot not in context.inputs or context.inputs[slot] is None:
        raise ValueError('Missing declared footstep input: ' + str(slot))
    packages = context.packages.get(slot)
    packages = [packages] if isinstance(packages, str) else packages
    if not isinstance(packages, (list, tuple)) or len(packages) != 1 or not str(packages[0]).startswith('/Game/'):
        raise ValueError('Footstep input must be exactly one declared package: ' + slot)
    return packages[0]


def _load(unreal, context, slot, cls):
    package = _one(context, slot)
    asset = unreal.EditorAssetLibrary.load_asset(package)
    if asset is None or asset.get_path_name().split('.', 1)[0] != package or not isinstance(asset, cls):
        raise ValueError('Declared footstep input did not load as expected: ' + package)
    return asset


def attenuation(context, unreal, args):
    _owns(context, unreal, ATTENUATION)
    built = original(context, unreal)['build_attenuation']()
    if built.get_path_name().split('.', 1)[0] != ATTENUATION:
        raise ValueError('build_attenuation did not author A_Footstep')
    settings = built.get_editor_property('attenuation')
    if (settings.get_editor_property('falloff_distance') != 2600.
            or settings.get_editor_property('db_attenuation_at_max') != -60.
            or settings.get_editor_property('enable_occlusion')):
        raise ValueError('A_Footstep lost its original attenuation settings')
    return built


def library(context, unreal, args):
    _owns(context, unreal, LIBRARY)
    namespace = original(context, unreal)
    surfaces = args['surfaces']
    if not isinstance(surfaces, dict) or not {'grass', 'leaves'} <= set(surfaces):
        raise ValueError('FootstepSet needs its grass default and leaves canopy surfaces')
    slots, banks, counts = {args['attenuation']}, {}, {}
    for surface, value in sorted(surfaces.items()):
        if (not SURFACE.fullmatch(surface) or not isinstance(value, dict) or set(value) != {'derived_items'}
                or set(value['derived_items']) != {'root', 'members'}):
            raise ValueError('footstep surface waves must be resolved before keying: ' + str(surface))
        members = value['derived_items']['members']
        if not isinstance(members, list) or not members:
            raise ValueError(surface + ': no finished footstep waves')
        rows = []
        for row in members:
            if (not isinstance(row, dict) or not {'piece', 'slot'} <= set(row) or set(row) - {'piece', 'slot', 'root'}
                    or not PIECE.fullmatch(str(row['piece'])) or row['slot'] in slots):
                raise ValueError(surface + ': invalid or duplicate footstep member')
            slots.add(row['slot'])
            rows.append(row)
        # main() imports sorted(folder.glob('*.wav')): order by original file name.
        waves = []
        for row in sorted(rows, key=lambda row: row['piece'] + '.wav'):
            wave = _load(unreal, context, row['slot'], unreal.SoundWave)
            if wave.get_path_name().split('.', 1)[0] != f"{DEST}/Footsteps/{surface}/{row['piece']}":
                raise ValueError(surface + ': footstep wave is outside its surface folder')
            waves.append(wave)
        banks[surface] = unreal.JapanFootstepBank(steps=waves)
        counts[surface] = len(waves)
    if set(context.inputs) != slots or set(context.packages) != slots:
        raise ValueError('FootstepSet inputs differ from the declared surface waves')
    factory = unreal.DataAssetFactory()
    factory.set_editor_property('data_asset_class', unreal.JapanFootstepSet)
    asset = namespace['asset']('DA_Footsteps', unreal.JapanFootstepSet, factory)
    if asset is None or asset.get_path_name().split('.', 1)[0] != LIBRARY:
        raise ValueError('DA_Footsteps not created')
    for key, value in dict(surfaces=banks,
                           material_surfaces={k: unreal.Name(v) for k, v in namespace['MATERIAL_SURFACES'].items()},
                           attenuation=_load(unreal, context, args['attenuation'], unreal.SoundAttenuation),
                           default_surface=unreal.Name('grass'),
                           canopy_surface=unreal.Name('leaves')).items():
        asset.set_editor_property(key, value)
    namespace['save_native_package'](asset, unreal.EditorAssetLibrary, None)
    saved = asset.get_editor_property('surfaces')
    if {str(k): len(v.get_editor_property('steps')) for k, v in saved.items()} != counts:
        raise ValueError('DA_Footsteps lost surface waves')
    namespace['log'](f'{sum(counts.values())} one-shots across {len(counts)} surfaces -> {LIBRARY}')
    return asset


ACTIONS = {'attenuation': attenuation, 'library': library}


def run(context):
    """@cc [owner:fontanierh,label:correctness] c3-footstep-owners
    Each job MUST author exactly its declared package with import_footsteps.py's own
    definitions and values, load only declared finished inputs, save through the
    exact-owned native save under the job Content root, and read the result back.
    It MUST NOT import waves, run the original top level or write its report.
    """
    import unreal
    params = context.params
    args = params.get('args')
    if set(params) != {'args', 'settings'} or params['settings'] != [] or not isinstance(args, dict):
        raise ValueError('Unsupported footstep parameters')
    expected = {'attenuation': {'action'}, 'library': {'action', 'attenuation', 'surfaces'}}
    if args.get('action') not in ACTIONS or set(args) != expected[args['action']]:
        raise ValueError('Unsupported footstep action')
    if args['action'] == 'attenuation' and (context.inputs or context.packages):
        raise ValueError('A_Footstep has no inputs')
    return ACTIONS[args['action']](context, unreal, args)
