"""tools/test/saved_objects.py's pure check: a saved object must draw every instance its runtime group places."""
import sys
from pathlib import Path

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME / 'tools/test'))
import saved_objects  # noqa: E402

LISTED = {'tag': 'brinecove', 'objects': [{'id': 'object/brinecove/wreck', 'group': 'SM_BC_Ships_2_2'}]}
DATA = {'bounds_m': [-10, -10, 10, 10], 'origin_cm': [0.0, 0.0, 0.0], 'groups': [
    {'asset': '/Game/BrineCove/SM_BC_Ships_2_2.SM_BC_Ships_2_2',
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
