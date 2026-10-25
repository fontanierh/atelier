"""Pure authored declarations for Yorimichi's independently owned shared materials."""
from copy import deepcopy
from pathlib import Path

SCRIPT = 'games/yorimichi/world/materials_v2.py'
SCRIPTS = 'games/yorimichi/unreal/Scripts/'
CODE = (SCRIPT, SCRIPTS + 'shared_materials.py', SCRIPTS + 'material_assets.py',
        SCRIPTS + 'foliage_material.py', SCRIPTS + 'see_through.py', SCRIPTS + 'atmosphere.py',
        SCRIPTS + 'sea_look.py', SCRIPTS + 'painterly_kernel.py',
        'games/yorimichi/world/yori.py', 'games/yorimichi/world/asset_catalog.py',
        'platform/studio/atelier/paths.py', 'platform/studio/atelier/__init__.py')
MATERIALS = '/Game/Japan/Materials/'
TEXTURES = '/Game/Japan/Textures/'
SEE_THROUGH = '/Game/SeeThrough/MPC_SeeThrough'
SIDECARS = ('.uexp', '.m.ubulk', '.ubulk', '.uptnl', '.upayload')


def material_specs():
    """The original shared factories' individual arguments and graph overlays."""
    specs = [
        {'asset': 'MPC_Wind', 'factory': 'wind', 'dependencies': []},
        {'asset': 'MPC_SeeThrough', 'factory': 'collection', 'dependencies': []},
        {'asset': 'M_Painted', 'factory': 'master', 'dependencies': ['T_white', 'MPC_SeeThrough'],
         'overlay': {'blend': False, 'scale': [1., 1., 1., 1.]}},
        {'asset': 'M_Foliage', 'factory': 'master', 'masked': True, 'wind': True,
         'dependencies': ['T_white', 'MPC_Wind', 'MPC_SeeThrough'],
         'overlay': {'blend': False, 'scale': [1., 1., 2., 1.]}},
        {'asset': 'M_Grass', 'factory': 'grass', 'dependencies': ['T_white', 'MPC_Wind', 'MPC_SeeThrough'],
         'overlay': {'scale': [1., 1., 2.5, 1.], 'whole_fade': False}},
        {'asset': 'M_Sky', 'factory': 'master', 'unlit': True, 'fixed_texture': 'T_sky', 'dependencies': ['T_sky']},
        {'asset': 'M_CloudShadow', 'factory': 'cloud', 'texture': 'T_cloudmask', 'dependencies': ['T_cloudmask']},
        {'asset': 'M_Painterly', 'factory': 'painterly', 'dependencies': []},
    ]
    def instance(name, parent, texture=None, tint=None, *, bark=False):
        row = {'asset': 'MI_' + name, 'factory': 'instance', 'parent': parent,
               'dependencies': [parent] + ([texture] if texture else [])}
        if texture:
            row['texture'] = texture
        if tint is not None:
            row['tint'] = list(tint)
        if bark:
            row['bark_lod'] = True
        if name in ('Bark', 'RoofTile', 'Tile', 'Plaster', 'Wood', 'Lattice', 'Vermilion', 'Paint', 'Metal', 'Stone', 'Concrete'):
            row['mask_instance'] = True
        if name == 'Paint':
            row['cut_scale'] = [1., .25, 1., 1.]
        specs.append(row)
    for name, texture in (('LeafBroad', 'T_leaf_broad'), ('LeafCedar', 'T_leaf_cedar'),
            ('LeafPine', 'T_leaf_pine'), ('LeafOchre', 'T_leaf_ochre'), ('LeafMaple', 'T_leaf_maple'),
            ('LeafGinkgo', 'T_leaf_ginkgo'), ('LeafSmall', 'T_leaf_small'), ('Litter', 'T_litter'),
            ('Flower', 'T_flower'), ('LeafOchreSmall', 'T_leaf_ochre_small')):
        instance(name, 'M_Foliage', texture, (1., .72, .42) if name == 'LeafGinkgo' else None)
    instance('Grass', 'M_Grass', 'T_grass')
    instance('RoofTile', 'M_Painted', 'T_rooftile', (.40, .42, .48))
    for name, texture, tint in (('Bark', 'T_bark', None), ('BarkOlive', 'T_bark_olive', None),
                               ('BarkTuscan', 'T_bark_olive', (.65, .55, .4))):
        instance(name, 'M_Painted', texture, tint, bark=True)
    for name, texture, tint in (('Concrete', 'T_concrete', None), ('Ground', 'T_ground', None),
            ('Road', 'T_road', (.34, .33, .33)), ('Water', 'T_water', None)):
        instance(name, 'M_Painted', texture, tint)
    instance('Sky', 'M_Sky', tint=(1.35, 1.35, 1.35))
    for name, tint in {'Paint': (.85, .85, .82), 'Stone': (.50, .50, .47), 'Vermilion': (.62, .12, .06),
            'Plaster': (.80, .74, .62), 'Tile': (.16, .17, .20), 'Wood': (.18, .11, .07),
            'Feather': (.92, .92, .90), 'FeatherDark': (.10, .10, .12), 'Metal': (.08, .08, .09),
            'Rock': (.30, .27, .24), 'Lattice': (.14, .10, .08), 'Moss': (.30, .38, .16)}.items():
        instance(name, 'M_Painted', 'T_white', tint)
    return specs


def _package(name):
    return SEE_THROUGH if name == 'MPC_SeeThrough' else (TEXTURES if name.startswith('T_') else MATERIALS) + name


def author_units(texture_units, *, code=None, checkout=None):
    """@cc [owner:fontanierh,label:correctness] individual-authored-material-declarations
    Each original shared material/instance/collection MUST have exactly one native
    output owner. Inputs MUST include every actual parent/texture/collection package
    read, including transitive parent dependencies. Original factory values and all
    see-through/LOD overlays MUST remain authored parameters. This compiler MUST NOT
    execute native factories, inspect generated assets or call the old monolith.
    """
    textures = {}
    for name, reference in texture_units.items():
        asset = name.rsplit('/', 1)[-1]
        if not asset.startswith('T_') or not isinstance(reference, dict):
            raise ValueError('expected finished texture references keyed by T_name or package')
        package = _package(asset)
        if reference.get('package', package) != package or not reference.get('unit') or not reference.get('item'):
            raise ValueError('finished texture reference differs from its canonical package')
        if asset in textures:
            raise ValueError('duplicate finished texture reference')
        textures[asset] = {**reference, 'package': package}
    specs = material_specs()
    by_name = {row['asset']: row for row in specs}
    references = {**textures, **{name: {'unit': 'unreal.materials.' + name, 'item': 'asset', 'package': _package(name)}
                               for name in by_name}}
    source_code = list(CODE if code is None else code)
    if checkout is not None and code is None:
        from atelier.source_imports import ImportScanner
        root = Path(checkout)
        source_code = [p.relative_to(root).as_posix() for p in ImportScanner().local_imports(
            root / SCRIPT, (root / 'games/yorimichi/world', root / 'games/yorimichi/unreal/Scripts',
                            root / 'platform/studio'))]
    if SCRIPT not in source_code:
        raise ValueError('authored material entry must be in the frozen code closure')
    def dependencies(name):
        found = set()
        def visit(current):
            for dependency in by_name[current]['dependencies']:
                if dependency in found:
                    continue
                if dependency not in references:
                    raise ValueError('missing finished material dependency: ' + dependency)
                found.add(dependency)
                if dependency in by_name:
                    visit(dependency)
        visit(name)
        return sorted(found)
    units, staged, slots = [], {}, {}
    for spec in specs:
        name = spec['asset']
        reference = references[name]
        deps = dependencies(name)
        inputs = [{'role': 'content', 'name': dep, 'source': {'kind': 'item',
                   'unit': references[dep]['unit'], 'item': references[dep]['item']}} for dep in deps]
        args = deepcopy({key: value for key, value in spec.items() if key != 'dependencies'})
        args.update(package=reference['package'], inputs={dep: references[dep]['package'] for dep in deps})
        relative = reference['package'].removeprefix('/Game/')
        files = [{'path': 'content/Game/' + relative + suffix,
                  'install_path': 'games/yorimichi/unreal/Content/' + relative + suffix,
                  'required': suffix == '.uasset'} for suffix in ('.uasset', *SIDECARS)]
        kind = 'MaterialParameterCollection' if spec['factory'] in ('wind', 'collection') else (
            'MaterialInstance' if spec['factory'] == 'instance' else 'Material')
        units.append({'id': reference['unit'], 'op': {'kind': 'unreal.author', 'version': '1'},
            'script': SCRIPT, 'code': sorted(set(source_code)), 'inputs': inputs,
            'params': {'args': args, 'settings': []}, 'outputs': [{'id': 'asset',
                'logical_path': reference['package'], 'class': kind, 'destination': 'checkout', 'files': files}]})
        staged[reference['unit']] = {dep: 'inputs/' + dep for dep in deps}
        slots.update({dep: False for dep in deps})
    return {'units': units, 'staged_inputs': staged, 'content_slots': slots,
            'packages': {row['package']: row for name, row in references.items() if name in by_name}}
