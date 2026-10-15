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
        views = [dict(player=i, rider=rider, pawn=f'/Game/{rider}/BP_{rider}.BP_{rider}_C', ready=True, local=local,
                      health=73, hits=2, attachment=True, activity=2 if phase in (1, 2, 3) else 0,
                      epoch=phase+1) for i, local in (('host', True), ('guest', False))]
        exit_input = dict(bike_exit_sent=True, bike_exit_grounded=True, bike_exit_speed=0,
                          mount_recovery_retries=0, mount_recovery_epochs=[])
        stages.append(dict(phase=phase, host=dict(views=views, **exit_input),
                           guest=dict(views=[r | dict(local=not r['local']) for r in views], **exit_input)))
    (tmp_path / 'features-result.json').write_text(json.dumps(dict(case='switch-bike', passed=True, default_vehicles=True, stages=stages)))
    return tmp_path


def test_two_observers_see_same_players_health_and_replacement(receipt):
    assert all(review.feature_checks(receipt, 'switch-bike').values())


@pytest.mark.parametrize('phase', [3, 4])
def test_return_to_cairo_requires_original_pawn_class(receipt, phase):
    path = receipt / 'features-result.json'
    value = json.loads(path.read_text())
    value['stages'][phase]['guest']['views'][1]['pawn'] = '/Game/Modori/BP_Modori.BP_Modori_C'
    path.write_text(json.dumps(value))
    assert not all(review.feature_checks(receipt, 'switch-bike').values())


@pytest.mark.parametrize('phase', [1, 3, 4])
def test_mount_return_and_dismount_require_fresh_activity_epoch(receipt, phase):
    path = receipt / 'features-result.json'
    value = json.loads(path.read_text())
    value['stages'][phase]['guest']['views'][1]['epoch'] = value['stages'][phase-1]['guest']['views'][1]['epoch']
    path.write_text(json.dumps(value))
    assert not all(review.feature_checks(receipt, 'switch-bike').values())


@pytest.mark.parametrize('pawn', [None, ''])
def test_replacement_requires_observed_pawn_class(receipt, pawn):
    path = receipt / 'features-result.json'
    value = json.loads(path.read_text())
    value['stages'][2]['guest']['views'][1]['pawn'] = pawn
    path.write_text(json.dumps(value))
    assert not all(review.feature_checks(receipt, 'switch-bike').values())


@pytest.mark.parametrize('sides', [('host', 'guest'), ('host',), ('guest',)])
def test_replacement_class_matches_expected_rider_on_both_observers(receipt, sides):
    path = receipt / 'features-result.json'
    value = json.loads(path.read_text())
    for side in sides:
        rows = value['stages'][2][side]['views']
        for row in rows if len(sides) == 2 else rows[:1]:
            row['pawn'] = '/Game/Nox/BP_Nox.BP_Nox_C'
    path.write_text(json.dumps(value))
    assert not all(review.feature_checks(receipt, 'switch-bike').values())


def test_agreed_wrong_cairo_class_cannot_define_the_expected_return(receipt):
    path = receipt / 'features-result.json'
    value = json.loads(path.read_text())
    for stage in value['stages']:
        for side in ('host', 'guest'):
            for row in stage[side]['views']:
                if row['rider'] == 'Cairo':
                    row['pawn'] = '/Game/Nox/BP_Nox.BP_Nox_C'
    path.write_text(json.dumps(value))
    assert not all(review.feature_checks(receipt, 'switch-bike').values())


@pytest.fixture
def zeppelin_receipt(receipt):
    path = receipt / 'features-result.json'
    value = json.loads(path.read_text())
    value.update(case='zeppelin', stages=value['stages'][:4])
    for stage in value['stages']:
        mounted = stage['phase'] in (1, 2)
        for side in ('host', 'guest'):
            stage[side].update(ship_stage=3 if mounted else 0, dock=0, destination=1, ship_z=1000)
            for index, row in enumerate(stage[side]['views']):
                rider = 'Modori' if stage['phase'] >= 2 else 'Cairo'
                row.update(rider=rider, pawn=f'/Game/{rider}/BP_{rider}.BP_{rider}_C', activity=4 if mounted else 0,
                           x=0, y=-55 if index == 0 else 55, z=1090)
    path.write_text(json.dumps(value))
    return receipt


def test_both_observers_see_shared_flying_zeppelin_and_separate_seats(zeppelin_receipt):
    assert all(review.feature_checks(zeppelin_receipt, 'zeppelin').values())


@pytest.mark.parametrize('field', ['dock', 'destination', 'ship_z', 'ship_stage'])
def test_zeppelin_requires_ship_state_from_both_observers(zeppelin_receipt, field):
    path = zeppelin_receipt / 'features-result.json'
    value = json.loads(path.read_text())
    for side in ('host', 'guest'):
        value['stages'][1][side].pop(field)
    path.write_text(json.dumps(value))
    assert not all(review.feature_checks(zeppelin_receipt, 'zeppelin').values())


@pytest.mark.parametrize('side', ['host', 'guest'])
def test_zeppelin_rejects_overlapping_seats_on_either_observer(zeppelin_receipt, side):
    path = zeppelin_receipt / 'features-result.json'
    value = json.loads(path.read_text())
    rows = value['stages'][2][side]['views']
    rows[1].update({key: rows[0][key] for key in ('x', 'y', 'z')})
    path.write_text(json.dumps(value))
    assert not all(review.feature_checks(zeppelin_receipt, 'zeppelin').values())


@pytest.mark.parametrize('edit', [dict(ship_stage=0), dict(dock=-1), dict(destination=True),
                                  dict(ship_z=float('inf'))])
def test_zeppelin_rejects_invalid_or_nonflying_ship_state(zeppelin_receipt, edit):
    path = zeppelin_receipt / 'features-result.json'
    value = json.loads(path.read_text())
    value['stages'][1]['guest'].update(edit)
    path.write_text(json.dumps(value))
    assert not all(review.feature_checks(zeppelin_receipt, 'zeppelin').values())


@pytest.mark.parametrize('edit', [dict(x=None), dict(y=True), dict(z=float('nan'))])
def test_zeppelin_requires_finite_seat_positions(zeppelin_receipt, edit):
    path = zeppelin_receipt / 'features-result.json'
    value = json.loads(path.read_text())
    value['stages'][1]['guest']['views'][0].update(edit)
    path.write_text(json.dumps(value))
    assert not all(review.feature_checks(zeppelin_receipt, 'zeppelin').values())


@pytest.mark.parametrize('counts,accepted', [([0, 1, 1, 1, 1], True), ([0, 1, 0, 0, 0], False),
                                            ([0, None, 0, 0, 0], False), ([0, -1, 0, 0, 0], False)])
def test_mount_recovery_count_survives_pawn_replacement(receipt, counts, accepted):
    path = receipt / 'features-result.json'
    value = json.loads(path.read_text())
    for stage, count in zip(value['stages'], counts):
        stage['guest']['mount_recovery_retries'] = count
        stage['guest']['mount_recovery_epochs'] = [dict(old_epoch=1, new_epoch=2)] if count == 1 else []
    path.write_text(json.dumps(value))
    assert all(review.feature_checks(receipt, 'switch-bike').values()) is accepted


@pytest.mark.parametrize('epochs', [None, [dict(old_epoch=1, new_epoch=1)], [dict(old_epoch=7, new_epoch=8)]])
def test_mount_recovery_cannot_erase_or_rewrite_epoch_evidence(receipt, epochs):
    path = receipt / 'features-result.json'
    value = json.loads(path.read_text())
    for stage in value['stages'][1:]:
        stage['guest'].update(mount_recovery_retries=1, mount_recovery_epochs=[dict(old_epoch=1, new_epoch=2)])
    value['stages'][3]['guest']['mount_recovery_epochs'] = epochs
    path.write_text(json.dumps(value))
    assert not all(review.feature_checks(receipt, 'switch-bike').values())


@pytest.mark.parametrize('edit', [dict(bike_exit_speed=41), dict(bike_exit_speed=None),
                                  dict(bike_exit_sent=False), dict(bike_exit_grounded=False)])
def test_bike_swap_receipt_requires_a_supported_dismount_request(receipt, edit):
    path = receipt / 'features-result.json'
    value = json.loads(path.read_text())
    value['stages'][4]['guest'].update(edit)
    path.write_text(json.dumps(value))
    assert not all(review.feature_checks(receipt, 'switch-bike').values())


@pytest.mark.parametrize('edit,accepted', [(dict(), True), (dict(sail_exit_requests=0), False),
                                         (dict(sail_shore_distance=2000), False),
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
                row.update(rider='Cairo', pawn='/Game/Cairo/BP_Cairo.BP_Cairo_C',
                           armed=stage['phase'] in (1, 2, 3), guard=True, guard_weight=1,
                           checkpoints=4, local_role=role, predicts_moves=role in (2, 3))
                if role == 1: row['predicts_moves'] = proxy_predicts
    path.write_text(json.dumps(value))
    assert all(review.feature_checks(receipt, 'equipment').values()) is (not proxy_predicts)


@pytest.mark.parametrize('edit', [
    lambda r: r.update(default_vehicles=False),
    lambda r: r['stages'].pop(2),
    lambda r: r['stages'][2]['guest']['views'][1].update(health=100),
    lambda r: r['stages'][2]['guest']['views'][1].update(player='fresh-id'),
    lambda r: r['stages'][2]['guest']['views'][1].update(pawn='/Game/Cairo/BP_Cairo.BP_Cairo_C'),
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
                           observed_pose_frames=100, matching_pose_frames=100,
                           matching_mesh_frames=100, mesh_world_error=0, body_visible=True)
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
                           observed_pose_frames=100, matching_pose_frames=100,
                           matching_mesh_frames=100, mesh_world_error=0, body_visible=True)
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


@pytest.mark.parametrize('fields', [dict(matching_mesh_frames=0), dict(mesh_world_error=50000),
                                    dict(mesh_world_error=None), dict(body_visible=False)])
def test_matching_local_bones_do_not_establish_body_world_placement(receipt, fields):
    path = receipt / 'features-result.json'
    value = json.loads(path.read_text())
    value['case'] = 'switch-skate'
    for stage in value['stages']:
        for side in ('host', 'guest'):
            for row in stage[side]['views']:
                row.update(activity=1 if stage['phase'] in (1, 2, 3) else 0,
                           simulation_tick=200, continued_at_tick=100, body_lift=88,
                           standing_half=88, ride_root_z=10, z=98,
                           observed_pose_frames=100, matching_pose_frames=100,
                           matching_mesh_frames=100, mesh_world_error=0, body_visible=True)
    value['stages'][1]['guest']['views'][0].update(fields)
    path.write_text(json.dumps(value))
    assert not all(review.feature_checks(receipt, 'switch-skate').values())


HOST_LOOK = dict(horse_breed='friesian', horse_tack='03', horse_coat='kestrel-palomino', horse_mask='Tobiano',
                 horse_hair_color='flaxen-gold', horse_hair_pattern='ombre', horse_tint='warm-sun')
GUEST_LOOK = dict(horse_breed='clydesdale', horse_tack='05', horse_coat='kestrel-blue-roan', horse_mask='Spots',
                  horse_hair_color='silver-white', horse_hair_pattern='streaked', horse_tint='cool-slate')


@pytest.fixture
def horse_receipt(receipt):
    path = receipt / 'features-result.json'
    value = json.loads(path.read_text())
    value['case'] = 'switch-horse'
    for stage in value['stages']:
        mounted = stage['phase'] in (1, 2, 3)
        for side, look in (('host', HOST_LOOK), ('guest', GUEST_LOOK)):
            stage[side].update(horse_exit_sent=True, horse_exit_grounded=True, horse_exit_speed=0,
                               local_player=side, horse_request=dict(look))
            for row in stage[side]['views']:
                row.update(activity=5 if mounted else 0, horse_visible=mounted, horse_role=8 if mounted else 0,
                           horse_speed=472.5 if mounted else 0, **(HOST_LOOK if row['player'] == 'host' else GUEST_LOOK))
    path.write_text(json.dumps(value))
    return receipt


def test_both_observers_see_each_players_horse_through_the_swap(horse_receipt):
    checks = review.feature_checks(horse_receipt, 'switch-horse')
    assert all(checks.values())
    assert all(checks[f'feature_{phase}_horse_appearance_agrees'] for phase in range(5))


@pytest.mark.parametrize('phase,side,row', [(0, 'host', 1), (2, 'guest', 0), (3, 'guest', 1)])
def test_horse_swap_rejects_an_observer_showing_another_look(horse_receipt, phase, side, row):
    path = horse_receipt / 'features-result.json'
    value = json.loads(path.read_text())
    value['stages'][phase][side]['views'][row]['horse_coat'] = 'native'
    path.write_text(json.dumps(value))
    assert not all(review.feature_checks(horse_receipt, 'switch-horse').values())


@pytest.mark.parametrize('edit', [dict(horse_request=None), dict(local_player=None), dict(local_player='host'),
                                  dict(horse_request=dict(GUEST_LOOK, horse_tint=''))])
def test_horse_swap_requires_each_players_own_request(horse_receipt, edit):
    path = horse_receipt / 'features-result.json'
    value = json.loads(path.read_text())
    value['stages'][1]['guest'].update(edit)
    path.write_text(json.dumps(value))
    assert not all(review.feature_checks(horse_receipt, 'switch-horse').values())


@pytest.mark.parametrize('edit', [dict(horse_exit_speed=41), dict(horse_exit_speed=None),
                                  dict(horse_exit_sent=False), dict(horse_exit_grounded=False)])
def test_horse_swap_rejects_a_moving_or_missing_dismount(horse_receipt, edit):
    path = horse_receipt / 'features-result.json'
    value = json.loads(path.read_text())
    value['stages'][4]['guest'].update(edit)
    path.write_text(json.dumps(value))
    assert not all(review.feature_checks(horse_receipt, 'switch-horse').values())


@pytest.mark.parametrize('edit', [lambda r: r.update(horse_visible=False), lambda r: r.update(activity=0),
                                  lambda r: r.pop('horse_visible'), lambda r: r.update(horse_role=None),
                                  lambda r: r.update(horse_speed=float('nan'))])
def test_horse_swap_requires_the_horse_in_the_replacement_phase(horse_receipt, edit):
    path = horse_receipt / 'features-result.json'
    value = json.loads(path.read_text())
    edit(value['stages'][2]['host']['views'][1])
    path.write_text(json.dumps(value))
    assert not all(review.feature_checks(horse_receipt, 'switch-horse').values())


@pytest.mark.parametrize('phase', [0, 4])
def test_horse_must_be_gone_on_foot(horse_receipt, phase):
    path = horse_receipt / 'features-result.json'
    value = json.loads(path.read_text())
    value['stages'][phase]['guest']['views'][0]['horse_visible'] = True
    path.write_text(json.dumps(value))
    assert not all(review.feature_checks(horse_receipt, 'switch-horse').values())


def test_bike_activity_does_not_satisfy_the_horse_case(horse_receipt):
    path = horse_receipt / 'features-result.json'
    value = json.loads(path.read_text())
    for stage in value['stages'][1:4]:
        for side in ('host', 'guest'):
            for row in stage[side]['views']:
                row['activity'] = 2
    path.write_text(json.dumps(value))
    assert not all(review.feature_checks(horse_receipt, 'switch-horse').values())
