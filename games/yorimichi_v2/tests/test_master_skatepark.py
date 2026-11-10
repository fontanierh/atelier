"""The skatepark material masters: the pier builder and the skateboard dissolve builder, each traced with a recording stand-in
for unreal and compared call by call against the donor it was extracted from. The donor text is read from the pinned donor
commit (its blob sha256 is checked), and the test is skipped when that commit is not in the local object store. Nothing here
runs Unreal: the native rebuild and the read-back are the editor's job (docs/inventory/master-sources.md, section 5)."""
import ast
import hashlib
import importlib.util
import inspect
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
SCRIPTS = ROOT / 'unreal/Scripts'
sys.path.insert(0, str(ROOT / 'tools' / 'content'))
sys.path.insert(0, str(ROOT / 'tools' / 'migrate'))
import records  # noqa: E402
import master_records as planner  # noqa: E402

DONOR_COMMIT = '7eec0f98dd'
DONOR_PIN = {
    'games/yorimichi/unreal/Scripts/import_skatepark.py':
        '5d07f84d217d82a87e6610344bffdbedefadb457e37cf6b472346ff833b7a9ea',
    'games/yorimichi/unreal/Scripts/board_dissolve_material.py':
        'a201e90d5dc6ccb9fb3f3b4eda753e946d0992a8994518daa2c8259368adaa2e',
}
PIER_KEYS = ('basalt', 'ceramic', 'concrete', 'mural', 'painted', 'steel', 'wood')
PIER_PLAN = {'basalt': 0.0, 'ceramic': 0.0, 'concrete': 0.0, 'mural': 0.0, 'painted': 0.0, 'steel': 1.0, 'wood': 0.0}

FAMILIES = planner.load_families()
PIER = FAMILIES['skatepark']
BOARD = FAMILIES['skatepark_board']


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pier_builders = load_module('v2_skatepark_masters', SCRIPTS / 'material_masters' / 'skatepark_masters.py')
board_builders = load_module('v2_skatepark_board_masters', SCRIPTS / 'material_masters' / 'skatepark_board_masters.py')


def donor_text(path):
    """The donor file at the pinned commit, with its blob sha256 checked. Skips when the commit is not available locally."""
    done = subprocess.run(['git', '-C', str(REPO), 'show', f'{DONOR_COMMIT}:{path}'], capture_output=True)
    if done.returncode != 0:
        pytest.skip(f'donor commit {DONOR_COMMIT} is not in this checkout')
    assert hashlib.sha256(done.stdout).hexdigest() == DONOR_PIN[path], path
    return done.stdout.decode()


# --- a recording stand-in for the unreal module --------------------------------------------------------------------------

class World:
    """The call log, and the node counter, which restarts at each material (delete_all_material_expressions) so that the
    donor's nodes and the builder's nodes get the same names."""

    def __init__(self):
        self.log = []
        self.nodes = 0


def shown(value):
    """A stand-in shows as its identity, a list or tuple of them element by element, and anything else as its repr."""
    if isinstance(value, Token):
        return value._ident
    if isinstance(value, (list, tuple)):
        return '[' + ', '.join(shown(v) for v in value) + ']'
    return repr(value)


class Token:
    """A stand-in for an unreal object, class, enum or library. A snake_case attribute is a method, which is logged when
    called; any other attribute is a child token (a class or a constant). Calling a token logs it as a constructor."""

    def __init__(self, world, ident):
        self._world, self._ident = world, ident

    def __getattr__(self, name):
        if name.startswith('__'):
            raise AttributeError(name)
        if name[:1].islower():
            return Method(self._world, self._ident, name)
        return Token(self._world, f'{self._ident}.{name}')

    def __call__(self, *args):
        self._world.log.append((self._ident.rsplit('.', 1)[-1], '<call>', tuple(shown(a) for a in args)))
        return Token(self._world, f'{self._ident}()')


class Method:
    def __init__(self, world, owner, name):
        self._world, self._owner, self._name = world, owner, name

    def __call__(self, *args):
        world = self._world
        world.log.append((self._name, self._owner, tuple(shown(a) for a in args)))
        if self._name == 'delete_all_material_expressions':
            world.nodes = 0
        if self._name == 'create_material_expression':
            world.nodes += 1
            return Token(world, f'node{world.nodes}')
        if self._name == 'create_asset':
            return Token(world, 'asset')
        if self._name == 'get_asset_tools':
            return Token(world, 'tools')
        if self._name == 'does_asset_exist':
            return False
        return True


def fake_unreal(world):
    return Token(world, 'unreal')


# Calls that are the donor's or the importer's, not the graph: the builder never makes them (or the donor's folder and log
# lines), and the get_asset_tools lookup is the donor's module-level AT, which the builder makes per call.
NOT_GRAPH = {'make_directory', 'save_loaded_asset', 'log', 'get_asset_tools'}


def graph(log):
    return [entry for entry in log if entry[0] not in NOT_GRAPH]


def run_builder(module, builder, package, reads, **arguments):
    world = World()
    original = module.unreal
    module.unreal = fake_unreal(world)
    try:
        getattr(module, builder)(package, reads, **arguments)
    finally:
        module.unreal = original
    return world.log


def by_material(log):
    """{material name: graph entries} for a log that builds one or more materials. Each material starts at its does_asset_exist
    call (the donor and the builder both make it there) and is named by its create_asset call."""
    starts = [i for i, entry in enumerate(log) if entry[0] == 'does_asset_exist']
    out = {}
    for a, b in zip(starts, starts[1:] + [len(log)]):
        segment = log[a:b]
        names = [entry[2][0] for entry in segment if entry[0] == 'create_asset']
        assert len(names) == 1, segment[:3]
        out[ast.literal_eval(names[0])] = graph(segment)
    return out


def pier_reads(key):
    """The loaded texture of each read package: a stand-in whose name is its package, as the donor's texture() returns."""
    roles = ('albedo',) if key == 'mural' else ('albedo', 'normal', 'roughness')
    return {f'/Game/SkatePark/Textures/T_Pier_{key}_{role}': Token(World(), f'/Game/SkatePark/Textures/T_Pier_{key}_{role}')
            for role in roles}


def pier_donor_manifest(tmp_path):
    """The donor's textures.json as tools/pier_texture_finish.py writes it: the steel metallic 1, the others 0, the mural
    with its albedo only. The donor adds `painted` itself (import_skatepark.py line 134)."""
    manifest = {}
    for name in ('basalt', 'ceramic', 'concrete', 'steel', 'wood'):
        manifest[name] = {'metallic': 1.0 if name == 'steel' else 0.0,
                          'maps': {role: f'{name}-{role}.png' for role in ('albedo', 'normal', 'roughness')}}
    manifest['mural'] = {'metallic': 0.0, 'maps': {'albedo': 'mural-albedo.png'}}
    (tmp_path / 'textures').mkdir(exist_ok=True)
    (tmp_path / 'textures' / 'textures.json').write_text(json.dumps(manifest))
    return tmp_path


def run_pier_donor(tmp_path):
    """The donor's materials() (import_skatepark.py lines 132-174), run once over the whole manifest, against the same stand-in.
    Its texture() helper (lines 115-129) is replaced by a stand-in that names the package and imports nothing."""
    text = donor_text('games/yorimichi/unreal/Scripts/import_skatepark.py').splitlines(keepends=True)
    body = ''.join(text[131:174])
    assert body.startswith('def materials():') and body.rstrip().endswith('return result'), 'the donor lines moved'
    world = World()
    unreal = fake_unreal(world)
    namespace = {'json': json, 'OUT': pier_donor_manifest(tmp_path), 'unreal': unreal,
                 'E': unreal.EditorAssetLibrary, 'MEL': unreal.MaterialEditingLibrary, 'AT': Token(world, 'tools'),
                 'texture': lambda file, name, role: Token(world, f'/Game/SkatePark/Textures/{name}')}
    exec(compile(body, 'import_skatepark.py:132-174', 'exec'), namespace)
    namespace['materials']()
    return world.log


# --- the builders exist, import without the editor and bind to their family entries ---------------------------------------

def test_both_builder_modules_import_without_the_editor_and_define_their_builders():
    assert pier_builders.unreal is None and board_builders.unreal is None
    assert callable(pier_builders.pier_material) and callable(board_builders.board_dissolve)


def test_each_family_master_binds_to_its_builder_signature():
    for family in (PIER, BOARD):
        module = pier_builders if family is PIER else board_builders
        for master in family['masters']:
            inspect.signature(getattr(module, master['builder'])).bind(
                master['package'], {r: object() for r in master['reads']}, **master['arguments'])


def test_the_families_are_planned_for_the_right_adopted_records_and_masters():
    assert PIER['adopted'] == 'adopted/skatepark/materials' and BOARD['adopted'] == 'adopted/skatepark/board'
    assert [m['id'] for m in PIER['masters']] == [f'master/skatepark/pier-{k}' for k in PIER_KEYS]
    assert [m['package'] for m in PIER['masters']] == [f'/Game/SkatePark/Materials/M_Pier_{k}' for k in PIER_KEYS]
    assert [m['id'] for m in BOARD['masters']] == ['master/skatepark/board-dissolve']
    assert PIER['fallback'] == 'master/skatepark/pier-concrete' and BOARD['fallback'] == 'master/skatepark/board-dissolve'
    for family in (PIER, BOARD):
        assert set(family) == {'name', 'adopted', 'owner', 'license', 'builder', 'donor', 'donor_lines', 'fallback', 'masters'}
        assert {m['builder'] for m in family['masters']} == set(family['donor_lines'])


def test_the_metallic_argument_is_the_donor_value_for_every_pier():
    for master in PIER['masters']:
        key = master['arguments']['key']
        assert master['arguments'] == {'key': key, 'metallic': PIER_PLAN[key]}, key
    assert {k: v for k, v in PIER_PLAN.items() if v} == {'steel': 1.0}


def test_the_mural_reads_only_its_albedo_and_the_others_read_all_three_maps():
    by_id = {m['package']: m for m in PIER['masters']}
    assert by_id['/Game/SkatePark/Materials/M_Pier_mural']['reads'] == ['/Game/SkatePark/Textures/T_Pier_mural_albedo']
    for key in PIER_KEYS:
        if key != 'mural':
            assert len(by_id[f'/Game/SkatePark/Materials/M_Pier_{key}']['reads']) == 3


# --- the wiring: each builder, against the donor it was extracted from --------------------------------------------------

def run_pier_builders():
    return {key: graph(run_builder(pier_builders, 'pier_material', f'/Game/SkatePark/Materials/M_Pier_{key}', pier_reads(key),
                                   key=key, metallic=PIER_PLAN[key])) for key in PIER_KEYS}


@pytest.fixture(scope='module')
def donor_piers(tmp_path_factory):
    return {name: entries for name, entries in by_material(run_pier_donor(tmp_path_factory.mktemp('pier'))).items()}


@pytest.mark.parametrize('key', PIER_KEYS)
def test_a_pier_builder_wires_as_the_donor_loop_body_does_for_its_key(key, donor_piers):
    """The donor loop body (lines 136-173) and the builder make the same calls in the same order, with the same classes,
    values, node names and connections, for every key. Metallic comes from the family argument, which is the donor's value."""
    assert len(donor_piers[f'M_Pier_{key}']) > 10   # a non-empty comparison: the donor's graph was read
    assert donor_piers[f'M_Pier_{key}'] == run_pier_builders()[key]


def test_the_donor_metallic_is_the_family_argument_for_every_pier(donor_piers):
    """The donor's one constant with an r value is the metallic (import_skatepark.py line 167), so its value is the argument."""
    for key in PIER_KEYS:
        radii = [args for name, _, args in donor_piers[f'M_Pier_{key}']
                 if name == 'set_editor_property' and args[0] == "'r'"]
        assert radii == [("'r'", repr(PIER_PLAN[key]))], key


def test_the_mural_base_colour_is_the_albedo_sample_alone(donor_piers):
    """The mural has no vertex-colour modulation (donor line 152): no VertexColor and no Custom expression is made for it."""
    for log in (donor_piers['M_Pier_mural'], run_pier_builders()['mural']):
        created = [args[1] for name, _, args in log if name == 'create_material_expression']
        assert 'unreal.MaterialExpressionCustom' not in created
        assert 'unreal.MaterialExpressionVertexColor' not in created
        assert created == ['unreal.MaterialExpressionTextureSample', 'unreal.MaterialExpressionConstant',
                           'unreal.MaterialExpressionMultiply']


def test_the_board_builder_wires_as_the_donor_module_body_does(monkeypatch):
    text = donor_text('games/yorimichi/unreal/Scripts/board_dissolve_material.py')
    world = World()
    monkeypatch.setitem(sys.modules, 'unreal', fake_unreal(world))
    exec(compile(text, 'board_dissolve_material.py', 'exec'), {'__name__': 'donor_board'})
    donor = graph(world.log)
    built = graph(run_builder(board_builders, 'board_dissolve', '/Game/SkatePark/Board/M_BoardDissolve', {}))
    assert len(donor) > 50   # a non-empty comparison: the donor's module body was read
    assert built == donor
    assert ("'parameter_name'", "'Dissolve'") in [args for name, _, args in built if name == 'set_editor_property']
    assert ("'opacity_mask_clip_value'", '0.5') in [args for name, _, args in built if name == 'set_editor_property']


def test_no_builder_saves_or_makes_a_directory_itself(donor_piers):
    logs = list(run_pier_builders().values())
    logs.append(graph(run_builder(board_builders, 'board_dissolve', '/Game/SkatePark/Board/M_BoardDissolve', {})))
    for log in logs:
        assert not {name for name, _, _ in log} & {'save_loaded_asset', 'save_asset', 'make_directory'}


# --- the planner, the real records and the reference rewrites -----------------------------------------------------------

def test_the_planner_loads_both_families_and_each_is_unprepared_on_the_real_tree():
    assert {'skatepark', 'skatepark_board'} <= set(FAMILIES)
    for family in (PIER, BOARD):
        assert planner.state(REPO / 'games' / 'yorimichi_v2', family) == 'unprepared'


def test_every_master_read_is_an_output_of_its_declared_input_records():
    for family in (PIER, BOARD):
        for master in family['masters']:
            outputs = set()
            for dep in master['inputs']:
                outputs |= {o.package for o in records.load_asset(ROOT / 'assets' / dep / 'asset.toml').outputs}
            missing = [r for r in master['reads'] if not r.startswith('/Engine/') and r not in outputs]
            assert missing == [], (master['id'], missing)
            assert [e for e in master['inputs'] if not (ROOT / 'assets' / e / 'asset.toml').is_file()] == []


def test_the_planned_master_records_load_as_material_masters_with_their_pinned_builder(tmp_path):
    for family in (PIER, BOARD):
        sha = planner.builder_sha(family)
        for master in family['masters']:
            path = tmp_path / master['id'] / 'asset.toml'
            path.parent.mkdir(parents=True)
            path.write_text(planner.record_text(family, master, sha))
            asset = records.load_asset(path)
            assert asset.kind == 'material-master' and asset.authority == 'generated'
            assert asset.recipe['settings']['builder'] == master['builder']
            assert [s.sha256 for s in asset.sources] == [sha]
            assert [o.package for o in asset.outputs] == [master['package']]
            owned = {dep: set(master['reads']) for dep in asset.input_dependencies}
            assert records.material_input_problems(asset, owned) == []
            assert sorted(asset.input_dependencies) == sorted(master['inputs'])


def test_the_builder_sources_are_pinned_to_the_builder_files():
    assert planner.builder_path(PIER).name == 'skatepark_masters.py'
    assert planner.builder_path(BOARD).name == 'skatepark_board_masters.py'
    assert planner.builder_path(PIER).is_file() and planner.builder_path(BOARD).is_file()


def test_each_referencing_record_points_at_the_masters_its_slot_map_names(tmp_path):
    """The 17 records that reference adopted/skatepark/materials each name their masters in slot_map. The rewrite points each
    at exactly those masters, and nothing is left on the adopted record. The fallback (Pier_concrete, the surface 16 of the 17
    name) is not used by any of them, since each names a master. Read from the real tree; nothing is written."""
    game = REPO / 'games' / 'yorimichi_v2'
    rewrites = planner.reference_rewrites(game, PIER)
    assert len(rewrites) == 17
    for rel, data in rewrites.items():
        original = (game / rel).read_text()
        slots = re_slots(original)
        expected = sorted({f'master/skatepark/pier-{slot[len("Pier_"):]}' for slot in slots})
        rewritten = tmp_path / rel.replace('/', '_')
        rewritten.write_bytes(data)
        asset = records.load_asset(rewritten)
        assert PIER['adopted'] not in asset.references, rel
        assert sorted(r for r in asset.references if r.startswith('master/skatepark/')) == expected, rel


def re_slots(text):
    match = re.search(r'slot_map = \{(.*)\}', text)
    return re.findall(r'(Pier_\w+) = "', match.group(1)) if match else []


def test_the_inventory_rows_for_these_masters_name_the_planned_record_and_family():
    """The inventory rows (docs/inventory/master-sources.json) for the eight masters name the record the family plans for each
    package, and the family that plans it."""
    rows = json.loads((ROOT / 'docs/inventory/master-sources.json').read_text())['masters']
    planned = {m['package']: (family['name'], m) for family in (PIER, BOARD) for m in family['masters']}
    skate = [row for row in rows if row['package'].startswith('/Game/SkatePark/')]
    assert len(skate) == 8
    for row in skate:
        family_name, master = planned[row['package']]
        assert row['record'] == master['id'] and row['family'] == family_name, row['package']
        assert row['status'] == f'planned (family {family_name})', row['package']
