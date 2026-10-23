"""The treehouse owns its bounded dressing render pieces and their saved packages."""
import hashlib
import json
import math
from pathlib import Path
import re

from atelier.mesh_geometry import package_inventory
from atelier.mesh_geometry import SIDECARS

PARENT = 'TH_Dressing'
DESTINATION = '/Game/Japan/Treehouse/Pieces'
TRIANGLE_LIMIT = 32768
CELL_METRES = 64
UVS = ('UVMap', 'Piece1', 'Piece2', 'Piece3', 'Piece4')
PROPS = tuple('TH_P_' + slug for slug in (
    'backpack', 'barrel', 'basket', 'bell', 'bookshelf', 'crate_desk', 'futon',
    'globe', 'kamado', 'log_table', 'planter', 'stump_kettle', 'telescope'))
TREES = ('Tree_Canopy_Maple', 'Tree_Canopy_Crimson', 'Tree_Canopy_Amber', 'Tree_Canopy_Ginkgo')
NAME = re.compile(r'TH_Dressing_cell_(?:0|-?[1-9][0-9]*)_(?:0|-?[1-9][0-9]*)(?:_Piece[0-3]{1,16})?')


def bounds(row):
    low, high = row['min'], row['max']
    if (not isinstance(low, list) or not isinstance(high, list) or len(low) != 3 or len(high) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in (*low, *high))
            or any(a > b for a, b in zip(low, high))):
        raise ValueError('Invalid treehouse piece bounds')
    return low, high


def members(manifest):
    """@cc [owner:fontanierh,label:correctness;performance] complete-treehouse-dressing-membership
    TH_Dressing MUST render only its complete bounded replacement set, preserving
    the original placement and five baked UV channels. Every face MUST have one
    child owner; no authored collision or parent fallback MAY enter this set.
    """
    if (not isinstance(manifest, dict) or manifest.get('version') != 1
            or manifest.get('complete') is not True or manifest.get('parent') != PARENT
            or manifest.get('triangle_limit') != TRIANGLE_LIMIT or manifest.get('cell_metres') != CELL_METRES
            or manifest.get('uv_channels') != list(UVS) or manifest.get('collision_boxes') != 0
            or type(manifest.get('source_triangles')) is not int or manifest['source_triangles'] < 1
            or not isinstance(manifest.get('slots'), list) or not manifest['slots']
            or any(not isinstance(s, str) or not re.fullmatch(r'TH_[A-Za-z0-9_]+', s) for s in manifest['slots'])
            or len(set(manifest['slots'])) != len(manifest['slots'])
            or not isinstance(manifest.get('pieces'), list) or not manifest['pieces']):
        raise ValueError('Missing complete treehouse dressing pieces')
    bounds(manifest)
    seen, result = set(), []
    for row in manifest['pieces']:
        if (not isinstance(row, dict) or not isinstance(row.get('name'), str)
                or not NAME.fullmatch(row['name']) or row['name'] in seen
                or type(row.get('triangles')) is not int or not 1 <= row['triangles'] <= TRIANGLE_LIMIT
                or not isinstance(row.get('used_slots'), list) or not row['used_slots']
                or any(slot not in manifest['slots'] for slot in row['used_slots'])
                or len(set(row['used_slots'])) != len(row['used_slots'])
                or not isinstance(row.get('sha256'), str) or not re.fullmatch('[0-9a-f]{64}', row['sha256'])):
            raise ValueError('Invalid bounded treehouse dressing piece')
        bounds(row)
        seen.add(row['name'])
        result.append(row)
    if sum(row['triangles'] for row in result) != manifest['source_triangles']:
        raise ValueError('Incomplete treehouse dressing face union')
    return result


def source_files(out):
    root = Path(out) / 'treehouse'
    manifest = json.loads((root / 'pieces.json').read_text())
    rows = members(manifest)
    files = [root / 'assets/dressing' / (row['name'] + '.fbx') for row in rows]
    for row, path in zip(rows, files):
        if (any(p.is_symlink() for p in (path.absolute(), *path.absolute().parents)) or not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']):
            raise ValueError('Missing or changed treehouse dressing source')
    return files


def sources_present(out):
    try:
        source_files(out)
        old = Path(out) / 'treehouse/assets/TH_Dressing.fbx'
        return not old.exists() and not old.is_symlink()
    except (OSError, ValueError, TypeError, KeyError):
        return False


def parent_absent(content):
    folder = Path(content) / 'Japan/Assets'
    if any(p.is_symlink() for p in (folder.absolute(), *folder.absolute().parents)):
        return False
    return not any(folder.glob(PARENT + '.*'))


def expected_assets(out):
    """The complete current treehouse writer roster; no unrelated namespace scan."""
    root = Path(out) / 'treehouse'
    rows = members(json.loads((root / 'pieces.json').read_text()))
    textures = json.loads((root / 'textures/textures.json').read_text())
    props = json.loads((root / 'props/props.json').read_text())
    trees = json.loads((root / 'trees/trees.json').read_text())
    if set(props) != set(PROPS) or set(trees) != set(TREES):
        raise ValueError('Incomplete current treehouse prop/tree ownership')
    names = (*props, *trees)
    if any(not isinstance(name, str) or not re.fullmatch('[A-Za-z0-9_]+', name) for name in (*names, *textures)):
        raise ValueError('Invalid treehouse native ownership roster')
    result = {'/Game/Japan/Assets/' + name for name in names}
    from treehouse_surfaces import rows as surface_rows
    result.update(row['package'] for row in surface_rows(out))
    result.update('/Game/Japan/Treehouse/Textures/T_TH_' + slug for slug in textures)
    result.update('/Game/Japan/Treehouse/Textures/T_' + key for key in props)
    result.update('/Game/Japan/Treehouse/Materials/MI_TH_' + slug for slug in textures)
    result.update('/Game/Japan/Treehouse/Materials/MI_' + key for key in props)
    result.update('/Game/Japan/Treehouse/Materials/' + key for key in ('M_TreeHouse', 'M_TH_Light', 'MI_TH_pane'))
    if 'bark' in textures:
        result.add('/Game/Japan/Treehouse/Materials/MI_TH_trunk')
    for colour in ('crimson', 'amber'):
        result.add('/Game/Japan/Textures/T_leaf_' + colour)
        result.add('/Game/Japan/Materials/MI_Leaf' + colour.title())
    return sorted(result)


def native_outputs(content):
    """Complete fixed native ownership is knowable before a cold producer runs."""
    content = Path(content)
    packages = ['Japan/Assets/' + name for name in ('TH_Trunks', 'TH_Frame', *PROPS, *TREES)]
    for colour in ('crimson', 'amber'):
        packages += ['Japan/Textures/T_leaf_' + colour, 'Japan/Materials/MI_Leaf' + colour.title()]
    primaries = tuple(content / (package + '.uasset') for package in packages)
    optional = tuple(content / (package + suffix) for package in packages for suffix in SIDECARS if suffix != '.uasset')
    return (content / 'Japan/Treehouse', *primaries), optional


def present(out, content):
    """Require current source membership, complete saved package bytes and retired parent sidecars."""
    try:
        root = Path(out) / 'treehouse'
        rows = members(json.loads((root / 'pieces.json').read_text()))
        report = json.loads((root / 'import-report.json').read_text())
        expected = [DESTINATION + '/' + row['name'] for row in rows]
        assets = report['assets']
        from treehouse_surfaces import retired_parents_absent, rows as surface_rows
        if (report.get('surfaces') != [row['package'] for row in surface_rows(out)] or not retired_parents_absent(content) or report.get('surfaces_sha256') != hashlib.sha256((root/'surfaces.json').read_bytes()).hexdigest()
                or report['pieces_sha256'] != hashlib.sha256((root / 'pieces.json').read_bytes()).hexdigest()
                or report['dressing'] != expected or assets != expected_assets(out) or not parent_absent(content)):
            return False
        return report['files'] == package_inventory(content, assets)
    except (OSError, ValueError, TypeError, KeyError):
        return False
