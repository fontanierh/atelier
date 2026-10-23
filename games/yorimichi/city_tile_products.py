"""Exact ownership of generated city visibility pieces inside one native tag."""
import re
import math
from pathlib import Path
from atelier.conventions import to_unreal
from atelier.model_files import regular_files
from atelier.atomic_files import atomic_json
import json

SOURCES = ('HD_Terrain', 'HD_Streets', 'HD_Square', 'HD_CivicGardens', 'HD_Park', 'HD_Harbor')
CELL = r'(?:0|-?[1-9][0-9]*)'
DESTINATION = '/Game/Experiments/CitySurfaces/v1_128m'
TRIANGLE_LIMIT = 32768


def require_sources(sources, expected=SOURCES):
    if not isinstance(sources, dict) or set(sources) != set(expected):
        raise ValueError('City tile import requires all six production surfaces' if expected == SOURCES
                         else 'City tile import requires the complete production source roster')


def native_bounds(tile):
    """Blender world metres -> Unreal centimetres, including handedness."""
    low, high = tile['min'], tile['max']
    if (len(low) != 3 or len(high) != 3 or any(type(v) not in (float, int) or not math.isfinite(v) for v in (*low, *high))
            or any(a > b for a, b in zip(low, high))):
        raise ValueError('Invalid city piece bounds')
    a, b = to_unreal(low), to_unreal(high)
    return ((a[0], b[1], a[2]), (b[0], a[1], b[2]))


def production_groups(manifest, *, parents=SOURCES, version=2, material_bindings=None, whole_small=False):
    """@cc [owner:fontanierh,label:correctness;performance] city-pieces-replace-native-parents
    Production pieces MUST cover every declared parent triangle exactly once and
    retain its placement frame and source material table. Authored collision hulls
    MUST have exactly one piece owner; every piece retains its own complex surface.
    Missing, partial or unbounded membership MUST refuse before loading a parent or
    publishing replacement data. This table MUST contain no parent mesh reference.
    """
    if (not isinstance(manifest, dict) or manifest.get('version') != version
            or manifest.get('complete') is not True or manifest.get('tag') != 'v1_128m'
            or manifest.get('triangle_limit') != TRIANGLE_LIMIT):
        raise ValueError('Missing complete production city pieces')
    sources = manifest.get('sources')
    require_sources(sources, expected=parents)
    groups, seen = {}, set()
    for source, row in sources.items():
        if not isinstance(row, dict):
            raise ValueError('Invalid production city source record')
        count = row.get('source_triangles')
        hulls = row.get('source_collision_hulls')
        vertices = row.get('source_collision_vertices')
        slots = row.get('source_material_slots')
        if (type(count) is not int or count < 1 or type(hulls) is not int or hulls < 0
                or not isinstance(slots, list) or not slots
                or any(not isinstance(slot, str) or not slot for slot in slots)
                or len(set(slots)) != len(slots)
                or not isinstance(vertices, list) or len(vertices) != hulls
                or any(not isinstance(hull, list) or len(hull) < 4
                       or any(not isinstance(vertex, list) or len(vertex) != 3
                              or any(type(v) not in (float, int) or not math.isfinite(v) for v in vertex)
                              for vertex in hull) for hull in vertices)
                or not isinstance(row.get('tiles'), list) or not row['tiles']):
            raise ValueError('Invalid production city source metadata')
        native_bounds(row['source_bounds'])
        (material_bindings or piece_material_paths)(source, slots)
        pieces = []
        for tile in row['tiles']:
            if not isinstance(tile, dict):
                raise ValueError('Invalid city piece record')
            name, triangles, collision = tile.get('name'), tile.get('triangles'), tile.get('collision_hulls')
            bounded_whole = whole_small and name == source and len(row['tiles']) == 1 and count <= TRIANGLE_LIMIT
            if ((not tile_name(source, name) and not bounded_whole) or name in seen or type(triangles) is not int
                    or not 1 <= triangles <= TRIANGLE_LIMIT or type(collision) is not int
                    or collision not in (0, hulls)):
                raise ValueError('Invalid bounded production city piece')
            native_bounds(tile)
            seen.add(name)
            pieces.append(dict(asset=DESTINATION+'/'+name+'.'+name, triangles=triangles,
                               collision_hulls=collision))
        if (sum(piece['triangles'] for piece in pieces) != count
                or sum(piece['collision_hulls'] for piece in pieces) != hulls
                or sum(piece['collision_hulls'] > 0 for piece in pieces) != int(hulls > 0)):
            raise ValueError('Incomplete city geometry or collision ownership')
        groups[source] = pieces
    return groups


def material_paths(slots):
    """The same authored HDS slots bind the city's existing owned materials."""
    result = {}
    for name in slots:
        if not isinstance(name, str) or not re.fullmatch(r'HDS_[a-z][a-z0-9_]*', name):
            raise ValueError('Unsupported production city material slot')
        slug = name.removeprefix('HDS_')
        result[name] = ('/Game/Japan/Materials/MI_Road' if slug == 'road' else
                        '/Game/Japan/Hidamari/Materials/MI_HD_'+slug)
    return result


def piece_material_paths(source, slots):
    """Harbor's single authored slot retains its region-owned material."""
    if source == 'HD_Harbor':
        if not isinstance(slots, list) or len(slots) != 1 or not isinstance(slots[0], str) or not slots[0]:
            raise ValueError('Harbor pieces require exactly one source material slot')
        return {slots[0]: '/Game/Japan/Materials/M_Harbor'}
    return material_paths(slots)


def _bijection(left, right, equivalent):
    """Match complete unordered multisets, including ambiguous nearby values."""
    if len(left) != len(right): return False
    edges = [[j for j, candidate in enumerate(right) if equivalent(value, candidate)] for value in left]
    owners = {}
    for first in range(len(left)):
        pending = [first]; previous = {}; visited = set(); found = None
        for current in pending:
            for target in edges[current]:
                if target in visited: continue
                visited.add(target); previous[target] = current
                if target not in owners:
                    found = target; break
                pending.append(owners[target])
            if found is not None: break
        if found is None: return False
        # Reverse the augmenting path without recursion or dropping multiplicity.
        while found is not None:
            current = previous[found]
            former = next((target for target, owner in owners.items() if owner == current), None)
            owners[found] = current
            found = former
    return True


def collision_matches(mesh, row, tile, *, read_vertices=None):
    """Read actual imported UCX vertices, including each native shape transform.

    FBX metre/axis conversion may round coordinates to float32; the comparison
    permits two float32 ulps, with a 0.001 cm floor. No hull/vertex may disappear.
    """
    # FKConvexElem.Transform is protected in reflected Python. Native code uses
    # its public getter and rejects nonconvex/nonfinite shapes before readback.
    if read_vertices is None:
        import unreal
        read_vertices = unreal.CitySurfaceValidation.collision_vertices
    try:
        hulls = json.loads(read_vertices(mesh))
    except (ValueError, TypeError):
        return False
    if (not isinstance(hulls, list)
            or any(not isinstance(hull, list) or len(hull)<4
                   or any(not isinstance(point, list) or len(point)!=3
                          or any(type(v) not in (float, int) or not math.isfinite(v) for v in point)
                          for point in hull) for hull in hulls)):
        return False
    expected = row['source_collision_vertices'] if tile['collision_hulls'] else []
    if len(hulls) != len(expected):
        return False
    # Import may reorder hulls and vertices. Convex geometry is identified by
    # its complete vertex set, rather than just its count or bounding box.
    # Lexicographic sorting is invalid under the existing rounding allowance:
    # nearly equal X values may swap two vertices whose Y/Z differ greatly.
    def point_matches(left, right):
        return all(abs(a-b) <= max(.001, 2.**(math.frexp(max(abs(a), abs(b)))[1]-23))
                   for a, b in zip(left, right))
    return _bijection(expected, hulls, lambda left, right: _bijection(left, right, point_matches))


def protected_files(root):
    """A local mutation guard, not a byte certificate or cross-run reuse proof.

    The piece importer never owns writes beneath this sibling root. Observe all
    regular file identities without rereading gigabytes of unrelated assets.
    """
    root = Path(root).absolute()
    if any(path.is_symlink() for path in (root, *root.parents)):
        raise ValueError('Linked protected city content')
    result = {}
    for name in regular_files(root):
        info = (root / name).stat()
        result[name] = (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    return result


def tile_name(source, name):
    return isinstance(name, str) and re.fullmatch(re.escape(source) + '_cell_' + CELL + '_' + CELL + r'(?:_Piece[0-3]{1,16})?', name) is not None


def owned_tiles(asset_paths, destination, *, parents=SOURCES, whole_small=False):
    """Enumerate only generated tile names inside the owner's exact tag root."""
    report = {source: [] for source in parents}
    for asset in asset_paths:
        if not isinstance(asset, str) or not asset.startswith(destination + '/'):
            continue
        name = asset[len(destination) + 1:].split('.')[0]
        for source, tiles in report.items():
            if tile_name(source, name) or (whole_small and name == source):
                if asset != destination + '/' + name + '.' + name:
                    raise ValueError('Invalid generated city tile object path')
                tiles.append({'name': name, 'asset': asset})
                break
    return report


def obsolete_assets(previous, current, destination, *, parents=SOURCES, whole_small=False):
    """@cc [owner:fontanierh,label:correctness] retire-only-superseded-city-pieces
    Only previously inventoried owned tiles inside this exact destination MAY
    retire, after every current tile has imported and validated. Source packages,
    other tags and current pieces MUST never enter the deletion list. Invalid
    ownership evidence MUST refuse rather than widen the deletion scope.
    """
    if not isinstance(destination, str) or not re.fullmatch('/Game/Experiments/CitySurfaces/[A-Za-z0-9_]+', destination):
        raise ValueError('Invalid city tile destination')

    def inventory(report):
        if not isinstance(report, dict):
            raise ValueError('Invalid city tile ownership report')
        found = set()
        for source, tiles in report.items():
            if source not in parents or not isinstance(tiles, list):
                raise ValueError('Invalid city tile source membership')
            for tile in tiles:
                if not isinstance(tile, dict):
                    raise ValueError('Invalid city tile record')
                name = tile.get('name')
                if not tile_name(source, name) and not (whole_small and name == source):
                    raise ValueError('Invalid city tile package name')
                asset = destination + '/' + name + '.' + name
                if tile.get('asset') != asset or asset in found:
                    raise ValueError('Invalid or duplicate city tile package ownership')
                found.add(asset)
        return found

    return sorted(inventory(previous) - inventory(current))


def assemble(root, log=print):
    """Assemble completed independent city sources without regenerating siblings."""
    root = Path(root)
    sources = {}
    for source in SOURCES:
        report = json.loads((root / source / 'manifest.json').read_text())
        if (report.get('version') != 2 or report.get('complete') is not True
                or report.get('tag') != 'v1_128m' or report.get('cell_metres') != 128
                or report.get('triangle_limit') != TRIANGLE_LIMIT
                or set(report.get('sources', {})) != {source}):
            raise ValueError('Incomplete independent city source: '+source)
        sources[source] = report['sources'][source]
    result = dict(version=2, complete=True, tag='v1_128m', cell_metres=128,
                  triangle_limit=TRIANGLE_LIMIT, sources=sources)
    production_groups(result)
    # Source subfolders own current products. Retire only the former flat FBX
    # membership after all replacements exist; never remove a sibling owner.
    if any(path.is_symlink() for path in (root.absolute(), *root.absolute().parents)):
        raise ValueError('Linked city assembly root')
    actual = regular_files(root)
    expected = {source+'/'+tile['name']+'.fbx'
                for source,row in sources.items() for tile in row['tiles']}
    if not expected <= actual:
        raise ValueError('Missing completed city source member')
    legacy = [name for name in actual if '/' not in name and name.endswith('.fbx')
              and any(tile_name(source, name[:-4]) for source in SOURCES)]
    atomic_json(root / 'manifest.json', result)
    for name in legacy:
        (root / name).unlink()
    log('CITY PIECES assembled '+str(sum(len(row['tiles']) for row in sources.values())))


def parents_retired(content):
    """A receiving absence postcondition, independent of copied piece products."""
    root = Path(content) / 'Japan/Assets'
    if any(path.is_symlink() for path in (root.absolute(), *root.absolute().parents)):
        return False
    # Every regular sidecar is covered by the exact primary stem; never scan
    # or claim ownership of another world's package directory.
    return all(not path.exists() and not path.is_symlink()
               for name in SOURCES for path in root.glob(name+'.*'))
