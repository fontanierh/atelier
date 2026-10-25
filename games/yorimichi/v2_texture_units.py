"""Author C3 texture RawImport and Finish units from exact source producer rows."""
from pathlib import Path, PurePosixPath

OPS = 'platform/studio/atelier/build_v2/unreal_ops.py'
SUPPORT = ('platform/studio/atelier/interchange_mesh.py', 'platform/studio/atelier/__init__.py')
PLUGIN = 'platform/build-v2/unreal/AtelierBuildWorker'
GENERATOR = 'games/yorimichi/world/gen_textures.py'
KEYS = ('leaf_broad', 'leaf_cedar', 'leaf_pine', 'leaf_ochre', 'leaf_maple', 'leaf_ginkgo',
        'leaf_ochre_small', 'leaf_small', 'litter', 'cloudmask', 'flower', 'rooftile', 'grass',
        'bark_olive', 'bark', 'road', 'ground', 'ground_detail', 'sky', 'water', 'concrete', 'white')
JPEG = frozenset(('rooftile', 'bark_olive', 'bark', 'road', 'ground', 'water', 'concrete'))
ASSETS = frozenset(('bark_olive', 'bark', 'ground_detail'))
SIDECARS = ('.uasset', '.uexp', '.m.ubulk', '.ubulk', '.uptnl', '.upayload')


class Unsupported(ValueError):
    """The source declaration differs from the explicitly migrated texture body."""


def _path(value):
    if (not isinstance(value, str) or not value or '\\' in value or PurePosixPath(value).is_absolute()
            or str(PurePosixPath(value)) != value or any(p in ('.', '..') for p in value.split('/'))):
        raise Unsupported('noncanonical texture producer path')
    return value


def _code(checkout):
    root = Path(checkout)
    plugin = root / PLUGIN
    source = plugin / 'Source'
    if plugin.is_symlink() or source.is_symlink() or not source.is_dir():
        raise Unsupported('native worker source tree is missing or linked')
    files = [plugin / 'AtelierBuildWorker.uplugin', root / OPS, *(root / name for name in SUPPORT)]
    for path in source.rglob('*'):
        if path.is_symlink():
            raise Unsupported('native worker source contains a link')
        if path.suffix in ('.cs', '.cpp', '.h'):
            files.append(path)
    for path in files:
        if not path.is_file() or path.is_symlink():
            raise Unsupported('native worker source member is missing or nonregular')
    return sorted(path.relative_to(root).as_posix() for path in files)


def _output(package, *, raw):
    stem = package.removeprefix('/Game/')
    files = []
    for suffix in SIDECARS:
        row = {'path': 'content/Game/' + stem + suffix, 'required': suffix == '.uasset'}
        if not raw:
            row['install_path'] = 'games/yorimichi/unreal/Content/' + stem + suffix
        files.append(row)
    return {'id': 'raw_texture' if raw else 'texture', 'logical_path': package,
            'class': 'RawTexture' if raw else 'Texture', 'destination': 'store' if raw else 'checkout',
            'files': files}


def texture_units(rows, *, checkout):
    """@cc [owner:fontanierh,label:correctness] authored-c3-texture-units
    Each migrated source MUST match its exact named producer, product ROOT and
    original texture command. RawImport MUST remain store-only without finish
    properties. Finish MUST consume its actual raw Item, apply the original
    alpha/mip properties only there, and declare the complete permitted native
    sidecars and checkout ownership. No generated content discovery or producer
    execution is permitted. Native worker source membership MUST be keyed code.
    """
    selected = [row for row in rows if row['id'].startswith('world.textures.')]
    code = _code(checkout) if selected else []
    units, staged, slots, textures, seen = [], {}, {}, {}, set()
    for row in selected:
        key = row['id'].removeprefix('world.textures.')
        if key not in KEYS or key in seen:
            raise Unsupported('unknown or duplicate texture producer')
        seen.add(key)
        filename = 'T_' + key + ('.jpg' if key in JPEG else '.png')
        products = row['products']
        if (len(products) != 1 or products[0]['id'] != 'texture.' + key
                or len(products[0]['paths']) != 1 or products[0]['optional_paths']):
            raise Unsupported('texture producer must own its exact single required product ROOT')
        source = _path(products[0]['paths'][0])
        if PurePosixPath(source).name != filename or row['outputs'] != [source]:
            raise Unsupported('texture source filename/output differs from its producer ROOT')
        commands = row['commands']
        arguments = ['--texture', key, '--spec', {'path': f'games/yorimichi/world/textures/{key}.json'},
                     '--output', {'path': source}]
        if key in ASSETS:
            arguments += ['--assets', {'path': 'games/yorimichi/assets'}]
        if (len(commands) != 1 or commands[0].get('kind') != 'python'
                or commands[0].get('script') != {'path': GENERATOR}
                or commands[0].get('args') != arguments):
            raise Unsupported('texture producer command differs from the original declared body')
        name = PurePosixPath(filename).stem
        raw_id, finish_id = 'unreal.texture.raw.' + key, 'unreal.texture.finish.' + key
        raw_package, package = '/Game/_Raw/Textures/' + name, '/Game/Japan/Textures/' + name
        raw_params = {'op': 'raw_import', 'kind': 'texture', 'source': 'source', 'destination': raw_package,
                      'input_roots': {'source': {'archive_member': 'products/0-0.tree.tar', 'name': filename}}}
        properties = {}
        if filename.startswith(('T_grass', 'T_leaf_', 'T_flower')):
            properties = {'do_scale_mips_for_alpha_coverage': True,
                          'alpha_coverage_thresholds': {'unreal_type': 'Vector4', 'args': [0, 0, 0, .4]},
                          'mip_gen_settings': {'unreal_enum': 'TextureMipGenSettings.TMGS_SIMPLE_AVERAGE'}}
        finish_params = {'op': 'finish', 'kind': 'texture', 'source': 'raw', 'destination': package,
                         'package_sources': {'raw': raw_package}, 'properties': properties}
        for unit_id, op, params, input_name, owner, item_id, raw in (
            (raw_id, 'unreal.raw_import', raw_params, 'source', row['id'], 'product0', True),
            (finish_id, 'unreal.finish', finish_params, 'raw', raw_id, 'raw_texture', False)):
            units.append({'id': unit_id, 'op': {'kind': op, 'version': '1'}, 'script': OPS, 'code': list(code),
                          'inputs': [{'role': 'content', 'name': input_name,
                                      'source': {'kind': 'item', 'unit': owner, 'item': item_id}}],
                          'params': params, 'outputs': [_output(raw_package if raw else package, raw=raw)]})
            staged[unit_id] = {input_name: 'inputs/' + input_name}
            slots[input_name] = False
        textures[name] = {'unit': finish_id, 'item': 'texture', 'package': package}
    return {'units': units, 'staged': staged, 'slots': slots, 'textures': textures}
