"""Sealed observations of the original CraterPark layout declaration.

This package grants no task, cache, repair or completion authority. It never opens
produced geometry or executes a producer, selector, provenance helper or tool.
"""
from dataclasses import dataclass
import ast
import hashlib
import json
import os
from pathlib import Path
import stat


class UnsupportedCraterparkLayout(ValueError):
    """The declaration is outside the original default shipped editor layout role."""


@dataclass(frozen=True)
class CraterparkLayout:
    step: str
    script: Path
    arguments: tuple[str, ...]
    raw_inputs: tuple[Path, ...]
    produced_inputs: tuple[Path, ...]
    code_inputs: tuple[Path, ...]
    output_paths: tuple[Path, ...]
    products: tuple[tuple[str, tuple[Path, ...]], ...]


# Complete original scanner closure, not the default four-file closure.
CODE_DIGESTS = {
    'games/yorimichi/world/craterpark_layout.py': '4e9cc69debd5a0e02287850bb4489322e1bfb494aa805aa1e5b1aa72fa06d23e',
    'games/yorimichi/world/regions/craterpark/__init__.py': 'ddc45019fb560a38712699d5e211dbdf75aa072973224e526f93ac007b7c68a6',
    'games/yorimichi/world/regions/craterpark/placement.py': '254ffc8edcd579ca6f1d618e71c1976372314969c936bc98d27c653067d1b580',
    'games/yorimichi/world/regions/craterpark/v2/__init__.py': '3543b4693a36a1098850b8bc928887694ed59a6deb7d3dfd0339de01f55a77b6',
    'games/yorimichi/world/regions/craterpark/v2/curves.py': '621c4382706726fb806a21602bf32d7dbeef4b9365dbeb62c84ddc9f8041307f',
    'games/yorimichi/world/regions/craterpark/v2/dsl.py': '6cfceb8d2be59877c3f0d5a881bbe1b74f4989de6bbd9e0ee032888f47f6efc9',
    'games/yorimichi/world/regions/craterpark/v2/profile.py': '1833c4953c490fae27feb3faf918790625654c367dcfd005c8cc351bd35030bb',
    'games/yorimichi/world/regions/craterpark/v2/v4_config.py': '0ac95ac889ce2c5d194381f5782540df420adb5b7609979257aa4a7391f795dd',
    'games/yorimichi/world/regions/craterpark/v2/v4_placement.py': '0378ba842506a3fae49ac683066e3eb591221a2438527cb7dc54369a29fcb090',
    'games/yorimichi/world/regions/megapark/__init__.py': '81204d73f4d36aa7823fd022ddd112568ff1adf7a21fe19ba4c863f3f6a4c7e0',
    'games/yorimichi/world/regions/megapark/placement.py': 'f489a1630040348390e75c37bdd92c7ae8c217b3d581bca20e14c3499c00964d',
    'games/yorimichi/world/yori.py': 'f3b3fe2e2b0600e2dae704a2c2ae8a25fd28e6160f6d2baeb5c3bd12c817fbbc',
    'platform/studio/atelier/__init__.py': '3695a32f8b7db8b12e9a6983751c82c9c5f109ac726a6e0b0f0dcda9b7511a15',
    'platform/studio/atelier/paths.py': '2a4a04024f6efa85292d64978ce795c3c8a772eeb7a79f68a97aed1a5183165e',
}


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
        raise UnsupportedCraterparkLayout(f'linked, missing or invalid source/data file: {path}') from error


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
        raise UnsupportedCraterparkLayout(f'linked, missing or invalid input role: {path}') from error


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
            raise UnsupportedCraterparkLayout('invalid output ancestry') from error
        expected = stat.S_ISDIR if directory or current != path else stat.S_ISREG
        if not expected(info.st_mode):
            raise UnsupportedCraterparkLayout('linked or invalid output role')
        if stat.S_ISDIR(info.st_mode):
            try:
                descriptor = _open_root(current)
                os.close(descriptor)
            except OSError as error:
                raise UnsupportedCraterparkLayout('linked output ancestry') from error
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
        raise UnsupportedCraterparkLayout('invalid raw JSON declaration') from error


def _ast(checkout, path):
    try:
        return ast.parse(_read(checkout, path), filename=str(path))
    except (SyntaxError, ValueError) as error:
        raise UnsupportedCraterparkLayout('invalid captured source structure') from error


def _digest(node):
    return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()


def _source_contract(checkout, game, code):
    constructor = _ast(checkout, game / 'build.py')
    factories = [n for n in constructor.body if isinstance(n, ast.FunctionDef)
                 and n.name == 'craterpark_v2_steps']
    raw_roles = [n for n in constructor.body if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == 'CRATERPARK' for t in n.targets)]
    enrichment = [n for n in ast.walk(constructor) if isinstance(n, ast.With)
                  and len(n.items) == 1
                  and ast.unparse(n.items[0].context_expr) == "diagnostic_phase('recipe.enrich')"]
    for nodes, expected in ((factories, '37cace5591aef1dd4d0b9a939617be977435f2b7738819f6500b0702979100d6'),
                            (raw_roles, 'e6f40f231c8629b10c8d7c80a49b9560ef551844195fcafd457f5f30c2369f6c'),
                            (enrichment, '8ddab7ffccde79c9135970b994ec7bf8fcf37ec934b0ec46f77e0e4d6bd71da4')):
        if len(nodes) != 1 or _digest(nodes[0]) != expected:
            raise UnsupportedCraterparkLayout('original constructor or enrichment structure differs')
    for source, expected in zip(code, CODE_DIGESTS.values()):
        if _digest(_ast(checkout, source)) != expected:
            raise UnsupportedCraterparkLayout('original source structure differs: ' + source.name)


def _closure(checkout, script, world, studio, expected):
    from atelier import paths
    from atelier.build import _FastImportScanner
    # Use the existing standard scanner behind the recipe acceleration layer.
    # Its candidate hook always runs, including aliases hidden by a warm fast cache.
    scanner_type = _FastImportScanner.__bases__[0]
    allowed = set(expected)
    def check(source):
        if source not in allowed:
            raise UnsupportedCraterparkLayout('unknown source import target')
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
        raise UnsupportedCraterparkLayout('original sorted source closure differs')
    return actual


def qualify_craterpark_layout(step, *, checkout: Path, output_root: Path) -> CraterparkLayout:
    """@cc [owner:fontanierh,label:correctness;safety] closed-craterpark-layout-observation
    Qualification MUST accept only the original raw factory or complete enriched layout
    Step in the default shipped editor context. Fixed code roles MUST be checked before
    inert scanning and bound to their original structure and complete import closure.
    Produced geometry MUST be excluded before any content read, including warm inputs.
    No producer, selector, provenance, process probe or task authority is granted.
    """
    from atelier import build
    try:
        checkout, output_root = Path(checkout), Path(output_root)
    except (TypeError, ValueError) as error:
        raise UnsupportedCraterparkLayout('invalid anchors') from error
    if any(os.environ.get(name, '').strip() for name in (
            'ATELIER_CRATERPARK_V4_DESIGN', 'ATELIER_CRATERPARK_EDITOR_PARK',
            'ATELIER_CRATERPARK_EDITOR_LINES')):
        raise UnsupportedCraterparkLayout('not the default shipped editor context')
    if (type(step) is not build.Step or type(getattr(step, 'name', None)) is not str or step.name != 'world.craterpark_layout'
            or not checkout.is_absolute() or not output_root.is_absolute()
            or '..' in checkout.parts or '..' in output_root.parts
            or checkout == Path(checkout.anchor) or output_root == Path(output_root.anchor)):
        raise UnsupportedCraterparkLayout('not the original layout Step and absolute anchors')
    game = checkout / 'games/yorimichi'
    world = game / 'world'
    regions = world / 'regions'
    v2 = regions / 'craterpark/v2'
    studio = checkout / 'platform/studio'
    script = world / 'craterpark_layout.py'
    park = game / 'tools/craterpark_editor/shipped.json'
    data = park.parent / 'data'
    outputs = (output_root / 'craterpark/layout-identity.json',)
    produced = (output_root / 'craterpark/v2/geometry.npz',)
    defaults = dict(deferred_inputs=[], needs=['world.craterpark_geometry'], after=[], heavy=True,
        pool_roots=[], explicit=False, verify=None, cutoff=True, products=[], reads=[], references=[],
        cache=False, audit=False, optional_inputs=[], queries=[], toolchain=False, batch=None,
        cook_recovery=None, checkpoint_previous_needs=None, checkpoint_restore=None,
        checkpoint_outputs=(), candidate_scope=None, replan=False, controller=None,
        about='validated Crater Park landform, exclusion and spawn identity for island consumers')
    if (set(vars(step)) != set(defaults) | {'name', 'commands', 'inputs', 'outputs'}
            or any(not _exact(vars(step)[name], value) for name, value in defaults.items())
            or not _exact(step.outputs, list(outputs))):
        raise UnsupportedCraterparkLayout('original Step controls or output roles differ')
    if type(step.commands) is not list or len(step.commands) != 1:
        raise UnsupportedCraterparkLayout('expected one original Python command')
    command = step.commands[0]
    if (type(command) is not build.Python or set(vars(command)) != {'script', 'args'}
            or not _exact(command.script, script) or not _exact(command.args, ())):
        raise UnsupportedCraterparkLayout('original layout command differs')
    # Precheck all fixed roles and their ancestors before the first source read.
    for path in (checkout, checkout / 'games', game, world, regions, v2,
                 checkout / 'platform', studio, data):
        _role(checkout, path, directory=True)
    code = tuple(checkout / relative for relative in CODE_DIGESTS)
    for source in (*code, game / 'build.py', park, data / 'terrain.json'):
        _role(checkout, source)
    for output in (*outputs, *produced):
        _output(output, directory=False)
    raw = [script, regions / 'craterpark/placement.py', game / 'assets/craterpark/scene.json',
           game / 'assets/craterpark/geometry', v2 / 'v4_config.py', park, data / 'terrain.json']
    document, terrain = _json(checkout, park), _json(checkout, data / 'terrain.json')
    try:
        layers = terrain['inner']['layers']
        names = [*layers.values(), terrain['outer']['file']]
        if document['schema'] != 'craterpark-editor/1' or set(layers) != {'natural', 'dug'}:
            raise ValueError('unsupported default editor metadata')
        if (any(type(name) is not str or name in ('', '.', '..') or '/' in name or '\\' in name
                or '\x00' in name for name in names)
                or len(set(name.casefold() for name in names)) != len(names)):
            raise ValueError('terrain references are not unique basenames')
    except (KeyError, TypeError, AttributeError, ValueError) as error:
        raise UnsupportedCraterparkLayout('unsupported raw editor/terrain membership') from error
    raw.extend(data / name for name in names)
    for path in raw:
        _role(checkout, path, directory=path == game / 'assets/craterpark/geometry')
    # Never treat the generated NPZ as a source or raw-data content candidate.
    factory = [*raw, *produced]
    enriched = [*factory, *(source for source in code if source not in factory)]
    if not (_exact(step.inputs, factory) or _exact(step.inputs, enriched)):
        raise UnsupportedCraterparkLayout('original raw or complete enriched input order differs')
    _source_contract(checkout, game, code)
    _closure(checkout, script, world, studio, code)
    return CraterparkLayout(step.name, script, (), tuple(raw), produced, code, outputs, ())
