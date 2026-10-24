"""Finite observations of the five original city JSON projections; no execution or authority."""
from dataclasses import dataclass
import ast
import hashlib
import os
from pathlib import Path
import stat

ASSETS = ('HD_CivicGardens', 'HD_Streets', 'HD_PlazaShopApproaches', 'HD_Wires', 'HD_LaneEdges')
CODE = ('games/yorimichi/world/regions/hidamari/city_data.py', 'games/yorimichi/world/yori.py',
        'platform/studio/atelier/__init__.py', 'platform/studio/atelier/atomic_files.py',
        'platform/studio/atelier/export_manifest.py', 'platform/studio/atelier/model_files.py',
        'platform/studio/atelier/paths.py')
AST_DIGESTS = {'games/yorimichi/world/regions/hidamari/city_data.py': '48f11986b20579347ff7c9f553238b5b694f98802e694565db3b7e9f3a524ac7', 'games/yorimichi/world/yori.py': 'f3b3fe2e2b0600e2dae704a2c2ae8a25fd28e6160f6d2baeb5c3bd12c817fbbc', 'platform/studio/atelier/__init__.py': '3695a32f8b7db8b12e9a6983751c82c9c5f109ac726a6e0b0f0dcda9b7511a15', 'platform/studio/atelier/atomic_files.py': '33c1d609f4391d80c3d267ed0b61a19304f58d51232f8cec8b7b43d69c4f3b78', 'platform/studio/atelier/export_manifest.py': '44da92d248422d587ebcb08b57e3f4308e7760411b68cccca28784abd5b7f3a6', 'platform/studio/atelier/model_files.py': '349c53215e39d939950b972e4353747d4dff560eaf7dda49325774398561ccbb', 'platform/studio/atelier/paths.py': '2a4a04024f6efa85292d64978ce795c3c8a772eeb7a79f68a97aed1a5183165e'}
LAYOUT_AST = '40ea78b91b0ab239920b08959a35c23c9eb2998491ef0b2832161e22f5e0dd82'


class UnsupportedHidamariProjection(ValueError):
    """The Step is outside the original fixed city projection family."""


@dataclass(frozen=True)
class HidamariProjection:
    step: str
    script: Path
    arguments: tuple[str, ...]
    raw_inputs: tuple[Path, ...]
    produced_inputs: tuple[Path, ...]
    code_inputs: tuple[Path, ...]
    products: tuple[tuple[str, tuple[Path, ...]], ...]


def _source(checkout, path):
    from atelier.build_v2.controller_client import _read_at, MAX_SOURCE_FILE_BYTES
    try:
        return _read_at(checkout, path.relative_to(checkout).as_posix(), MAX_SOURCE_FILE_BYTES)
    except (OSError, ValueError) as error:
        raise UnsupportedHidamariProjection('source is missing, linked or outside checkout') from error


def _output(path):
    from atelier.build_v2.controller_client import _open_root
    current = path
    while True:
        try:
            info = current.lstat()
        except FileNotFoundError:
            if current == current.parent:
                raise UnsupportedHidamariProjection('output has no anchored ancestor') from None
            current = current.parent
            continue
        except OSError as error:
            raise UnsupportedHidamariProjection('output ancestry cannot be inspected') from error
        expected = stat.S_ISREG if current == path else stat.S_ISDIR
        if not expected(info.st_mode):
            raise UnsupportedHidamariProjection('output ancestry is linked or has wrong role')
        try:
            fd = _open_root(current if stat.S_ISDIR(info.st_mode) else current.parent)
            os.close(fd)
        except OSError as error:
            raise UnsupportedHidamariProjection('output ancestry is not anchored') from error
        return


def _ast(raw):
    try:
        return ast.parse(raw)
    except (SyntaxError, ValueError) as error:
        raise UnsupportedHidamariProjection('invalid source syntax') from error


def _digest(node):
    return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()


def qualify_hidamari_projection(step, *, checkout: Path, output_root: Path) -> HidamariProjection:
    """@cc [owner:fontanierh,label:correctness;safety] original-city-projection-observation
    Only the five fixed original layout_steps JSON projections MAY qualify. Exact
    Step/Python/Product types, controls, argv, ordered seven-file code closure,
    constructor/source AST and the city named read MUST agree. Anchored nofollow
    source reads and candidate checks MUST precede source execution; generated
    city/output bytes MUST remain unopened and cold output tails uncreated.
    This function MUST NOT invoke producers/helpers, mutate state, authorize future
    tasks or grant cache, repair, guarded execution, settlement or Finish authority.
    """
    from atelier import build, build_products, paths
    from atelier.build_v2.controller_client import _open_root
    checkout, output_root = Path(checkout), Path(output_root)
    prefix = 'world.hidamari.data.'
    if (type(step) is not build.Step or type(step.name) is not str
            or not step.name.startswith(prefix) or step.name[len(prefix):] not in ASSETS
            or not checkout.is_absolute() or not output_root.is_absolute()
            or '..' in checkout.parts or '..' in output_root.parts
            or checkout == Path(checkout.anchor) or output_root == Path(output_root.anchor)):
        raise UnsupportedHidamariProjection('foreign Step or anchors')
    try:
        fd = _open_root(checkout); os.close(fd)
    except OSError as error:
        raise UnsupportedHidamariProjection('checkout is not anchored') from error
    asset = step.name[len(prefix):]
    script = checkout / CODE[0]
    source = output_root / 'hidamari/layout-data.json'
    output = output_root / 'hidamari/constructor-data' / (asset + '.json')
    _output(source); _output(output)
    arguments = ('--source', str(source), '--asset', asset, '--output', str(output))
    defaults = {'deferred_inputs': [], 'needs': [], 'after': [], 'outputs': [], 'heavy': False,
        'pool_roots': [], 'explicit': False, 'verify': None, 'cutoff': False, 'references': [],
        'cache': True, 'audit': False, 'optional_inputs': [], 'queries': [], 'toolchain': False,
        'batch': None, 'cook_recovery': None, 'checkpoint_previous_needs': None,
        'checkpoint_restore': None, 'checkpoint_outputs': (), 'candidate_scope': None,
        'replan': False, 'controller': None}
    dynamic = {'name', 'commands', 'inputs', 'about', 'products', 'reads'}
    if (set(vars(step)) - dynamic != set(defaults)
            or any(type(vars(step)[name]) is not type(value) or vars(step)[name] != value
                   for name, value in defaults.items())
            or type(step.reads) is not list or any(type(v) is not str for v in step.reads)
            or step.reads != ['hidamari.city_data']
            or type(step.commands) is not list or len(step.commands) != 1):
        raise UnsupportedHidamariProjection('original projection controls differ')
    command = step.commands[0]
    if (type(command) is not build.Python or set(vars(command)) != {'script', 'args'}
            or type(command.script) is not type(script) or command.script != script
            or type(command.args) is not tuple or command.args != arguments
            or any(type(value) is not str for value in command.args)):
        raise UnsupportedHidamariProjection('original Python argv differs')
    if type(step.products) is not list or len(step.products) != 1:
        raise UnsupportedHidamariProjection('original projection product differs')
    product = step.products[0]
    if (type(product) is not build_products.Product
            or set(vars(product)) != {'name', 'paths', 'collection', 'bounds', 'optional_paths'}
            or type(product.name) is not str or product.name != 'hidamari.data.' + asset
            or type(product.paths) is not tuple or any(type(p) is not type(output) for p in product.paths)
            or product.paths != (output,) or product.collection is not None or product.bounds is not None
            or type(product.optional_paths) is not tuple or product.optional_paths != ()):
        raise UnsupportedHidamariProjection('original projection product differs')
    code = tuple(checkout / name for name in CODE)
    if (type(step.inputs) is not list or len(step.inputs) != len(code)
            or any(type(actual) is not type(expected) or actual != expected
                   for actual, expected in zip(step.inputs, code))):
        raise UnsupportedHidamariProjection('original source membership/order differs')
    for name, path in zip(CODE, code):
        if _digest(_ast(_source(checkout, path))) != AST_DIGESTS[name]:
            raise UnsupportedHidamariProjection('original source structure differs: ' + name)
    constructor = _ast(_source(checkout, checkout/'games/yorimichi/hidamari_build.py'))
    functions = [node for node in constructor.body
                 if isinstance(node, ast.FunctionDef) and node.name == 'layout_steps']
    assignments = [node for node in constructor.body if isinstance(node, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == 'DATA_ASSETS' for t in node.targets)]
    try:
        assets = ast.literal_eval(assignments[0].value) if len(assignments) == 1 else None
    except (ValueError, TypeError) as error:
        raise UnsupportedHidamariProjection('original asset roster is not literal') from error
    if (len(functions) != 1 or _digest(functions[0]) != LAYOUT_AST or assets != ASSETS):
        raise UnsupportedHidamariProjection('original layout projection constructor differs')
    # The existing scanner is inert. Every candidate is checked against the exact
    # pre-read source roles; unknown imports do not gain live-loader permission.
    allowed = set(code)
    class Scanner(build._FastImportScanner.__bases__[0]):
        def resolve(self, root, parts):
            if root == paths.STUDIO:
                root = checkout/'platform/studio'
            elif root == paths.STUDIO/'atelier':
                root = checkout/'platform/studio/atelier'
            found = super().resolve(root, parts)
            for path in found:
                if path not in allowed:
                    raise UnsupportedHidamariProjection('unknown imported source candidate')
                _source(checkout, path)
            return found
    world = checkout/'games/yorimichi/world'
    if tuple(Scanner().local_imports(script, (world, world/'regions'))) != code:
        raise UnsupportedHidamariProjection('source scanner closure differs')
    return HidamariProjection(step.name, script, arguments, code, (source,), code,
                              ((product.name, (output,)),))
