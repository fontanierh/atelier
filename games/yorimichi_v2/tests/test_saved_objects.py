"""tools/test/saved_objects.py's pure check: a saved object must draw every instance its runtime group places."""
import sys
from pathlib import Path

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME / 'tools/test'))
import saved_objects  # noqa: E402

LISTED = {'tag': 'brinecove', 'objects': [{'id': 'object/brinecove/wreck', 'group': 'SM_BC_Ships_2_2'}]}
DATA = {'bounds_m': [-10, -10, 10, 10], 'origin_cm': [0.0, 0.0, 0.0], 'groups': [
    {'asset': '/Game/BrineCove/SM_BC_Ships_2_2.SM_BC_Ships_2_2', 'plant': False,
     'transforms': [{'translation_cm': [0, 0, 0]}, {'translation_cm': [500, -500, 0]},
                    {'translation_cm': [900000, 0, 0]}]}]}   # the last lies outside the district: never drawn


def found(count):
    return {'SM_BC_Ships_2_2': [['V2ScenePatch', 'brinecove:wreck', count, [0, 0, 0]]]}


def test_expected_instances_apply_the_runtime_bounds_filter():
    assert saved_objects.expected_instances(DATA) == {'SM_BC_Ships_2_2': 2}


def test_a_saved_object_drawing_no_or_too_few_instances_fails():
    expected = saved_objects.expected_instances(DATA)
    assert saved_objects.check(LISTED, found(2), expected) == {}
    for count in (0, 1, 3):
        problems = saved_objects.check(LISTED, found(count), expected)
        assert problems == {'object/brinecove/wreck': [f'SM_BC_Ships_2_2: {count} instance(s) drawn, 2 expected']}


def test_a_group_the_runtime_file_does_not_place_fails():
    assert 'places no instance' in saved_objects.check(LISTED, found(1), {})['object/brinecove/wreck'][0]


def test_groups_sharing_a_mesh_are_checked_by_their_summed_instances():
    """Cell pieces and `#index` groups name their mesh by prefix; one object's actor draws them together, and another
    object listing that mesh is not a duplicate."""
    listed = {'tag': 'brinecove', 'objects': [
        {'id': 'object/brinecove/fern-a', 'groups': ['SM_Fern#3@0_0', 'SM_Fern#3@1_0']},
        {'id': 'object/brinecove/fern-b', 'group': 'SM_Fern#3@9_9'}]}
    expected = {'SM_Fern#3@0_0': 4, 'SM_Fern#3@1_0': 2, 'SM_Fern#3@9_9': 5}
    rows = {'SM_Fern': [['V2ScenePatch', 'brinecove:fern-a', 6, [0, 0, 0]],
                        ['V2ScenePatch', 'brinecove:fern-b', 5, [1, 1, 0]]]}
    assert saved_objects.check(listed, rows, expected) == {}
    rows['SM_Fern'].append(['V2ScenePatch', 'megapark:trees/cell-x0-z0', 40, [9, 9, 0]])   # another region's own plants
    assert saved_objects.check(listed, rows, expected) == {}
    rows['SM_Fern'].append(['BrineCoveRegion', 'BrineCoveRegion_0', 0, [0, 0, 0]])   # emptied: draws nothing
    assert saved_objects.check(listed, rows, expected) == {}
    rows['SM_Fern'][-1][2] = 11
    assert saved_objects.check(listed, rows, expected)['object/brinecove/fern-b'] == \
        ['SM_Fern: also drawn by BrineCoveRegion BrineCoveRegion_0']
