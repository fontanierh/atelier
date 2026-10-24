"""Observation-only qualification of the three original Treehouse library variants.

No assembly, inventory, validation, copy or retention helper is executed. The
frozen observations do not grant native, cache, ctypes or completion authority.
"""
import ast
from dataclasses import dataclass
import os
from pathlib import Path
import stat


TREES = ('Tree_Canopy_Maple', 'Tree_Canopy_Crimson', 'Tree_Canopy_Amber', 'Tree_Canopy_Ginkgo')
PROPS = tuple('TH_P_' + slug for slug in (
    'backpack', 'barrel', 'basket', 'bell', 'bookshelf', 'crate_desk', 'futon',
    'globe', 'kamado', 'log_table', 'planter', 'stump_kettle', 'telescope'))
SURFACES = ('TH_Structure', 'TH_Frame', 'TH_Trunks', 'TH_Dressing')
ROSTERS = {'trees': TREES, 'props': PROPS, 'surfaces': ()}
CODE_SOURCES = (
    'games/yorimichi/treehouse_pieces.py',
    'games/yorimichi/treehouse_surfaces.py',
    'games/yorimichi/world/mesh_pieces.py',
    'games/yorimichi/world/region_mesh_parts.py',
    'games/yorimichi/world/region_plan_files.py',
    'games/yorimichi/world/regions/treehouse/assemble_atomic.py',
    'games/yorimichi/world/yori.py',
    *(f'platform/studio/atelier/{name}.py' for name in (
        '__init__', 'atomic_files', 'export_assembly', 'export_manifest', 'file_copy',
        'mesh_cells', 'mesh_collision', 'mesh_geometry', 'mesh_ir', 'mesh_materials',
        'mesh_partition', 'model_files', 'paths')),
)


class UnsupportedTreehouseLibrary(ValueError):
    """The declaration is outside the three reviewed original library variants."""


@dataclass(frozen=True)
class TreehouseLibrary:
    step: str
    kind: str
    script: Path
    arguments: tuple[str, ...]
    raw_inputs: tuple[Path, ...]
    produced_inputs: tuple[Path, ...]
    code_inputs: tuple[Path, ...]
    products: tuple[tuple[str, tuple[Path, ...]], ...]


def _source(checkout, path):
    from atelier.build_v2.controller_client import MAX_SOURCE_FILE_BYTES, _read_at
    try:
        return _read_at(checkout, Path(path).relative_to(checkout).as_posix(), MAX_SOURCE_FILE_BYTES)
    except (OSError, ValueError) as error:
        raise UnsupportedTreehouseLibrary(f'library source is absent, linked or invalid: {path}') from error


def _directory(path):
    try:
        info = path.lstat()
    except FileNotFoundError as error:
        raise UnsupportedTreehouseLibrary(f'library source directory is absent: {path}') from error
    if not stat.S_ISDIR(info.st_mode):
        raise UnsupportedTreehouseLibrary(f'library source directory is linked: {path}')


def _output(path, *, directory=False):
    from atelier.build_v2.controller_client import _open_root
    current = path
    while True:
        try:
            info = current.lstat()
        except FileNotFoundError:
            if current == current.parent:
                raise UnsupportedTreehouseLibrary(f'library output has no real ancestor: {path}') from None
            current = current.parent
            continue
        expected = stat.S_ISDIR if directory or current != path else stat.S_ISREG
        if not expected(info.st_mode):
            raise UnsupportedTreehouseLibrary(f'library output is linked or invalid: {current}')
        if stat.S_ISDIR(info.st_mode):
            try:
                descriptor = _open_root(current)
                os.close(descriptor)
            except OSError as error:
                raise UnsupportedTreehouseLibrary(f'library output ancestry is linked: {current}') from error
            break
        current = current.parent


def _props_literal(tree):
    node = next(node for node in tree.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == 'PROPS' for target in node.targets))
    value = node.value
    if (not isinstance(value, ast.Call) or not isinstance(value.func, ast.Name) or value.func.id != 'tuple'
            or len(value.args) != 1 or value.keywords
            or not isinstance(value.args[0], ast.GeneratorExp)):
        raise UnsupportedTreehouseLibrary('PROPS is not the original literal generator')
    generator = value.args[0]
    if (len(generator.generators) != 1 or generator.generators[0].is_async
            or not isinstance(generator.generators[0].target, ast.Name)
            or generator.generators[0].target.id != 'slug' or generator.generators[0].ifs
            or not isinstance(generator.elt, ast.BinOp) or not isinstance(generator.elt.op, ast.Add)
            or ast.literal_eval(generator.elt.left) != 'TH_P_'
            or not isinstance(generator.elt.right, ast.Name) or generator.elt.right.id != 'slug'):
        raise UnsupportedTreehouseLibrary('PROPS literal prefix or slug binding differs')
    return tuple('TH_P_' + slug for slug in ast.literal_eval(generator.generators[0].iter))


def _literal(tree, name):
    node = next(node for node in tree.body if isinstance(node, (ast.Assign, ast.AnnAssign))
                and any(isinstance(target, ast.Name) and target.id == name
                        for target in (node.targets if isinstance(node, ast.Assign) else [node.target])))
    return ast.literal_eval(node.value)


def _scanner_type():
    from atelier import build_inputs
    # The recipe's optimized subclass bypasses resolve and can reuse live closure
    # caches. Use the existing uncached scanner so this instance's guard sees every
    # candidate; retain the original resolver, traversal and ordering unchanged.
    return next(cls for cls in build_inputs.ImportScanner.__mro__
                if cls.__module__ == 'atelier.source_imports' and cls.__name__ == 'ImportScanner')


def _source_roles(checkout, script, constructor, pieces):
    try:
        constructor_ast = ast.parse(_source(checkout, constructor), filename=str(constructor))
        if (_literal(constructor_ast, 'TREES') != TREES or _props_literal(constructor_ast) != PROPS
                or _literal(constructor_ast, 'SURFACES') != SURFACES):
            raise UnsupportedTreehouseLibrary('literal Treehouse constructor rosters differ')
        assemble = next(node for node in constructor_ast.body
                        if isinstance(node, ast.FunctionDef) and node.name == 'assemble')
        reads = next(node for node in constructor_ast.body
                     if isinstance(node, ast.FunctionDef) and node.name == 'assembly_reads')
        if (not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == 'local_imports' for node in ast.walk(assemble))
                or not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                           and node.func.id == 'assembly_reads' for node in ast.walk(constructor_ast))
                or not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                           and node.func.attr == 'startswith' for node in ast.walk(reads))):
            raise UnsupportedTreehouseLibrary('library constructor source roles differ')
        pieces_ast = ast.parse(_source(checkout, pieces), filename=str(pieces))
        if _literal(pieces_ast, 'TREES') != TREES or _props_literal(pieces_ast) != PROPS:
            raise UnsupportedTreehouseLibrary('library file-only source rosters differ')
        source_ast = ast.parse(_source(checkout, script), filename=str(script))
        if _literal(source_ast, 'PARENTS') != SURFACES:
            raise UnsupportedTreehouseLibrary('library surface source parents differ')
        functions = {node.name: node for node in source_ast.body if isinstance(node, ast.FunctionDef)}
        if set(('library', 'surfaces', 'main')) - functions.keys():
            raise UnsupportedTreehouseLibrary('library parser or file-only dispatch is absent')
        main = functions['main']
        choices = next((node for node in ast.walk(main) if isinstance(node, ast.keyword)
                        and node.arg == 'choices'), None)
        dispatch = next((node for node in main.body if isinstance(node, ast.If)), None)
        expected_dispatch = ast.parse(
            "if args.kind=='surfaces':surfaces(args.out)\nelse:library(args.out,args.kind,args.name)").body[0]
        if (choices is None or ast.literal_eval(choices.value) != ('surfaces', 'props', 'trees')
                or dispatch is None
                or ast.dump(dispatch, include_attributes=False) != ast.dump(
                    expected_dispatch, include_attributes=False)):
            raise UnsupportedTreehouseLibrary('library parser or exact kind dispatch differs')
        parser_calls = {ast.dump(node, include_attributes=False)
                        for node in ast.walk(main) if isinstance(node, ast.Call)}
        for expression in ("parser.add_argument('--out',type=Path,required=True)",
                           "parser.add_argument('--kind',choices=('surfaces','props','trees'),required=True)",
                           "parser.add_argument('--name',action='append')"):
            if ast.dump(ast.parse(expression, mode='eval').body,
                        include_attributes=False) not in parser_calls:
                raise UnsupportedTreehouseLibrary('library exact parser controls differ')
        for name in ('library', 'surfaces'):
            calls = {ast.dump(node.func, include_attributes=False)
                     for node in ast.walk(functions[name]) if isinstance(node, ast.Call)}
            required = {ast.dump(ast.parse(expression, mode='eval').body, include_attributes=False)
                        for expression in ('export_assembly.assemble', 'validate_export',
                                           'copy_verified', 'atomic_json')}
            if not required <= calls:
                raise UnsupportedTreehouseLibrary(f'library {name} file-only assembly roles differ')
        library_nodes = {ast.dump(node, include_attributes=False)
                         for node in ast.walk(functions['library'])}
        roster = ast.parse(
            "if tuple(names)!=tuple(PROPS if kind=='props' else TREES):"
            "raise ValueError('Incomplete logical Treehouse library roster')").body[0]
        region = ast.parse("region='treehouse_'+kind").body[0]
        if (ast.dump(roster, include_attributes=False) not in library_nodes
                or ast.dump(region, include_attributes=False) not in library_nodes):
            raise UnsupportedTreehouseLibrary('library kind roster/source mapping differs')
    except UnsupportedTreehouseLibrary:
        raise
    except (OSError, SyntaxError, ValueError, TypeError, StopIteration) as error:
        raise UnsupportedTreehouseLibrary('library source roles are missing or invalid') from error


def _read_roles(output_root, kind, reads):
    region = 'treehouse_surfaces' if kind == 'surfaces' else 'treehouse_' + kind
    names = SURFACES if kind == 'surfaces' else ROSTERS[kind]
    prefix = {
        'trees': [f'{region}.atomic', 'treehouse.canopy_dimensions', 'treehouse.canopy_recolours'],
        'props': [f'{region}.atomic', *(f'treehouse.prop_data.{name}' for name in names)],
        'surfaces': [f'{region}.atomic', 'treehouse.surface_metadata'],
    }[kind]
    geometry = [f'{region}.geometry.{name}' for name in names]
    exports = [f'world.{region}.export.{name}' for name in names]
    if reads != [*prefix, *geometry, *exports]:
        raise UnsupportedTreehouseLibrary(
            'library current direct read roster is incomplete or future/expanded declarations are required')
    paths = {
        f'{region}.atomic': (output_root / 'atomic_regions' / region,),
        'treehouse.canopy_dimensions': (output_root / 'treehouse-data/canopy/trees.json',),
        'treehouse.canopy_recolours': (output_root / 'treehouse-data/canopy/recoloured',),
        'treehouse.surface_metadata': (output_root / 'treehouse-data/surfaces/runtime.json',
                                      output_root / 'treehouse-data/surfaces/manifest.json'),
    }
    paths.update({f'treehouse.prop_data.{name}': (output_root / 'treehouse-data/props' / name,)
                  for name in PROPS})
    paths.update({f'{region}.geometry.{name}': (output_root / 'planned_exports' / region / name,)
                  for name in names})
    paths.update({f'world.{region}.export.{name}': (output_root / 'exports' / f'world.{region}.export' / name,)
                  for name in names})
    return tuple(path for read in reads for path in paths[read])


def qualify_treehouse_library(step, *, checkout: Path, output_root: Path) -> TreehouseLibrary:
    """@cc [owner:fontanierh,label:correctness;safety] closed-treehouse-library-observation
    Qualification MUST bind only the three actual full-recipe file-only library variants,
    exact source/argv/direct-read/product rosters and original controls. Current direct reads
    MUST include declared logical and raw-export products without OUT-parent authority;
    cold zero-plan declarations MUST refuse pending original Discovery/Advance. Fixed bounded
    nofollow sources precede inert discovery; generated paths MUST NOT be source-read, created
    or certified. No helper execution, ctypes/native/cache/Finish or generic-family authority.
    """
    from atelier import build, build_products
    from atelier.build_v2.controller_client import _open_root

    if (type(checkout) is not type(Path()) or type(output_root) is not type(Path())
            or '..' in checkout.parts or '..' in output_root.parts):
        raise UnsupportedTreehouseLibrary('library anchors must be exact normalized Paths')
    expected_steps = {'trees': 'world.treehouse_trees', 'props': 'world.treehouse_props',
                      'surfaces': 'world.treehouse'}
    kinds = {name: kind for kind, name in expected_steps.items()}
    if (type(step) is not build.Step or type(step.name) is not str or step.name not in kinds
            or not checkout.is_absolute() or not output_root.is_absolute()
            or checkout == Path(checkout.anchor) or output_root == Path(output_root.anchor)):
        raise UnsupportedTreehouseLibrary('not an exact Treehouse library Step and absolute anchors')
    kind = kinds[step.name]
    names = ROSTERS[kind]
    try:
        descriptor = _open_root(checkout)
        os.close(descriptor)
    except OSError as error:
        raise UnsupportedTreehouseLibrary('library checkout is not a real anchored directory') from error
    game = checkout / 'games/yorimichi'
    world = game / 'world'
    regions = world / 'regions'
    studio = checkout / 'platform/studio/atelier'
    for path in (game, world, regions, regions / 'treehouse', studio):
        _directory(path)
    script = regions / 'treehouse/assemble_atomic.py'
    arguments = ('--out', str(output_root), '--kind', kind,
                 *(item for name in names for item in ('--name', name)))
    produced = _read_roles(output_root, kind, step.reads)
    expected_products = {
        'trees': (('treehouse.trees', (output_root / 'treehouse/trees',)),
                  ('treehouse.tree_meshes', (output_root / 'treehouse/assembled-trees',))),
        'props': (('treehouse.props', (output_root / 'treehouse/props',)),
                  ('treehouse.prop_meshes', (output_root / 'treehouse/assembled-props',))),
        'surfaces': (('treehouse.meshes', (output_root / 'treehouse/assets',
                                           output_root / 'treehouse/pieces.json',
                                           output_root / 'treehouse/surfaces.json',
                                           output_root / 'treehouse/manifest.json')),
                     ('treehouse.runtime', (output_root / 'treehouse/runtime.json',))),
    }[kind]
    output_directories = {'treehouse.trees', 'treehouse.tree_meshes', 'treehouse.props',
                          'treehouse.prop_meshes', 'treehouse.meshes'}
    for name, paths_ in expected_products:
        for path in paths_:
            _output(path, directory=name in output_directories and path.name == 'assets'
                    or name in {'treehouse.trees', 'treehouse.tree_meshes', 'treehouse.props',
                                'treehouse.prop_meshes'})
    for path in produced:
        _output(path, directory=path.suffix != '.json')

    defaults = {
        'deferred_inputs': [], 'needs': [], 'after': [], 'outputs': [], 'heavy': False,
        'pool_roots': [], 'explicit': False, 'verify': None, 'cutoff': False, 'references': [],
        'cache': True, 'audit': False, 'optional_inputs': [], 'queries': [], 'toolchain': False,
        'batch': None, 'cook_recovery': None, 'checkpoint_previous_needs': None,
        'checkpoint_restore': None, 'checkpoint_outputs': (), 'candidate_scope': None,
        'replan': False, 'controller': None,
    }
    dynamic = {'name', 'commands', 'inputs', 'about', 'products', 'reads'}
    if (set(vars(step)) - dynamic != set(defaults)
            or any(type(vars(step)[name]) is not type(value) or vars(step)[name] != value
                   for name, value in defaults.items())
            or getattr(step, '_query_bindings', None) not in (None, ())):
        raise UnsupportedTreehouseLibrary('library Step controls or flags differ')
    if len(step.commands) != 1:
        raise UnsupportedTreehouseLibrary('library requires exactly one original Python command')
    command = step.commands[0]
    if (type(command) is not build.Python or set(vars(command)) != {'script', 'args'}
            or type(command.script) is not type(script) or command.script != script
            or type(command.args) is not tuple or command.args != arguments
            or not all(type(value) is str for value in command.args)):
        raise UnsupportedTreehouseLibrary('library script or exact argument roster differs')
    if type(step.products) is not list or len(step.products) != 2:
        raise UnsupportedTreehouseLibrary('library requires its two original Products')
    products = []
    for product, (name, paths_) in zip(step.products, expected_products):
        if (type(product) is not build_products.Product
                or set(vars(product)) != {'name', 'paths', 'collection', 'bounds', 'optional_paths'}
                or product.name != name or product.paths != paths_
                or type(product.paths) is not tuple
                or any(type(path) is not type(script) for path in product.paths)
                or product.collection is not None or product.bounds is not None or product.optional_paths):
            raise UnsupportedTreehouseLibrary('library product or complete output ownership differs')
        products.append((product.name, product.paths))

    # Close the finite original source roster before the existing inert scanner can
    # resolve links. Generated or foreign declared inputs never reach a source reader.
    expected_code = tuple(checkout / relative for relative in CODE_SOURCES)
    if (type(step.inputs) is not list or len(step.inputs) != len(expected_code) or any(
            type(actual) is not type(expected) or actual != expected
            for actual, expected in zip(step.inputs, expected_code))):
        raise UnsupportedTreehouseLibrary('library enriched source membership/order differs')
    for source in expected_code:
        _source(checkout, source)
    _source_roles(checkout, script, game / 'treehouse_atomic_build.py', game / 'treehouse_pieces.py')
    scanner = _scanner_type()()
    resolve = scanner.resolve
    def checked_resolution(root, parts):
        found = resolve(root, parts)
        for source in found:
            if source not in expected_code:
                raise UnsupportedTreehouseLibrary(f'library import escapes its closed source roster: {source}')
            _source(checkout, source)
        return found
    # Keep original resolution semantics, but refuse an unexpected candidate before
    # the original scanner opens it. This is observation, never import execution.
    scanner.resolve = checked_resolution
    local = scanner.local_imports(script, (world, regions, game))
    code = []
    for path in local:
        try:
            mapped = studio / path.relative_to(studio)
        except ValueError:
            try:
                mapped = world / path.relative_to(world)
            except ValueError:
                try:
                    mapped = game / path.relative_to(game)
                except ValueError as error:
                    raise UnsupportedTreehouseLibrary(f'library source has a foreign root: {path}') from error
        code.append(mapped)
    if len(set(code)) != len(code):
        raise UnsupportedTreehouseLibrary('library code closure duplicates a source role')
    if (type(step.inputs) is not list or len(step.inputs) != len(code) or any(
            type(actual) is not type(expected) or actual != expected
            for actual, expected in zip(step.inputs, code))):
        raise UnsupportedTreehouseLibrary('library enriched source membership/order differs')
    for source in code:
        _source(checkout, source)
    return TreehouseLibrary(step.name, kind, script, arguments, (), produced, tuple(code), tuple(products))
