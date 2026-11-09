"""Brine Cove split batch 1: the pure parts of the planner (objects.toml and runtime-file edits, placement check)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'migrate'))
import brinecove_split_apply as apply  # noqa: E402


def part(obj, soft=False, tiles=('Props_3_3',), triangles=10):
    return {'object': obj, 'soft': soft, 'record': apply.record_id(obj, soft), 'mesh': apply.mesh_name(obj, soft),
            'package': apply.MESHES + apply.mesh_name(obj, soft), 'triangles': triangles, 'tiles': list(tiles),
            'slots': [apply.MATERIALS + 'MI_BC_wood'], 'sha256': '0' * 64, 'materials': ['BC_wood'], 'min': [0, 0, 0],
            'max': [1, 1, 1], 'share': {t: triangles for t in tiles}}


def group(name, collision=True, translation=(0.0, 0.0, 0.0)):
    return {'asset': f'/Game/Brinecove/Meshes/{name}.{name}', 'collision': collision, 'cull_cm': 120000,
            'materials': ['/Game/Brinecove/Materials/MI_BC_wood.MI_BC_wood', '/Game/Brinecove/Materials/MI_BC_rope.MI_BC_rope'],
            'plant': False, 'shadow': True,
            'transforms': [{'rotation_xyzw': [0, 0, 0, 1], 'scale': [1, 1, 1], 'translation_cm': list(translation)}]}


def plan():
    return {'parts': {('cannon-west', False): part('cannon-west'), ('crane-west', False): part('crane-west', tiles=('Harbor_2_3',)),
                      ('crane-west', True): part('crane-west', True, tiles=('Harbor_2_3_Soft',))},
            'remainders': {'Props_3_3': {'slots': [apply.MATERIALS + 'MI_BC_rope'], 'triangles': 5},
                           'Harbor_2_3': {'slots': [apply.MATERIALS + 'MI_BC_wood'], 'triangles': 3},
                           'Harbor_2_3_Soft': None,
                           'Ships_4_3': None},
            'tiles': {}}


def test_names():
    assert apply.mesh_name('galleon-nightjar', False) == 'SM_BC_GalleonNightjar'
    assert apply.mesh_name('crane-west', True) == 'SM_BC_CraneWest_Soft'
    assert apply.record_id('crane-west', True) == 'prop/brinecove/crane-west-soft'
    assert apply.tile_record('Harbor_5_3_Soft') == 'prop/brinecove/harbor-5-3-soft'
    assert apply.tile_record('Market_3_4_Piece130') == 'prop/brinecove/market-3-4-piece130'


def test_runtime_edit_adds_parts_updates_remainders_and_drops_retired():
    data = {'groups': [group('SM_BC_Props_3_3'), group('SM_BC_Harbor_2_3'), group('SM_BC_Harbor_2_3_Soft', collision=False),
                       group('SM_BC_Ships_4_3'), group('SM_BC_Other_1_1')]}
    out = apply.edit_runtime(data, plan())
    names = apply.group_names(out)
    assert 'SM_BC_Ships_4_3' not in names and 'SM_BC_Harbor_2_3_Soft' not in names      # retired tiles
    assert names.count('SM_BC_CannonWest') == 1 and names.count('SM_BC_CraneWest') == 1
    assert names.count('SM_BC_CraneWest_Soft') == 1 and 'SM_BC_Other_1_1' in names
    cannon = next(g for g in out['groups'] if g['asset'].endswith('SM_BC_CannonWest.SM_BC_CannonWest'))
    assert cannon['collision'] is True and cannon['transforms'] == data['groups'][0]['transforms']
    soft = next(g for g in out['groups'] if g['asset'].endswith('SM_BC_CraneWest_Soft.SM_BC_CraneWest_Soft'))
    assert soft['collision'] is False
    tile = next(g for g in out['groups'] if g['asset'].endswith('SM_BC_Props_3_3.SM_BC_Props_3_3'))
    assert tile['materials'] == ['/Game/Brinecove/Materials/MI_BC_rope.MI_BC_rope']        # the remainder's slots


def test_runtime_edit_is_idempotent():
    data = {'groups': [group('SM_BC_Props_3_3'), group('SM_BC_Harbor_2_3'), group('SM_BC_Harbor_2_3_Soft', collision=False)]}
    once = apply.edit_runtime(data, plan())
    assert apply.edit_runtime(once, plan()) == once


HEAD = '''# head
schema = 1
tag = "brinecove"
data = "brinecove/runtime.json"

[[objects]]
id = "object/brinecove/wreck"
group = "SM_BC_Ships_2_2"
model = "prop/brinecove/wreck"
about = "the wreck"

'''
TAIL = apply.MARKER + ''' (rerun to regenerate) ---

[[objects]]
id = "object/brinecove/ships-nightjar-sloop"
groups = ["SM_BC_Ships_4_2", "SM_BC_Ships_4_3"]
model = "adopted/brinecove/ships-nightjar-sloop"
about = "ships"

[[objects]]
id = "object/brinecove/props-3-3"
group = "SM_BC_Props_3_3"
model = "prop/brinecove/props-3-3"
about = "props"
'''


def test_objects_toml_edit_adds_objects_retires_ships_and_is_idempotent():
    import tomllib
    text = apply.edit_objects_toml(HEAD + TAIL, plan(), set())
    items = tomllib.loads(text)['objects']
    ids = [i['id'] for i in items]
    assert 'object/brinecove/ships-nightjar-sloop' not in ids
    assert ids.count('object/brinecove/cannon-west') == 1 and 'object/brinecove/wreck' in ids
    crane = next(i for i in items if i['id'] == 'object/brinecove/crane-west')
    assert crane['groups'] == ['SM_BC_CraneWest', 'SM_BC_CraneWest_Soft']
    assert crane['model'] == ['prop/brinecove/crane-west', 'prop/brinecove/crane-west-soft']
    assert apply.edit_objects_toml(text, plan(), set()) == text


def test_expected_shape():
    p = plan()
    p['tiles'] = {'Props_3_3': {'record': 'prop/brinecove/props-3-3', 'package': '/Game/x', 'triangles': 15, 'owner': 'o',
                                'references': [], 'settings': {}, 'material_package': {}}}
    p['remainders'] = {'Props_3_3': {'sha256': 'a', 'triangles': 5, 'materials': ['BC_rope']}}
    p['parts'] = {('cannon-west', False): part('cannon-west', triangles=10)}
    exp = apply.expected(p)
    assert exp['shares']['Props_3_3'] == {'prop/brinecove/cannon-west': 10}
    assert 5 + 10 == exp['tiles']['Props_3_3']['source_triangles']
