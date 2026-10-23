"""Finite source proof for the atlas-facing part of the atomic export transition.

This does not rerender, recut, or certify a new coast. It compares the actual
height/placement expressions with the immutable source already signed by the
paintings. Render-only export entry points are outside the map's read closure.
"""
import ast
import copy
import hashlib
import json
from pathlib import Path

GAME = Path(__file__).resolve().parents[1]
PREFIX = 'games/yorimichi/'
FIXTURE = GAME / 'tests/fixtures/atlas-atomic-predecessor.json'
WITNESS = 'coasts/atomic-export-equivalence.json'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def dump(node):
    return ast.dump(node, include_attributes=False).replace(', type_params=[]', '')


def restore_record(rel, record, game=GAME):
    """Reconstruct the exact older record before this source-only carry."""
    witness_path = Path(game) / 'world/map/atlas' / WITNESS
    witness = json.loads(witness_path.read_text())
    expected = dict(witness=WITNESS, sha256=sha(witness_path.read_bytes()))
    value = copy.deepcopy(record)
    if value.pop('atomic_export_revalidation', None) != expected:
        raise ValueError('Atlas atomic carry is missing or unbound')
    row = witness['records'][rel]
    for field, previous in row['previous_tables'].items():
        owner = value
        for name in field.split('.')[:-1]:
            owner = owner[name]
        key = field.split('.')[-1]
        if owner[key] != witness['current_geography']:
            raise ValueError('Atlas current source attestation differs')
        owner[key] = previous
    if sha((json.dumps(value, indent=2) + '\n').encode()) != row['previous_record_sha256']:
        raise ValueError('Atlas paid/history record changed during atomic carry')
    return value


def declarations(text):
    result = {}
    for node in ast.parse(text).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            result[node.name] = node
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                for name in ast.walk(target):
                    if isinstance(name, ast.Name):
                        result[name.id] = node
    return result


def closure(nodes, roots):
    pending = list(roots)
    selected = {}
    while pending:
        name = pending.pop()
        if name not in nodes or name in selected:
            continue
        node = nodes[name]
        selected[name] = dump(node)
        pending.extend(n.id for n in ast.walk(node) if isinstance(n, ast.Name) and n.id in nodes)
    return dict(sorted(selected.items()))


def prove(game=GAME):
    """@cc [owner:fontanierh,label:correctness] finite-atlas-atomic-source-carry
    A carry MUST compare actual map-facing declarations against byte-bound immutable
    signed predecessor source, including relocated placement/ground declarations.
    It MUST NOT execute history, change art/paid receipts, normalize heights or
    permit arbitrary geometry deltas. Any changed map expression MUST refuse.
    """
    game = Path(game)
    fixture = json.loads((game / 'tests/fixtures/atlas-atomic-predecessor.json').read_text())
    originals = fixture['files']
    for row in originals.values():
        if sha(row['source'].encode()) != row['sha256']:
            raise ValueError('Immutable atlas predecessor source differs')

    def old(rel):
        return originals[PREFIX + rel]['source']

    def current(rel):
        return (game / rel).read_text()

    comparisons = []
    bound_sources = {rel.removeprefix(PREFIX) for rel in originals}

    def compare(rel, roots, *, previous=None, additions=None):
        bound_sources.add(rel)
        before = declarations(old(previous or rel))
        after = declarations(current(rel))
        if additions:
            after.update(additions)
        expected, actual = closure(before, roots), closure(after, roots)
        if not expected or expected != actual:
            changed = sorted(k for k in set(expected) | set(actual) if expected.get(k) != actual.get(k))
            raise ValueError('Atlas consumed declarations differ: ' + rel + ': ' + ','.join(changed))
        comparisons.append(dict(source=rel, previous_source=previous or rel,
                                declarations=sorted(expected), ast_sha256=sha(json.dumps(expected, sort_keys=True).encode())))

    # The actual map implementation, frames, raster sampling and colour/probe
    # logic are unchanged. Its imports never consume either render constructor.
    map_rel = 'world/map/build_map.py'
    query_read = "        from belmonte.query_arrays import read as final_query\n        mesh = BM_SOURCE.Surface(final_query(yori.OUT / 'belmonte-query-data' / f'{name}-final.npz', owner=name, stage='final')['faces'])"
    old_read = "        mesh = BM_SOURCE.Surface(BM_SOURCE.triangles(yori.OUT / f'belmonte/glb/{name}.glb'))"
    if current(map_rel).count(query_read) != 1 or current(map_rel).replace(query_read, old_read) != old(map_rel):
        raise ValueError('Atlas renderer changed; this finite carry no longer applies')
    imports = [n for n in ast.walk(ast.parse(current(map_rel))) if isinstance(n, (ast.Import, ast.ImportFrom))]
    if any('build_terrain' in dump(n) or "module='hidamari.build'" in dump(n) for n in imports):
        raise ValueError('Atlas unexpectedly reads a render-only source')

    compare('world/regions/hidamari/layout.py',
            ('backdrop_height', 'terrain_axes', 'height', 'north_height'))
    # These are the four exact alias targets of layout's placement imports.
    for name in ('arrival', 'park_grounds', 'station_yard', 'temple_precinct'):
        previous = 'world/regions/hidamari/' + name + '.py'
        rel = 'world/regions/hidamari/' + name + '_placement.py'
        compare(rel, declarations(current(rel)), previous=previous)

    compare('world/regions/hidamari/mountains.py',
            ('height', 'natural_height', 'backdrop_height', 'trail_points', 'BOUNDS', 'VOLCANO'))
    compare('world/regions/southwest/island.py', ('height', 'path_points', 'WAYPOINTS', 'SIZE'))

    # Belmonte's map samples actual final valley triangles. Constant extraction
    # and encoder factoring cannot substitute a natural/partial source here.
    bounds = declarations(current('world/regions/belmonte/terrain_bounds.py'))
    names = declarations(current('world/regions/belmonte/ground_names.py'))
    compare('world/regions/belmonte/terrain.py', ('valley_tile_triangles', 'VALLEY_CARVED_TILES'),
            additions={**bounds, **names})
    compare('world/regions/belmonte/query_surface.py', ('Surface',),
            previous='world/regions/belmonte/source.py')
    # The data-only decoder factors the original function at the file-read
    # boundary. Reconstruct that exact original boundary before AST comparison.
    old_source = declarations(old('world/regions/belmonte/source.py'))
    new_source = declarations(current('world/regions/belmonte/source.py'))
    decoder = copy.deepcopy(new_source['triangles_data'])
    decoder.name = 'triangles'
    decoder.args = copy.deepcopy(old_source['triangles'].args)
    decoder.body[0] = copy.deepcopy(old_source['triangles'].body[0])

    class DecoderBoundary(ast.NodeTransformer):
        def visit_Name(self, node):
            if node.id == 'data':
                return ast.parse('path.read_bytes()', mode='eval').body
            if node.id == 'label':
                return ast.Name(id='path', ctx=ast.Load())
            return node

    decoder = DecoderBoundary().visit(decoder)
    if dump(decoder) != dump(old_source['triangles']):
        raise ValueError('Belmonte complete triangle decoder changed')
    compare('world/regions/belmonte/source.py', ('terrain',), additions={
        'triangles': decoder,
        'Surface': declarations(current('world/regions/belmonte/query_surface.py'))['Surface'],
    })

    # Brinecove's former helpers are the exact current ground sampling helpers;
    # no rounding, offsets or boundary/winding policy is normalized away.
    for rel, roots in (
        ('world/regions/brinecove/ground_sampling.py', ('STEP', '_axis', 'jag_point')),
        ('world/regions/brinecove/boundary.py', ('weld',)),
    ):
        compare(rel, roots, previous='world/regions/brinecove/ground.py')

    # Only this complete, byte-bound natural-reader/cache-signature transition
    # may change route.py. Every sampler, route constant, arithmetic expression,
    # frame and operation outside these two exact boundaries remains unchanged.
    route_rel = 'world/train/route.py'
    route = current(route_rel)
    previous_route = old(route_rel)
    previous_read = """    paths = [yori.OUT / f'belmonte/natural/{name}.glb' for name in ('SM_BM_NorthCountry', 'SM_BM_NorthApron')]
    for p in paths:
        if not p.is_file():
            raise FileNotFoundError(f'missing Belmonte natural ground {p}; run world.belmonte first')
    north = [source.Surface(source.triangles(p)) for p in paths]"""
    current_read = """    from belmonte.surface_data import read
    owners = ('SM_BM_NorthCountry', 'SM_BM_NorthApron')
    packets = [read(yori.OUT / 'belmonte-natural-source-data' / (owner + '.surface'),
                    owner=owner, stage='natural')[1] for owner in owners]
    north = [source.Surface(source.triangles_data(data)) for data in packets]"""
    previous_cache = """            yori.OUT / 'belmonte' / 'natural' / 'SM_BM_NorthApron.glb',
            yori.OUT / 'belmonte' / 'natural' / 'SM_BM_NorthCountry.glb',
            yori.OUT / 'belmonte' / 'glb' / 'SM_BM_NorthApron.glb',
            yori.OUT / 'belmonte' / 'glb' / 'SM_BM_NorthCountry.glb',"""
    current_cache = """            yori.OUT / 'belmonte-natural-source-data' / 'SM_BM_NorthApron.surface',
            yori.OUT / 'belmonte-natural-source-data' / 'SM_BM_NorthCountry.surface',"""
    for actual, previous in ((current_read, previous_read), (current_cache, previous_cache)):
        if route.count(actual) != 1:
            raise ValueError('Atlas natural reader/signature transition differs')
        route = route.replace(actual, previous)
    if route != previous_route:
        raise ValueError('Atlas consumed declarations differ: ' + route_rel)
    reader = fixture['natural_surface_reader']
    reader_rel = reader['path'].removeprefix(PREFIX)
    if (reader['path'] != PREFIX + 'world/regions/belmonte/surface_data.py'
            or sha(reader['source'].encode()) != reader['sha256']
            or current(reader_rel) != reader['source']):
        raise ValueError('Atlas natural source reader differs from immutable binding')
    bound_sources.update((route_rel, reader_rel))
    route_ast = closure(declarations(previous_route), declarations(previous_route))
    comparisons.append(dict(source=route_rel, previous_source=route_rel,
        declarations=sorted(route_ast), ast_sha256=sha(json.dumps(route_ast, sort_keys=True).encode())))
    natural_reader = dict(predecessor_revision=fixture['revision'],
        predecessor_route_sha256=originals[PREFIX + route_rel]['sha256'],
        current_route_sha256=sha(current(route_rel).encode()),
        reader_revision=reader['revision'], reader_source_sha256=reader['sha256'],
        stage='natural', owners=['SM_BM_NorthCountry', 'SM_BM_NorthApron'],
        boundary='exact encoded GLB bytes; original triangles_data decoder and Surface sampler unchanged',
        cache_signature='exact natural .surface filenames replace natural and unused final GLB filenames')

    changed = {}
    for path, row in originals.items():
        rel = path.removeprefix(PREFIX)
        digest = sha((game / rel).read_bytes())
        if digest != row['sha256']:
            changed[rel] = dict(previous_sha256=row['sha256'], current_sha256=digest)
    return dict(schema=1, kind='atomic-export-map-source-equivalence',
                predecessor_revision=fixture['revision'], predecessor_fixture_sha256=sha((game / 'tests/fixtures/atlas-atomic-predecessor.json').read_bytes()),
                renderer_sha256=sha(current(map_rel).encode()), natural_reader_equivalence=natural_reader,
                changed_sources=changed, comparisons=comparisons,
                bound_sources={rel: sha((game / rel).read_bytes()) for rel in sorted(bound_sources | {'world/regions/belmonte/query_arrays.py', 'world/regions/belmonte/terrain_bounds.py', 'world/regions/belmonte/ground_names.py'})},
                render_only_sources=['world/build_terrain.py', 'world/regions/hidamari/build.py'],
                scope='Unchanged atlas-consumed height/placement expressions and exact helper relocations; no new terrain/coast/painting acceptance.')
