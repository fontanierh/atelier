"""Brine Cove ships: the pure parts (generator-vertex assignment, hull split, objects.toml and runtime edits)."""
import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'migrate'))
import brinecove_ships as ships  # noqa: E402
import brinecove_split as split  # noqa: E402
import towns  # noqa: E402

LAYOUT = {'galleon-adventure': (-44.0, -70.0), 'galleon-nightjar': (40.0, -132.0), 'sloop-east': (252.0, -72.0)}
CELLS = ('SM_BC_Hero_GalleonHull_cell_-1_-1', 'SM_BC_Hero_GalleonHull_cell_-1_0',
         'SM_BC_Hero_GalleonHull_cell_0_-1', 'SM_BC_Hero_GalleonHull_cell_0_0')


def xform(name, z=-7.0):
    x, y = LAYOUT[name]
    return {'rotation_xyzw': [0, 0, 0, 1], 'scale': [1, 1, 1], 'translation_cm': [x * 100, -y * 100, z]}


def group(mesh, transforms=None, collision=True):
    return {'asset': f'/Game/Brinecove/Meshes/{mesh}.{mesh}', 'collision': collision, 'cull_cm': 60000,
            'materials': ['/Game/Brinecove/Materials/MI_BC_hull.MI_BC_hull'], 'plant': False, 'shadow': True,
            'transforms': transforms if transforms is not None else [xform('galleon-adventure')]}


def runtime():
    hulls = [group(c, [xform(n) for n in LAYOUT]) for c in CELLS]
    return {'groups': [group('SM_BC_Before')] + hulls + [group('SM_BC_Plant_A'), group('SM_BC_Plant_A'), group('SM_BC_Ships_4_3')]}


# --- assignment by generator vertices ---

def tri(mat, *pts):
    return mat, tuple(pts)      # corners are glTF (x, y up, z); the ground plane is (x, z)


def test_owner_is_the_ship_whose_vertices_coincide_within_two_millimetres():
    index = ships.vertex_index({'a': [('BC_rope', 1.0, 2.0), ('BC_rope', 1.5, 2.0), ('BC_rope', 1.0, 2.5)],
                                'b': [('BC_rope', 50.0, 60.0), ('BC_rope', 50.5, 60.0), ('BC_rope', 50.0, 60.5)]})
    m, c = tri('BC_rope', (1.0009, 9.0, 2.0), (1.5, 3.0, 2.0011), (1.0, 5.0, 2.5))
    assert ships.triangle_owner(index, m, c) == ('a', False)
    m, c = tri('BC_rope', (50.0, 1.0, 60.0), (50.5, 1.0, 60.0), (50.0, 1.0, 60.5))
    assert ships.triangle_owner(index, m, c) == ('b', False)


def test_a_cell_border_does_not_lose_a_match():
    x = 0.0049999              # rounds to cell 0, the GLB corner (+1.5 mm) to cell 1
    index = ships.vertex_index({'a': [('BC_wood', x, 0.0)] * 3})
    assert ships.owners_of(index, 'BC_wood', x + 0.0015, 0.0) == {'a'}


def test_material_or_position_mismatch_leaves_the_triangle_in_the_remainder():
    index = ships.vertex_index({'a': [('BC_rope', 1.0, 2.0)] * 3})
    assert ships.triangle_owner(index, 'BC_wood', ((1.0, 0, 2.0),) * 3) == (None, False)
    assert ships.triangle_owner(index, 'BC_rope', ((1.01, 0, 2.0),) * 3) == (None, False)


def test_a_triangle_two_ships_both_own_is_ambiguous_not_guessed():
    index = ships.vertex_index({'a': [('BC_rope', 1.0, 2.0)], 'b': [('BC_rope', 1.0, 2.0)]})
    assert ships.triangle_owner(index, 'BC_rope', ((1.0, 0, 2.0),) * 3) == (None, True)


def test_assigner_maps_ships_to_objects_and_reports_ambiguity():
    index = ships.vertex_index({'galleon-nightjar': [('BC_rope', 1.0, 2.0)] * 3,
                                'sloop-east': [('BC_rope', 9.0, 9.0)] * 3,
                                'galleon-adventure': [('BC_rope', 5.0, 5.0)] * 3})
    problems = []
    run = ships.make_assigner(index, ships.OBJECTS, problems)
    tris = [tri('BC_rope', *[(1.0, 0, 2.0)] * 3), tri('BC_rope', *[(9.0, 0, 9.0)] * 3),
            tri('BC_rope', *[(5.0, 0, 5.0)] * 3), tri('BC_rope', *[(3.0, 0, 3.0)] * 3)]
    out = run('Ships_4_3', tris, [], {'galleon-nightjar': {}, 'sloop-east': {}})
    assert out == {'galleon-nightjar': [0], 'sloop-east': [1], '': [2, 3]}     # an unlisted ship stays in the remainder
    assert problems == []


def test_compute_takes_the_assigner_instead_of_the_radius(monkeypatch):
    pos = [(0, 0, 0), (1, 0, 0), (0, 0, 1), (5, 0, 5), (6, 0, 5), (5, 0, 6)]
    model = {'materials': ['BC_rope'], 'prims': [{'material': 0, 'positions': pos, 'indices': [0, 1, 2, 3, 4, 5]}]}
    monkeypatch.setattr(split, 'wanted_tiles', lambda glb, objs: ['Ships_9_9'])
    monkeypatch.setattr(split, 'read_glb', lambda path: model)
    seen = []

    def run(stem, tris, comps, allowed):
        seen.append((stem, len(tris), sorted(allowed)))
        return {'a': [1], '': [0]}
    done = split.compute(Path('.'), {'a': dict(tiles=('Ships_9_9',))}, run)
    assert seen == [('Ships_9_9', 2, ['a'])] and done['owned']['Ships_9_9'] == {'a': [1], '': [0]}
    assert done['problems'] == []                       # parts + remainder are exactly the tile


def test_the_objects_name_the_donor_ships_and_their_tiles():
    assert {o['ship'] for o in ships.OBJECTS.values()} == {'galleon-nightjar', 'sloop-east'}
    assert set(ships.TILES) == {t for o in ships.OBJECTS.values() for t in o['tiles']}
    assert ships.HULL_SHIPS == ('galleon-adventure', 'galleon-nightjar', 'sloop-east')     # layout.SHIPS order


# --- the hull, one group per instance ---

def test_instance_of_reads_the_translation():
    assert ships.instance_of(xform('sloop-east'), LAYOUT) == 'sloop-east'
    with pytest.raises(ships.SplitError):
        ships.instance_of({'translation_cm': [1.0, 2.0, 0.0]}, LAYOUT)


def test_hull_split_keeps_cells_in_place_with_the_first_instance_and_appends_the_rest():
    data = runtime()
    out = ships.split_hull_groups(data, LAYOUT)
    names = [towns.mesh_name(g) for g in out['groups']]
    assert names[1:5] == list(CELLS)                               # the cell groups keep their places
    assert len(out['groups']) == len(data['groups']) + 8
    assert all(len(g['transforms']) == 1 for g in out['groups'] if ships.is_hull(g))
    assert names[len(data['groups']):] == list(CELLS) * 2          # nightjar's four, then the sloop's four
    tail = out['groups'][len(data['groups']):]
    assert [ships.instance_of(g['transforms'][0], LAYOUT) for g in tail] == ['galleon-nightjar'] * 4 + ['sloop-east'] * 4
    for g in tail:                                                 # flags and materials copied from the shared group
        assert g['collision'] is True and g['cull_cm'] == 60000 and g['materials'] == data['groups'][1]['materials']


def test_hull_split_does_not_move_a_group_before_the_appended_ones():
    data = runtime()
    before = towns.group_keys(data)
    after = towns.group_keys(ships.split_hull_groups(data, LAYOUT))
    # the plant pair (duplicate names, positional keys) keeps its key
    assert [k for k in before if k.startswith('SM_BC_Plant_A')] == [k for k in after if k.startswith('SM_BC_Plant_A')]


def test_hull_split_is_idempotent_and_keeps_every_transform():
    data = runtime()
    once = ships.split_hull_groups(data, LAYOUT)
    assert ships.split_hull_groups(once, LAYOUT) == once
    got = sorted((towns.mesh_name(g), tuple(g['transforms'][0]['translation_cm'])) for g in once['groups'] if ships.is_hull(g))
    want = sorted((c, tuple(xform(n)['translation_cm'])) for c in CELLS for n in LAYOUT)
    assert got == want                                            # 12 hulls, the same 3 transforms in each of 4 cells
    assert data == runtime()                                       # the input is not changed


def test_hull_keys_name_each_ships_four_groups_by_position():
    out = ships.split_hull_groups(runtime(), LAYOUT)
    keys = ships.hull_keys(out, LAYOUT)
    assert all(len(v) == 4 for v in keys.values())
    assert keys['galleon-adventure'] == [f'{c}#{i}' for i, c in zip(range(1, 5), CELLS)]
    assert len({k for v in keys.values() for k in v}) == 12
    with pytest.raises(ships.SplitError):
        ships.hull_keys(runtime(), LAYOUT)                          # still shared: apply first


# --- objects.toml and runtime ---

def plan():
    def part(obj, tiles):
        return {'object': obj, 'soft': False, 'record': ships.apply.record_id(obj, False), 'mesh': ships.apply.mesh_name(obj, False),
                'package': ships.apply.MESHES + ships.apply.mesh_name(obj, False), 'triangles': 10, 'tiles': list(tiles),
                'slots': [ships.apply.MATERIALS + 'MI_BC_rope'], 'share': {t: 10 for t in tiles}}
    return {'parts': {('galleon-nightjar', False): part('galleon-nightjar', ('Ships_4_2', 'Ships_4_3')),
                      ('sloop-east', False): part('sloop-east', ('Ships_4_3', 'Ships_5_3'))},
            'remainders': {'Ships_4_2': None, 'Ships_4_3': None, 'Ships_5_3': None}, 'tiles': {}, 'ships': LAYOUT}


def test_runtime_edit_adds_parts_and_splits_hulls_and_retire_drops_the_tiles():
    data = runtime()
    identity = [{'rotation_xyzw': [0, 0, 0, 1], 'scale': [1, 1, 1], 'translation_cm': [0.0, 0.0, 0.0]}]
    data['groups'] += [group('SM_BC_Ships_4_2', identity), group('SM_BC_Ships_5_3', identity)]
    data['groups'][-3]['transforms'] = identity       # the fused tiles are placed at identity
    kept = ships.edited_runtime(data, plan(), LAYOUT)
    names = ships.apply.group_names(kept)
    assert 'SM_BC_Ships_4_3' in names and names.count('SM_BC_GalleonNightjar') == 1 and names.count('SM_BC_SloopEast') == 1
    assert sum(len(g['transforms']) for g in kept['groups'] if ships.is_hull(g)) == 12
    gone = ships.edited_runtime(data, plan(), LAYOUT, retire=True)
    names = ships.apply.group_names(gone)
    assert not {'SM_BC_Ships_4_2', 'SM_BC_Ships_4_3', 'SM_BC_Ships_5_3'} & set(names)


def test_runtime_edit_is_idempotent_and_hull_keys_survive_a_rerun():
    data = runtime()
    identity = [{'rotation_xyzw': [0, 0, 0, 1], 'scale': [1, 1, 1], 'translation_cm': [0.0, 0.0, 0.0]}]
    data['groups'] += [group('SM_BC_Ships_4_2', identity), group('SM_BC_Ships_4_3', identity), group('SM_BC_Ships_5_3', identity)]
    once = ships.edited_runtime(data, plan(), LAYOUT)
    assert ships.edited_runtime(once, plan(), LAYOUT) == once
    assert ships.hull_keys(once, LAYOUT) == ships.hull_keys(ships.edited_runtime(once, plan(), LAYOUT), LAYOUT)


TOML = '''# head
[[objects]]
id = "object/brinecove/wreck"
group = "SM_BC_Ships_2_2"
model = "x/wreck"
about = "w"

# --- Generated by tools/migrate/towns.py: every other runtime group of the region (rerun to regenerate) ---
[[objects]]
id = "object/brinecove/hero-galleon-hull"
groups = ["SM_BC_Hero_GalleonHull_cell_-1_-1", "SM_BC_Hero_GalleonHull_cell_-1_0"]
model = "adopted/brinecove/hero-galleon-hull"
about = "h"

[[objects]]
id = "object/brinecove/ships-nightjar-sloop"
groups = ["SM_BC_Ships_4_2", "SM_BC_Ships_4_3", "SM_BC_Ships_5_3"]
model = "adopted/brinecove/ships-nightjar-sloop"
about = "s"
'''


def test_objects_toml_pairs_each_rig_with_its_hull_and_drops_the_shared_hero_entry():
    keys = ships.hull_keys(ships.split_hull_groups(runtime(), LAYOUT), LAYOUT)
    entries = ships.object_entries(plan(), keys)
    assert [e['id'] for e in entries] == ['object/brinecove/galleon-nightjar', 'object/brinecove/sloop-east',
                                          'object/brinecove/galleon-adventure-hull']
    night = entries[0]
    assert night['groups'] == ['SM_BC_GalleonNightjar'] + keys['galleon-nightjar']
    assert night['models'] == ['prop/brinecove/galleon-nightjar', ships.HULL_MODEL]
    assert entries[2]['groups'] == keys['galleon-adventure'] and entries[2]['models'] == [ships.HULL_MODEL]
    text = ships.edit_objects_toml(TOML, entries, (ships.HERO_OBJECT,))
    import tomllib
    listed = {o['id']: o for o in tomllib.loads(text)['objects']}
    assert 'object/brinecove/hero-galleon-hull' not in listed and 'object/brinecove/ships-nightjar-sloop' in listed
    assert listed['object/brinecove/sloop-east']['groups'][0] == 'SM_BC_SloopEast'
    assert len(listed['object/brinecove/sloop-east']['model']) == 2
    assert ships.edit_objects_toml(text, entries, (ships.HERO_OBJECT,)) == text            # a rerun is a no-op
    final = ships.edit_objects_toml(text, entries, ships.RETIRED_OBJECTS)
    assert 'ships-nightjar-sloop' not in final and final.index('# --- Generated') < len(final)
    claimed = [g for o in tomllib.loads(final)['objects'] for g in ([o['group']] if 'group' in o else o['groups'])]
    assert len(claimed) == len(set(claimed))                                                # every group is listed once


def test_run_step_writes_under_the_scopes_it_authorized(monkeypatch, tmp_path):
    """The shared execute takes the authorized scopes (keyword-only) and the step's lockable test."""
    calls = {}
    lockable = object()
    monkeypatch.setattr(ships.apply.Journal, 'recover', lambda self, claim: [])
    monkeypatch.setattr(ships, 'compute', lambda *a, **k: {'writes': {}, 'deletes': []})
    monkeypatch.setattr(ships, 'touched', lambda *a, **k: {'paths': ['p'], 'scopes': ['region/w09-brinecove']})
    monkeypatch.setattr(ships.apply.authority, 'authorize', lambda paths, claim, what, scopes: calls.setdefault('auth', scopes))
    monkeypatch.setattr(ships.apply, 'execute',
                        lambda game, ops, *, scopes, lockable: calls.update(scopes=scopes, lockable=lockable))
    for retire in (False, True):
        calls.clear()
        ships.run_step(tmp_path, {}, 'TASK', retire=retire, lockable=lockable, echo=lambda *_: None)
        assert calls['scopes'] == calls['auth'] == ['region/w09-brinecove'] and calls['lockable'] is lockable
