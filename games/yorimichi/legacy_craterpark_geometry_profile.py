"""Finite observations of the original default editor geometry declaration.

Producer, selector, frontend and Node bodies never execute here. Generated artifacts
remain unread and uncertified. Installed-tool identity and nested execution remain core concerns.
"""
from dataclasses import dataclass
import ast
import hashlib
import json
import os
from pathlib import Path
import stat


class UnsupportedCraterparkGeometry(ValueError):
    """The declaration is outside the original default shipped editor role."""


@dataclass(frozen=True)
class CraterparkGeometry:
    step: str
    script: Path
    arguments: tuple[str, ...]
    raw_inputs: tuple[Path, ...]
    produced_inputs: tuple[Path, ...]
    code_inputs: tuple[Path, ...]
    output_paths: tuple[Path, ...]
    tool_sources: tuple[Path, ...]


# The existing scanner's finite original closure, including package initializers.
# New helpers require an explicit profile review; directory raw roles never grant code.
CODE_ROLES = (
    'games/yorimichi/world/regions/craterpark/__init__.py',
    'games/yorimichi/world/regions/craterpark/clean.py',
    'games/yorimichi/world/regions/craterpark/placement.py',
    'games/yorimichi/world/regions/craterpark/v2/__init__.py',
    'games/yorimichi/world/regions/craterpark/v2/ao.py',
    'games/yorimichi/world/regions/craterpark/v2/cdt.py',
    'games/yorimichi/world/regions/craterpark/v2/coping.py',
    'games/yorimichi/world/regions/craterpark/v2/curves.py',
    'games/yorimichi/world/regions/craterpark/v2/dressing.py',
    'games/yorimichi/world/regions/craterpark/v2/dsl.py',
    'games/yorimichi/world/regions/craterpark/v2/editor/__init__.py',
    'games/yorimichi/world/regions/craterpark/v2/editor/frontend.py',
    'games/yorimichi/world/regions/craterpark/v2/editor_boost.py',
    'games/yorimichi/world/regions/craterpark/v2/editor_coping.py',
    'games/yorimichi/world/regions/craterpark/v2/editor_decal.py',
    'games/yorimichi/world/regions/craterpark/v2/editor_floor.py',
    'games/yorimichi/world/regions/craterpark/v2/editor_generate.py',
    'games/yorimichi/world/regions/craterpark/v2/editor_prado.py',
    'games/yorimichi/world/regions/craterpark/v2/editor_supports.py',
    'games/yorimichi/world/regions/craterpark/v2/export.py',
    'games/yorimichi/world/regions/craterpark/v2/generate.py',
    'games/yorimichi/world/regions/craterpark/v2/ground.py',
    'games/yorimichi/world/regions/craterpark/v2/profile.py',
    'games/yorimichi/world/regions/craterpark/v2/rails.py',
    'games/yorimichi/world/regions/craterpark/v2/shrine.py',
    'games/yorimichi/world/regions/craterpark/v2/solids.py',
    'games/yorimichi/world/regions/craterpark/v2/spawns.py',
    'games/yorimichi/world/regions/craterpark/v2/split.py',
    'games/yorimichi/world/regions/craterpark/v2/tjunction.py',
    'games/yorimichi/world/regions/craterpark/v2/trees.py',
    'games/yorimichi/world/regions/craterpark/v2/v4_config.py',
    'games/yorimichi/world/regions/craterpark/v2/v4_placement.py',
    'games/yorimichi/world/regions/craterpark/v2/validate.py',
    'games/yorimichi/world/regions/hidamari/__init__.py',
    'games/yorimichi/world/regions/hidamari/natural_terrain.py',
    'games/yorimichi/world/regions/megapark/__init__.py',
    'games/yorimichi/world/regions/megapark/placement.py',
    'games/yorimichi/world/yori.py',
    'platform/studio/atelier/__init__.py',
    'platform/studio/atelier/atomic_files.py',
    'platform/studio/atelier/blender/__init__.py',
    'platform/studio/atelier/blender/fbx.py',
    'platform/studio/atelier/paths.py',
)

TOOL_DIGESTS = ('36886b417ed0cd4ff45c4428fc70bfef8591555372ec9d8d5034bb33fc8d08d0', '7e61398c75ad4186a6403b348ddc52d0c49b95fa6c2420739d0a4e3052973571', 'db35053e6cfa6a9dfaca311ce4f65bf766b1299c82ace7627a6d4734d0d4b134')



def _exact(actual, expected):
    if type(actual) is not type(expected):
        return False
    if type(expected) in (tuple, list):
        return len(actual) == len(expected) and all(_exact(a, b) for a, b in zip(actual, expected))
    return actual == expected


def _read(checkout, path):
    from atelier.build_v2.controller_client import MAX_SOURCE_FILE_BYTES, _read_at
    try:
        return _read_at(checkout, path.relative_to(checkout).as_posix(), MAX_SOURCE_FILE_BYTES)
    except (OSError, ValueError) as error:
        raise UnsupportedCraterparkGeometry(f'linked, missing or invalid source/data file: {path}') from error


def _role(checkout, path, *, directory=False):
    """Inspect only the role and nofollow ancestors; large data contents stay unopened."""
    from atelier.build_v2.controller_client import _open_root
    try:
        path.relative_to(checkout)
        descriptor = _open_root(path if directory else path.parent)
        try:
            if not directory and not stat.S_ISREG(os.stat(path.name, dir_fd=descriptor, follow_symlinks=False).st_mode):
                raise ValueError('not a regular file')
        finally:
            os.close(descriptor)
    except (OSError, ValueError) as error:
        raise UnsupportedCraterparkGeometry(f'linked, missing or invalid input role: {path}') from error


def _output(path, *, directory):
    from atelier.build_v2.controller_client import _open_root
    current = path
    while True:
        try:
            info = current.lstat()
        except FileNotFoundError:
            current = current.parent
            continue
        except OSError as error:
            raise UnsupportedCraterparkGeometry('invalid output ancestry') from error
        expected = stat.S_ISDIR if directory or current != path else stat.S_ISREG
        if not expected(info.st_mode):
            raise UnsupportedCraterparkGeometry('linked or invalid output role')
        if stat.S_ISDIR(info.st_mode):
            try:
                descriptor = _open_root(current)
                os.close(descriptor)
            except OSError as error:
                raise UnsupportedCraterparkGeometry('linked output ancestry') from error
            return
        current = current.parent


def _json(checkout, path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    try:
        return json.loads(_read(checkout, path), object_pairs_hook=unique)
    except (ValueError, UnicodeError) as error:
        raise UnsupportedCraterparkGeometry('invalid raw JSON declaration') from error


def _ast(checkout, path):
    try:
        return ast.parse(_read(checkout, path), filename=str(path))
    except (SyntaxError, ValueError) as error:
        raise UnsupportedCraterparkGeometry('invalid captured source structure') from error


def _digest(node):
    return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()


def _source_contract(checkout, game, v2):
    # These AST fingerprints bind the exact original constructor/enrichment and
    # frontend command contract without importing modules, evaluating defaults or
    # trusting live provider callbacks. Formatting/comments do not change structure.
    constructor = _ast(checkout, game / 'build.py')
    factories = [node for node in constructor.body if isinstance(node, ast.FunctionDef)
                 and node.name == 'craterpark_v2_steps']
    enrichment = [node for node in ast.walk(constructor) if isinstance(node, ast.With)
                  and len(node.items) == 1 and isinstance(node.items[0].context_expr, ast.Call)
                  and isinstance(node.items[0].context_expr.func, ast.Name)
                  and node.items[0].context_expr.func.id == 'diagnostic_phase'
                  and len(node.items[0].context_expr.args) == 1
                  and isinstance(node.items[0].context_expr.args[0], ast.Constant)
                  and node.items[0].context_expr.args[0].value == 'recipe.enrich']
    if (len(factories) != 1 or _digest(factories[0]) != '7cd5de15c4d34cbb0012c55c927bc7b8b2c718b35637f6fd5c87f327c86ca8a3'
            or len(enrichment) != 1 or _digest(enrichment[0]) != '8ddab7ffccde79c9135970b994ec7bf8fcf37ec934b0ec46f77e0e4d6bd71da4'):
        raise UnsupportedCraterparkGeometry('original constructor or enrichment structure differs')
    for relative, expected in (
        ('editor_generate.py', '5c3a92ed9c982d2462def18d6b7489045d9ef666fd23b9a60b84c5b96fcce4e7'),
        ('v4_config.py', '0ac95ac889ce2c5d194381f5782540df420adb5b7609979257aa4a7391f795dd'),
        ('editor/frontend.py', '01096c8f86916bbc10810cb9d4f46b9623f86b9d8e22dd14bd3473503e5b96e4')):
        if _digest(_ast(checkout, v2 / relative)) != expected:
            raise UnsupportedCraterparkGeometry(f'original editor/frontend source structure differs: {relative}')


def _closure(checkout, script, world, studio, expected):
    from atelier import paths
    from atelier.build import _FastImportScanner
    # Use the existing standard scanner behind the recipe acceleration layer.
    # Its candidate hook always runs, including aliases hidden by a warm fast cache.
    scanner_type = _FastImportScanner.__bases__[0]
    allowed = set(expected)
    def check(source):
        if source not in allowed:
            raise UnsupportedCraterparkGeometry('unknown source import target')
        _read(checkout, source)
    def anchored(root):
        if root == paths.STUDIO:
            return studio
        if root == paths.STUDIO / 'atelier':
            return studio / 'atelier'
        return root
    class CheckedScanner(scanner_type):
        def resolve(self, root, parts):
            found = super().resolve(anchored(root), parts)
            for source in found:
                check(source)
            return found
    actual = tuple(CheckedScanner().local_imports(script, (world, world / 'regions', studio)))
    for source in actual:
        check(source)  # Bind the entire returned closure, not just individual candidates.
    if actual != expected:
        raise UnsupportedCraterparkGeometry('original sorted source closure differs')
    return actual


def qualify_craterpark_geometry(step, *, checkout: Path, output_root: Path) -> CraterparkGeometry:
    """@cc [owner:fontanierh,label:correctness;safety] closed-craterpark-editor-observation
    Qualification MUST observe only the original default shipped editor geometry Step,
    its exact raw factory or complete enriched declaration, fixed code/tool sources and
    three original outputs. All reads MUST be bounded, anchored and nofollow; generated
    contents and large terrain layers MUST remain unopened. No producer/provider/frontend
    execution, Node probe, invented product or runtime/cache/completion authority is granted.
    See focused actual factory/Graph, source structure and reached alias regressions.
    """
    from atelier import build
    checkout, output_root = Path(checkout), Path(output_root)
    if (type(step) is not build.Step or type(step.name) is not str or step.name != 'world.craterpark_geometry'
            or not checkout.is_absolute() or not output_root.is_absolute()
            or '..' in checkout.parts or '..' in output_root.parts
            or checkout == Path(checkout.anchor) or output_root == Path(output_root.anchor)):
        raise UnsupportedCraterparkGeometry('not the default CraterPark Step and absolute anchors')
    game = checkout / 'games/yorimichi'
    world = game / 'world'
    regions = world / 'regions'
    v2 = regions / 'craterpark/v2'
    editor = v2 / 'editor'
    studio = checkout / 'platform/studio'
    script = v2 / 'editor_generate.py'
    park = game / 'tools/craterpark_editor/shipped.json'
    data = park.parent / 'data'
    arguments = ('--park', str(park))
    outputs = tuple(output_root / 'craterpark/v2' / name for name in
                    ('geometry.npz', 'geometry-report.json', 'lines'))
    defaults = dict(deferred_inputs=[], needs=[], after=[], heavy=True, pool_roots=[], explicit=False,
        verify=None, cutoff=True, products=[], reads=[], references=[], cache=False, audit=False,
        optional_inputs=[], queries=[], toolchain=False, batch=None, cook_recovery=None,
        checkpoint_previous_needs=None, checkpoint_restore=None, checkpoint_outputs=(), candidate_scope=None,
        replan=False, controller=None,
        about='Crater Park v2: layout -> conforming surfaces, solids, rails, render tiles and collision (numpy)')
    if (set(vars(step)) != set(defaults) | {'name', 'commands', 'inputs', 'outputs'}
            or any(not _exact(vars(step)[name], value) for name, value in defaults.items())
            or not _exact(step.outputs, list(outputs))):
        raise UnsupportedCraterparkGeometry('original Step controls or output roles differ')
    if type(step.commands) is not list or len(step.commands) != 1:
        raise UnsupportedCraterparkGeometry('expected one original Python command')
    command = step.commands[0]
    if (type(command) is not build.Python or set(vars(command)) != {'script', 'args'}
            or not _exact(command.script, script) or not _exact(command.args, arguments)):
        raise UnsupportedCraterparkGeometry('original editor command or shipped document differs')
    for path in (checkout, game, world, regions, v2, editor, studio, game / 'assets/craterpark', data):
        _role(checkout, path, directory=True)
    for path, directory in zip(outputs, (False, False, True)):
        _output(path, directory=directory)
    raw = [v2, regions / 'craterpark/__init__.py', regions / 'craterpark/placement.py',
           game / 'assets/craterpark', regions / 'megapark/placement.py', world / 'yori.py',
           regions / 'hidamari/__init__.py', regions / 'hidamari/natural_terrain.py', park, data / 'terrain.json']
    document = _json(checkout, park)
    terrain = _json(checkout, data / 'terrain.json')
    try:
        layers = terrain['inner']['layers']
        names = [*layers.values(), terrain['outer']['file']]
        if document['schema'] != 'craterpark-editor/1' or set(layers) != {'natural', 'dug'}:
            raise ValueError('unsupported default editor metadata')
        if (len(set(name.casefold() for name in names)) != len(names)
                or any(type(name) is not str or name in ('', '.', '..')
                       or '/' in name or '\\' in name or '\x00' in name for name in names)):
            raise ValueError('terrain references are not unique basenames')
    except (KeyError, TypeError, AttributeError, ValueError) as error:
        raise UnsupportedCraterparkGeometry('unsupported raw editor/terrain membership') from error
    raw.extend(data / name for name in names)
    for path in raw:
        _role(checkout, path, directory=path in (v2, game / 'assets/craterpark'))
    code = tuple(checkout / relative for relative in CODE_ROLES)
    tool_sources = tuple(editor / name for name in ('bridge.cjs', 'pieces.cjs', 'terrain.cjs', 'pin.json'))
    for source in code:
        _read(checkout, source)
    tool_bytes = tuple(_read(checkout, source) for source in tool_sources)
    if tuple(hashlib.sha256(content).hexdigest() for content in tool_bytes[:3]) != TOOL_DIGESTS:
        raise UnsupportedCraterparkGeometry('original pinned tool sources differ')
    pin = _json(checkout, tool_sources[-1])
    if (type(pin) is not dict or pin.get('schema') != 'craterpark-editor-pin/1' or pin.get('schema_version') != 'craterpark-editor/1'
            or pin.get('pieces_sha256') != hashlib.sha256(tool_bytes[1]).hexdigest()):
        raise UnsupportedCraterparkGeometry('editor tool pin differs')
    _source_contract(checkout, game, v2)
    _closure(checkout, script, world, studio, code)
    enriched = [*raw, *(source for source in code if source not in raw)]
    if not (_exact(step.inputs, raw) or _exact(step.inputs, enriched)):
        raise UnsupportedCraterparkGeometry('original raw or complete enriched input order differs')
    return CraterparkGeometry(step.name, script, arguments, tuple(raw), (), code, outputs, tool_sources)
