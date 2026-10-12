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
        exit_input = dict(bike_exit_sent=True, bike_exit_grounded=True, bike_exit_speed=0)
        stages.append(dict(phase=phase, host=dict(views=views, **exit_input),
                           guest=dict(views=[r | dict(local=not r['local']) for r in views], **exit_input)))
    (tmp_path / 'features-result.json').write_text(json.dumps(dict(case='switch-bike', passed=True, default_vehicles=True, stages=stages)))
    return tmp_path


def test_two_observers_see_same_players_health_and_replacement(receipt):
    assert all(review.feature_checks(receipt, 'switch-bike').values())


@pytest.mark.parametrize('edit', [dict(bike_exit_speed=41), dict(bike_exit_speed=None),
                                  dict(bike_exit_sent=False), dict(bike_exit_grounded=False)])
def test_bike_swap_receipt_requires_a_supported_dismount_request(receipt, edit):
    path = receipt / 'features-result.json'
    value = json.loads(path.read_text())
    value['stages'][4]['guest'].update(edit)
    path.write_text(json.dumps(value))
    assert not all(review.feature_checks(receipt, 'switch-bike').values())


@pytest.mark.parametrize('edit,accepted', [(dict(), True), (dict(sail_exit_requests=0), False),
                                         (dict(sail_shore_distance=900), False),
                                         (dict(sail_shore_distance=None), False),
                                         (dict(sail_landing_grounded=False), False)])
def test_sail_swap_requires_an_observed_return_to_shore(receipt, edit, accepted):
    path = receipt / 'features-result.json'
    value = json.loads(path.read_text()); value['case'] = 'switch-sail'
    for stage in value['stages']:
        for side in ('host', 'guest'):
            stage[side].update(sail_exit_requests=1, sail_shore_distance=300, sail_landing_grounded=True)
            for row in stage[side]['views']: row['activity'] = 3 if stage['phase'] in (1, 2, 3) else 0
    value['stages'][4]['guest'].update(edit)
    path.write_text(json.dumps(value))
    assert all(review.feature_checks(receipt, 'switch-sail').values()) is accepted


@pytest.mark.parametrize('proxy_predicts', [False, True])
def test_remote_equipment_does_not_run_gameplay_prediction(receipt, proxy_predicts):
    path = receipt / 'features-result.json'
    value = json.loads(path.read_text()); value['case'] = 'equipment'
    for stage in value['stages']:
        for side in ('host', 'guest'):
            for row in stage[side]['views']:
                role = 3 if side == 'host' else 2 if row['local'] else 1
                row.update(armed=stage['phase'] in (1, 2, 3), guard=True, guard_weight=1,
                           checkpoints=4, local_role=role, predicts_moves=role in (2, 3))
                if role == 1: row['predicts_moves'] = proxy_predicts
    path.write_text(json.dumps(value))
    assert all(review.feature_checks(receipt, 'equipment').values()) is (not proxy_predicts)


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
                           standing_half=88, ride_root_z=10, z=98,
                           observed_pose_frames=100, matching_pose_frames=100)
    value['stages'][2]['guest']['views'][1].update(body_lift=height)
    path.write_text(json.dumps(value))
    assert all(review.feature_checks(receipt, 'switch-skate').values()) is (height == 88)


@pytest.mark.parametrize('observed,matching,accepted', [(100, 100, True), (100, 0, False), (None, None, False)])
def test_skate_swap_requires_evaluated_remote_pose(receipt, observed, matching, accepted):
    path = receipt / 'features-result.json'
    value = json.loads(path.read_text())
    value['case'] = 'switch-skate'
    for stage in value['stages']:
        for side in ('host', 'guest'):
            for row in stage[side]['views']:
                row.update(activity=1 if stage['phase'] in (1, 2, 3) else 0,
                           simulation_tick=200, continued_at_tick=100, body_lift=88,
                           standing_half=88, ride_root_z=10, z=98,
                           observed_pose_frames=100, matching_pose_frames=100)
    value['stages'][2]['guest']['views'][0].update(observed_pose_frames=observed, matching_pose_frames=matching)
    path.write_text(json.dumps(value))
    assert all(review.feature_checks(receipt, 'switch-skate').values()) is accepted


def test_rendered_feature_requires_complete_decodable_captures(tmp_path):
    from PIL import Image
    assert not any(review.feature_render_checks(tmp_path, 'equipment').values())
    for phase in range(5):
        Image.new('RGB', (960, 540)).save(tmp_path / f'feature-{phase}.png')
    assert all(review.feature_render_checks(tmp_path, 'equipment').values())
    (tmp_path / 'feature-2.png').write_bytes(b'not a complete PNG')
    assert not review.feature_render_checks(tmp_path, 'equipment')['feature_2_rendered_capture']


def test_valid_png_checksums_do_not_establish_decodable_pixels(tmp_path):
    import struct
    import zlib
    from PIL import Image
    def chunk(kind, payload):
        return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload))
    damaged = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 960, 540, 8, 2, 0, 0, 0)) +
               chunk(b'IDAT', b'invalid compressed pixels') + chunk(b'IEND', b''))
    path = tmp_path / 'feature-2.png'
    path.write_bytes(damaged)
    with Image.open(path) as capture:
        capture.verify()  # Structurally valid, including chunk checksums.
    assert not review.feature_render_checks(tmp_path, 'equipment')['feature_2_rendered_capture']
