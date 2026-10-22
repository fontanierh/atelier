"""Exact membership-only compatibility proof for the city parent handoff.

This does not certify geometry or packages. The native adapter must separately
reproduce the original receipt policy, source bytes, sidecars and current checks.
"""
import ast

ORIGINAL_PARENTS = ('HD_Terrain', 'HD_Streets', 'HD_Square')
PREVIOUS_PARENTS = (*ORIGINAL_PARENTS, 'HD_CivicGardens', 'HD_Park')
PARENTS = (*PREVIOUS_PARENTS, 'HD_Harbor')
IMPORTER = 'games/yorimichi/unreal/Scripts/import_hidamari.py'
CATALOG = 'games/yorimichi/world/asset_catalog.py'
SETUP = 'games/yorimichi/unreal/Scripts/setup_project.py'
PRODUCTS = 'games/yorimichi/city_tile_products.py'
PIECE_IMPORTER = 'games/yorimichi/unreal/Scripts/import_city_surface_tiles.py'
FERRY_SOURCE = 'games/yorimichi/world/regions/hidamari/ferry_source.py'
OLD_FERRY_DOC = ('@cc [owner:fontanierh,label:correctness] hidamari-ferry-package-source\n'
    '    Refuse missing/failed cuts or changed cut code, base mesh, sweep proof and final bytes.\n\n'
    '    The normal Hidamari importer is the sole writer of HD_Harbor. Reimporting the world MUST\n'
    '    select this same validated opening; a later transport import MUST NOT patch the package.\n    ')
NEW_FERRY_DOC = OLD_FERRY_DOC.replace(
    'The normal Hidamari importer is the sole writer of HD_Harbor. Reimporting the world MUST\n'
    '    select this same validated opening; a later transport import MUST NOT patch the package.',
    'The bounded city owner MUST select this same validated opening for every Harbor piece.\n'
    '    Reimporting the world MUST NOT recreate the retired parent; a later transport import\n'
    '    MUST NOT patch the parent or piece packages.')


def _ferry_doc(old, new):
    """Only the exact ownership prose may change; executable AST stays significant."""
    functions = [[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'validated_harbor']
                 for tree in (old, new)]
    if any(len(group) != 1 for group in functions):
        return False
    before, after = (group[0] for group in functions)
    for function, expected in ((before, OLD_FERRY_DOC), (after, NEW_FERRY_DOC)):
        if (not function.body or not isinstance(function.body[0], ast.Expr)
                or not isinstance(function.body[0].value, ast.Constant)
                or function.body[0].value.value != expected):
            return False
    after.body[0] = before.body[0]
    return True


def _remove_current_branch(tree, path, parents=ORIGINAL_PARENTS):
    """Remove exactly one known delegation statement, with its exact location."""
    if path == IMPORTER:
        blocks = [node.body for node in tree.body if isinstance(node, ast.For)
                  and ast.dump(node.target) == ast.dump(ast.parse('for name, entry in manifest.items(): pass').body[0].target)
                  and ast.dump(node.iter) == ast.dump(ast.parse('manifest.items()', mode='eval').body)]
        expected = ast.parse(f"if name in {parents!r}:\n    continue").body[0]
        # It must follow the original selection filter, before source import.
        index = 1
    elif path == CATALOG:
        blocks = [node.body for node in tree.body if isinstance(node, ast.FunctionDef)
                  and node.name == 'independently_owned']
        expected = ast.parse("if package in {'/Game/Japan/Assets/'+name for name in "
                             "('HD_Terrain', 'HD_Streets', 'HD_Square')}:\n    return True").body[0]
        index = 1  # the original function docstring still occupies the first slot
    else:
        return False
    if len(blocks) != 1 or len(blocks[0]) <= index or ast.dump(blocks[0][index]) != ast.dump(expected):
        return False
    del blocks[0][index]
    return True


def _extend_sources(old, new):
    """Only the literal membership and its exact completeness error may differ."""
    def assignment(names):
        return ast.parse(f'SOURCES = {names!r}').body[0]
    matches = [(i, node, names) for i, node in enumerate(old.body)
               for names in (ORIGINAL_PARENTS, PREVIOUS_PARENTS)
               if ast.dump(node) == ast.dump(assignment(names))]
    if len(matches) != 1:
        return False
    index, before, names = matches[0]
    after = assignment(PARENTS)
    if len(new.body) <= index or ast.dump(new.body[index]) != ast.dump(after):
        return False
    new.body[index] = before
    owners = [node for node in new.body if isinstance(node, ast.FunctionDef) and node.name == 'require_sources']
    expected = ast.parse("def require_sources(sources):\n"
        "    if not isinstance(sources, dict) or set(sources) != set(SOURCES):\n"
        "        raise ValueError('City tile import requires all six production surfaces')").body[0]
    if len(owners) != 1 or ast.dump(owners[0]) != ast.dump(expected):
        return False
    cardinality = 'three' if names == ORIGINAL_PARENTS else 'five'
    owners[0].body[0].body[0].exc.args[0].value = f'City tile import requires all {cardinality} production surfaces'
    return True


def _material_wrapper(tree, path):
    """Remove only the exact finite new Harbor binding and its call sites."""
    if path == PRODUCTS:
        expected = ast.parse('''def piece_material_paths(source, slots):
    """Harbor's single authored slot retains its region-owned material."""
    if source == 'HD_Harbor':
        if not isinstance(slots, list) or len(slots) != 1 or not isinstance(slots[0], str) or not slots[0]:
            raise ValueError('Harbor pieces require exactly one source material slot')
        return {slots[0]: '/Game/Japan/Materials/M_Harbor'}
    return material_paths(slots)
''').body[0]
        matches = [i for i, node in enumerate(tree.body) if ast.dump(node) == ast.dump(expected)]
        if len(matches) != 1:
            return False
        del tree.body[matches[0]]
        current, previous = 'piece_material_paths(source, slots)', 'material_paths(slots)'
    elif path == PIECE_IMPORTER:
        imports = [node for node in tree.body if isinstance(node, ast.ImportFrom) and node.module == 'city_tile_products']
        if len(imports) != 1:
            return False
        aliases = [alias for alias in imports[0].names if alias.name == 'piece_material_paths' and alias.asname is None]
        if len(aliases) != 1:
            return False
        aliases[0].name = 'material_paths'
        current = "piece_material_paths(name, source['source_material_slots'])"
        previous = "material_paths(source['source_material_slots'])"
    else:
        return False
    wanted = ast.dump(ast.parse(current, mode='eval').body)
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and ast.dump(node) == wanted]
    if len(calls) != 1:
        return False
    replacement = ast.parse(previous, mode='eval').body
    calls[0].func, calls[0].args, calls[0].keywords = replacement.func, replacement.args, replacement.keywords
    return True


def _extend_importer(old, new):
    """Forward delegation from the original or three-parent owner, never reverse."""
    # Both sides normalize only the exact statement at its original location.
    if not _remove_current_branch(new, IMPORTER, PARENTS):
        return False
    if not _remove_current_branch(old, IMPORTER, PREVIOUS_PARENTS):
        _remove_current_branch(old, IMPORTER, ORIGINAL_PARENTS)
    return True


def _remove_previous_purge(tree):
    """Normalize only the removed upfront namespace deletion, never imports."""
    owners = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main']
    expected = ast.dump(ast.parse('purge()').body[0])
    if len(owners) != 1:
        return False
    indices = [i for i, node in enumerate(owners[0].body) if ast.dump(node) == expected]
    source_load = ast.parse("W = json.load(open(os.path.join(OUT, 'world.json')))").body[0]
    if indices != [4] or ast.dump(owners[0].body[3]) != ast.dump(source_load):
        return False
    del owners[0].body[4]
    return True


def excluded_packages(previous, current):
    """@cc [owner:fontanierh,label:correctness] exact-city-delegation-owner-transition
    Original source texts MUST come from the invocation-bound producing inputs.
    Recovered member projections MUST have identical keys. An exact ORIGINAL
    local receipt header MUST independently prove full historical closure membership;
    receiptless bootstrap and donor transitions MUST remain disabled. Only
    the exact original three-parent delegation, its forward extension to six,
    literal product membership with its cardinality error, exact finite Harbor
    material wrapper/call substitutions, its exact ferry ownership docstring
    replacement and removal of the upfront
    main() purge call MAY differ; all remaining imports and finishing MUST remain identical; every remaining AST MUST agree. These six generated
    parent packages MUST be excluded from historical admission. No other source,
    owner finishing, native validator or byte evidence MAY be relaxed. Unsupported
    history MUST refuse and use the ordinary import path.
    """
    if (not isinstance(previous, dict) or not isinstance(current, dict)
            or not previous or set(previous) != set(current)):
        return None
    changed = False
    try:
        for path in previous:
            old = ast.parse(previous[path])
            new = ast.parse(current[path])
            if ast.dump(old) == ast.dump(new):
                continue
            if path == SETUP:
                if not _remove_previous_purge(old):
                    return None
            elif path == PRODUCTS:
                if not _extend_sources(old, new) or not _material_wrapper(new, path):
                    return None
            elif path == PIECE_IMPORTER:
                if not _material_wrapper(new, path):
                    return None
            elif path == FERRY_SOURCE:
                if not _ferry_doc(old, new):
                    return None
            elif path == IMPORTER:
                if not _extend_importer(old, new) and not _remove_current_branch(new, path):
                    return None
            elif path not in (IMPORTER, CATALOG) or not _remove_current_branch(new, path):
                return None
            if ast.dump(old) != ast.dump(new):
                return None
            changed = True
    except (ValueError, TypeError, SyntaxError):
        return None
    return tuple('/Game/Japan/Assets/'+name for name in PARENTS) if changed else None
