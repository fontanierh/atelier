"""Observation-only qualification of the existing finite island texture tasks.

This module describes source and output roles for the managed legacy integration. It
neither grants execution authority nor computes a cache key, and never creates outputs.
"""
from dataclasses import dataclass
import os
from pathlib import Path
import stat


class UnsupportedTexture(ValueError):
    """The declaration is outside the closed, reviewed texture family."""


# Freeze the complete accepted catalogue, including generator roles. A new texture or
# generator needs a new reviewed profile rather than silently joining the family.
ROSTER = {
    'leaf_broad': ('T_leaf_broad.png', 'atlas', ()),
    'leaf_cedar': ('T_leaf_cedar.png', 'atlas', ()),
    'leaf_pine': ('T_leaf_pine.png', 'atlas', ()),
    'leaf_ochre': ('T_leaf_ochre.png', 'atlas', ()),
    'leaf_maple': ('T_leaf_maple.png', 'small_leaf_atlas', ()),
    'leaf_ginkgo': ('T_leaf_ginkgo.png', 'small_leaf_atlas', ()),
    'leaf_ochre_small': ('T_leaf_ochre_small.png', 'small_leaf_atlas', ()),
    'leaf_small': ('T_leaf_small.png', 'small_leaf_atlas', ()),
    'litter': ('T_litter.png', 'litter', ()),
    'cloudmask': ('T_cloudmask.png', 'cloudmask', ()),
    'flower': ('T_flower.png', 'flower_atlas', ()),
    'rooftile': ('T_rooftile.jpg', 'rooftile', ()),
    'grass': ('T_grass.png', 'grass', ()),
    'bark_olive': ('T_bark_olive.jpg', 'bark', ('tree-bark.jpg',)),
    'bark': ('T_bark.jpg', 'bark', ('tree-bark.jpg',)),
    'road': ('T_road.jpg', 'road', ()),
    'ground': ('T_ground.jpg', 'ground', ()),
    'ground_detail': ('T_ground_detail.png', 'ground_detail',
                      ('tuscan-ground.jpg', 'tuscan-ground.provenance.json')),
    'sky': ('T_sky.png', 'sky', ()),
    'water': ('T_water.jpg', 'water', ()),
    'concrete': ('T_concrete.jpg', 'concrete', ()),
    'white': ('T_white.png', 'white', ()),
}


@dataclass(frozen=True)
class TextureTask:
    step: str
    texture: str
    script: Path
    arguments: tuple[str, ...]
    output: Path
    product: str
    raw_inputs: tuple[Path, ...]
    code_inputs: tuple[Path, ...]


def _directory(path):
    """Accept an existing real directory without resolving away original spellings."""
    try:
        info = path.lstat()
    except FileNotFoundError as error:
        raise UnsupportedTexture(f'texture directory is absent or linked: {path}') from error
    if not stat.S_ISDIR(info.st_mode):
        raise UnsupportedTexture(f'texture directory is absent or linked: {path}')


def _regular_source(path):
    # lstat rejects links instead of following them. Missing sources retain normal
    # FileNotFoundError behavior; no source or output is created by qualification.
    if not stat.S_ISREG(path.lstat().st_mode):
        raise UnsupportedTexture(f'texture source is not a regular file: {path}')


def _closed_anchors(checkout, output_root, game, world, assets_root):
    """Refuse linked source parents and output aliases before any source is executed."""
    for parent in game.parents:
        if parent == checkout:
            break
        _directory(parent)
    _directory(checkout)
    for path in (game, world, world / 'textures', assets_root, assets_root / 'environment',
                 assets_root / 'environment/textures'):
        _directory(path)
    from atelier.build_v2.controller_client import _open_root
    for path in (output_root, output_root.parent):
        descriptor = _open_root(path)
        os.close(descriptor)
        _directory(path)
    # The factory places the sole required file directly in this directory. Do not
    # create it, adopt existing bytes, or allow a linked destination ancestor.
    _directory(output_root)
    if output_root.name != 'textures':
        _directory(output_root / 'textures')


def qualify_texture_step(step, *, checkout: Path, output_root: Path) -> TextureTask:
    """@cc [owner:fontanierh,label:correctness] closed-legacy-texture-qualification
    Qualification MUST match the actual frozen22texture factory declaration, exact argv,
    selected raw members, static code closure and sole required output before any effect.
    It MUST refuse aliases, unknown generators/members and custom controls, return only
    observations, and never grant execution, create outputs or compute cache authority.
    See test_legacy_texture_profile.py actual-factory positive and mutation regressions.
    """
    from atelier import build, build_products

    checkout, output_root = Path(checkout), Path(output_root)
    if type(step) is not build.Step or not checkout.is_absolute() or not output_root.is_absolute():
        raise UnsupportedTexture('texture requires a real Step and absolute source/output anchors')
    if checkout == Path(checkout.anchor) or output_root == Path(output_root.anchor):
        raise UnsupportedTexture('texture source/output anchors must not be filesystem roots')
    if step.name not in {f'world.textures.{name}' for name in ROSTER}:
        raise UnsupportedTexture(f'not an individual qualified texture task: {step.name}')
    texture = step.name.removeprefix('world.textures.')
    filename, generator, assets = ROSTER[texture]
    game = checkout / 'games/yorimichi'
    world = game / 'world'
    assets_root = game / 'assets'
    script = world / 'gen_textures.py'
    spec = world / 'textures' / f'{texture}.json'
    output = output_root / 'textures' / filename
    arguments = ('--texture', texture, '--spec', str(spec), '--output', str(output),
                 *(('--assets', str(assets_root)) if assets else ()))
    raw = (spec, *(assets_root / 'environment/textures' / name for name in assets))
    _closed_anchors(checkout, output_root, game, world, assets_root)

    # Load through the existing recipe helper rather than a second module-resolution
    # mechanism. Captured integration uses the same original logical filenames.
    from importlib.util import module_from_spec, spec_from_file_location
    from atelier.source_imports import ImportScanner
    loader = spec_from_file_location('yorimichi_texture_catalog_qualification', world / 'texture_catalog.py')
    catalogue = module_from_spec(loader)
    loader.loader.exec_module(catalogue)
    if catalogue.TEXTURES != ROSTER:
        raise UnsupportedTexture('texture catalogue or generator roles differ from the frozen profile')

    default_controls = {
        'deferred_inputs': [], 'needs': [], 'after': [],
        'heavy': False, 'pool_roots': [], 'explicit': False,
        'verify': None, 'cutoff': False, 'reads': [], 'references': [],
        'cache': True, 'audit': True, 'optional_inputs': [], 'queries': [], 'toolchain': False,
        'batch': None, 'cook_recovery': None, 'checkpoint_previous_needs': None,
        'checkpoint_restore': None, 'checkpoint_outputs': (), 'candidate_scope': None,
        'replan': False, 'controller': None,
    }
    values = vars(step)
    if (set(values) - {'name', '_query_bindings', 'commands', 'inputs', 'outputs', 'about', 'products'}
            != set(default_controls)
            or any(values[name] != default for name, default in default_controls.items())):
        raise UnsupportedTexture(f'{step.name}: unsupported or customized Step controls')
    if len(step.commands) != 1:
        raise UnsupportedTexture(f'{step.name}: expected exactly one original Python command')
    command = step.commands[0]
    if (type(command) is not build.Python or set(vars(command)) != {'script', 'args'}
            or command.script != script or type(command.args) is not tuple
            or not all(isinstance(value, (str, Path)) for value in command.args)
            or tuple(map(str, command.args)) != arguments):
        raise UnsupportedTexture(f'{step.name}: script or arguments differ from the original factory')
    if len(step.outputs) != 1 or step.outputs != [output]:
        raise UnsupportedTexture(f'{step.name}: required output differs from the original factory')
    if len(step.products) != 1 or type(step.products[0]) is not build_products.Product:
        raise UnsupportedTexture(f'{step.name}: expected one original named product')
    product = step.products[0]
    if (set(vars(product)) != {'name', 'paths', 'collection', 'bounds', 'optional_paths'}
            or product.name != f'texture.{texture}' or product.collection is not None
            or product.bounds is not None or product.optional_paths
            or list(product.paths) != [output]):
        raise UnsupportedTexture(f'{step.name}: product role or complete output claim differs')

    # The selected spec is the only settings input. Its existing schema reader performs
    # no writes; missing files and malformed settings retain their ordinary errors.
    for source in raw:
        _regular_source(source)
    catalogue.load_spec(spec)
    code = tuple(ImportScanner().local_imports(script))
    if script not in code or len(set(code)) != len(code):
        raise UnsupportedTexture(f'{step.name}: generator resolved through an alias or duplicate role')
    for source in code:
        _regular_source(source)
    support = tuple(path for path in code if path != script)
    expected_inputs = [spec, *support, *raw[1:]]
    if step.inputs != expected_inputs:
        raise UnsupportedTexture(f'{step.name}: spec, code or asset membership/order differs')
    return TextureTask(step.name, texture, script, arguments, output, product.name, raw, code)
