"""Author one playable character's pawn, BP_<Name>, from declared inputs (Scripts/character_pawn.py's body).

The class defaults and component templates arrive as authored parameters, computed by the declaration from
the committed character.toml through assets/characters/pipeline/definition.py exactly as character_pawn.py
computes them. The merged move set is a declared native input and the move record (adventure.json) a
declared data input. The registration record is written by a separate unit after this one succeeds.
"""
import json
from pathlib import Path
import re

PACKAGE = re.compile(r'/Game/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+\Z')
ARGS = {'character', 'blueprint', 'pawn', 'definition', 'defaults', 'components', 'inputs'}
COMPONENTS = {'capsule_component', 'character_movement', 'mesh'}


def _package(value):
    if not isinstance(value, str) or not PACKAGE.fullmatch(value):
        raise ValueError('Expected a canonical declared /Game package')
    return value


def object_path(package):
    return f"{package}.{package.rsplit('/', 1)[1]}"


def _value(unreal, value):
    if isinstance(value, dict):
        if set(value) != {'unreal_type', 'args'} or value['unreal_type'] != 'Vector' or len(value['args']) != 3:
            raise ValueError('Unsupported authored pawn value')
        return unreal.Vector(*(float(v) for v in value['args']))
    return value


def same(unreal, a, b):
    """character_pawn.same: vectors and floats within 1e-4, lists by their string members."""
    if isinstance(b, unreal.Vector):
        return abs(a.x - b.x) + abs(a.y - b.y) + abs(a.z - b.z) < 1e-4
    if isinstance(b, float):
        return abs(a - b) < 1e-4
    if isinstance(b, list):
        return [str(x) for x in a] == b
    return a == b


def apply(cdo, defaults, components):
    """character_pawn.apply: class defaults, then the inherited component templates."""
    for key, value in defaults.items():
        cdo.set_editor_property(key, value)
    for component, values in components.items():
        template = cdo.get_editor_property(component)
        for key, value in values.items():
            template.set_editor_property(key, value)


def check(unreal, cdo, defaults, components, blueprint):
    """character_pawn.check: every value read back from the saved class."""
    wrong = [(k, cdo.get_editor_property(k), v) for k, v in defaults.items()
             if not same(unreal, cdo.get_editor_property(k), v)]
    for component, values in components.items():
        template = cdo.get_editor_property(component)
        wrong += [(f'{component}.{k}', template.get_editor_property(k), v) for k, v in values.items()
                  if not same(unreal, template.get_editor_property(k), v)]
    if wrong:
        raise ValueError(f'{blueprint}: class defaults differ from [game]: {wrong}')


def _single(context, slot):
    if not isinstance(slot, str) or slot not in context.inputs or context.inputs[slot] is None:
        raise ValueError('Missing declared pawn input: ' + str(slot))
    return context.inputs[slot]


def _record(context, slot):
    """The move record must be present, as character_pawn.py asserts before it builds the pawn."""
    root = Path(_single(context, slot))
    job = Path(context.job_dir)
    if not root.is_absolute() or not root.resolve().is_relative_to(job.resolve()) or root.is_symlink():
        raise ValueError('Pawn move record must be a job-local declared input')
    path = root / 'adventure.json' if root.is_dir() else root
    if path.name != 'adventure.json' or path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError('Pawn move record adventure.json is absent')
    if not isinstance(json.loads(path.read_bytes()), dict):
        raise ValueError('Pawn move record is not a JSON object')


def run(context):
    """@cc [owner:fontanierh,label:correctness] c3-playable-pawn-author
    The body MUST create only the original BP_<Name> at its sole declared package as a
    Blueprint of AMoverCharacter, after its declared merged move set loads and its move
    record is present; apply the authored class defaults and component templates,
    compile, save, read every value back and require the generated class path the
    tools name. It MUST NOT write the registration record or touch any other package.
    """
    import unreal
    params = context.params
    args = params.get('args')
    if (set(params) - {'args', 'settings', 'input_roots'} or not isinstance(args, dict) or set(args) != ARGS
            or not isinstance(args['inputs'], dict) or set(args['inputs']) != {'definition', 'adventure'}
            or not isinstance(args['defaults'], dict) or not isinstance(args['components'], dict)
            or set(args['components']) != COMPONENTS):
        raise ValueError('Unexpected pawn author parameters')
    blueprint = _package(args['blueprint'])
    if list(context.outputs) != [blueprint]:
        raise ValueError('Pawn author owns exactly its BP_<Name> package')
    if args['pawn'] != object_path(blueprint) + '_C':
        raise ValueError('Pawn generated class differs from its Blueprint package')
    library = unreal.EditorAssetLibrary
    slot = args['inputs']['definition']
    packages = context.packages.get(slot)
    packages = [packages] if isinstance(packages, str) else packages
    _single(context, slot)
    definition = _package(args['definition'].split('.', 1)[0])
    if args['definition'] != object_path(definition) or list(packages or ()) != [definition]:
        raise ValueError('Pawn move set input differs from its merged definition package')
    loaded = library.load_asset(definition)
    if loaded is None or loaded.get_path_name() != args['definition']:
        raise ValueError('Declared merged move set did not load: ' + definition)
    _record(context, args['inputs']['adventure'])
    if args['defaults'].get('definition_path') != args['definition']:
        raise ValueError('Pawn defaults name another move set')
    defaults = {key: _value(unreal, value) for key, value in args['defaults'].items()}
    components = {name: {key: _value(unreal, value) for key, value in values.items()}
                  for name, values in args['components'].items()}
    if library.does_asset_exist(blueprint):
        raise ValueError('Pawn destination must be fresh: ' + blueprint)
    factory = unreal.BlueprintFactory()
    factory.set_editor_property('parent_class', unreal.MoverCharacter.static_class())
    path, name = blueprint.rsplit('/', 1)
    bp = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, path, unreal.Blueprint, factory)
    if not bp or bp.get_path_name() != object_path(blueprint):
        raise ValueError(blueprint + ': not created')
    tools = unreal.BlueprintEditorLibrary
    tools.compile_blueprint(bp)
    cdo = unreal.get_default_object(tools.generated_class(bp))
    if not isinstance(cdo, unreal.MoverCharacter):
        raise ValueError(blueprint + ': not a MoverCharacter')
    apply(cdo, defaults, components)
    bp.modify()
    tools.compile_blueprint(bp)
    if not library.save_asset(blueprint, only_if_is_dirty=False):
        raise ValueError(blueprint + ': not saved')
    generated = tools.generated_class(bp)
    check(unreal, unreal.get_default_object(generated), defaults, components, blueprint)
    if generated.get_path_name() != args['pawn']:
        raise ValueError(f'{generated.get_path_name()} is not {args["pawn"]}')
    return bp
