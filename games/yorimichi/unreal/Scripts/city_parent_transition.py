"""Exact membership-only compatibility proof for the city parent handoff.

This does not certify geometry or packages. The native adapter must separately
reproduce the original receipt policy, source bytes, sidecars and current checks.
"""
import ast

ORIGINAL_PARENTS = ('HD_Terrain', 'HD_Streets', 'HD_Square')
PARENTS = (*ORIGINAL_PARENTS, 'HD_CivicGardens', 'HD_Park')
IMPORTER = 'games/yorimichi/unreal/Scripts/import_hidamari.py'
CATALOG = 'games/yorimichi/world/asset_catalog.py'
SETUP = 'games/yorimichi/unreal/Scripts/setup_project.py'
PRODUCTS = 'games/yorimichi/city_tile_products.py'


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
    before, after = assignment(ORIGINAL_PARENTS), assignment(PARENTS)
    indices = [i for i, node in enumerate(old.body) if ast.dump(node) == ast.dump(before)]
    if (len(indices) != 1 or len(new.body) <= indices[0]
            or ast.dump(new.body[indices[0]]) != ast.dump(after)):
        return False
    new.body[indices[0]] = before
    owners = [node for node in new.body if isinstance(node, ast.FunctionDef) and node.name == 'require_sources']
    expected = ast.parse("def require_sources(sources):\n"
        "    if not isinstance(sources, dict) or set(sources) != set(SOURCES):\n"
        "        raise ValueError('City tile import requires all five production surfaces')").body[0]
    if len(owners) != 1 or ast.dump(owners[0]) != ast.dump(expected):
        return False
    owners[0].body[0].body[0].exc.args[0].value = 'City tile import requires all three production surfaces'
    return True


def _extend_importer(old, new):
    """Forward delegation from the original or three-parent owner, never reverse."""
    # Both sides normalize only the exact statement at its original location.
    if not _remove_current_branch(new, IMPORTER, PARENTS):
        return False
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
    the exact original three-parent delegation, its forward extension to five,
    literal product membership with its cardinality error and removal of the upfront
    main() purge call MAY differ; imports and finishing MUST remain identical; every remaining AST MUST agree. These five generated
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
                if not _extend_sources(old, new):
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
