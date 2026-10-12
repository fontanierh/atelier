"""A successful exit cannot replace evidence from both observers after a swap."""
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('network_feature_review', Path(__file__).resolve().parents[1] / 'tools/network_feature_review.py')
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


@pytest.fixture
def receipt(tmp_path):
    stages = []
    for phase in range(5):
        rider = 'Modori' if phase == 2 else 'Cairo'
        views = [dict(player=i, rider=rider, pawn=rider+'Character', ready=True, local=local,
                      health=73, hits=2, attachment=True, activity=2 if phase in (1, 2, 3) else 0,
                      epoch=phase+1) for i, local in (('host', True), ('guest', False))]
        stages.append(dict(phase=phase, host=dict(views=views), guest=dict(views=[r | dict(local=not r['local']) for r in views])))
    (tmp_path / 'features-result.json').write_text(json.dumps(dict(case='switch-bike', passed=True, default_vehicles=True, stages=stages)))
    return tmp_path


def test_two_observers_see_same_players_health_and_replacement(receipt):
    assert all(review.feature_checks(receipt, 'switch-bike').values())


@pytest.mark.parametrize('edit', [
    lambda r: r.update(default_vehicles=False),
    lambda r: r['stages'].pop(2),
    lambda r: r['stages'][2]['guest']['views'][1].update(health=100),
    lambda r: r['stages'][2]['guest']['views'][1].update(player='fresh-id'),
    lambda r: r['stages'][2]['guest']['views'][1].update(pawn='CairoCharacter'),
    lambda r: r['stages'][2]['guest']['views'][1].update(epoch=2),
    lambda r: r['stages'][2]['guest']['views'][1].update(activity=0),
    lambda r: r['stages'][2]['guest']['views'][1].update(attachment=False),
])
def test_false_success_receipt_is_rejected(receipt, edit):
    path = receipt / 'features-result.json'
    value = json.loads(path.read_text()); edit(value); path.write_text(json.dumps(value))
    assert not all(review.feature_checks(receipt, 'switch-bike').values())


@pytest.mark.parametrize('height', [88, 140, None])
def test_skate_replacement_height_uses_retained_root(receipt, height):
    path = receipt / 'features-result.json'
    value = json.loads(path.read_text())
    value['case'] = 'switch-skate'
    for stage in value['stages']:
        for side in ('host', 'guest'):
            for row in stage[side]['views']:
                row.update(activity=1 if stage['phase'] in (1, 2, 3) else 0,
                           simulation_tick=200, continued_at_tick=100, body_lift=88,
                           standing_half=88, ride_root_z=10, z=98)
    value['stages'][2]['guest']['views'][1].update(body_lift=height)
    path.write_text(json.dumps(value))
    assert all(review.feature_checks(receipt, 'switch-skate').values()) is (height == 88)


def test_rendered_feature_requires_complete_decodable_captures(tmp_path):
    from PIL import Image
    assert not any(review.feature_render_checks(tmp_path, 'equipment').values())
    for phase in range(5):
        Image.new('RGB', (960, 540)).save(tmp_path / f'feature-{phase}.png')
    assert all(review.feature_render_checks(tmp_path, 'equipment').values())
    (tmp_path / 'feature-2.png').write_bytes(b'not a complete PNG')
    assert not review.feature_render_checks(tmp_path, 'equipment')['feature_2_rendered_capture']
