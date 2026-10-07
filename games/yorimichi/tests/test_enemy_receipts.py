import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('enemy_review', Path(__file__).resolve().parents[1] / 'tools/network_enemy_review.py')
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


@pytest.fixture
def enemy(tmp_path):
    setup = dict(pause_unchanged=True, resume_count=1, paused_ai_ticks=0, initial_maximum=6, frozen_maximum=9,
                 paused_movement_mode=1, movement_mode_at_notice=1, host_notice_distance=600, guest_notice_distance=500,
                 settle_displacement_cm=2, host_id='host', guest_id='guest')
    phases = []
    for phase, before, after in [(1, 9, 8), (2, 8, 7), (3, 7, 7), (4, 7, 0)]:
        row = dict(phase=phase, net_guid=5, health=after, phase_start_health=before, maximum_health=9, action_serial=phase,
                   ai_ticks=phase*100, sweep_calls=6 if phase >= 3 else 0, frame_count=30, frame_min=.033, frame_max=.04,
                   owner_id='host', owner_attempts=1 if phase >= 2 else 0, owner_blade_candidates=1 if phase >= 2 else 0,
                   guest_health=80 if phase >= 3 else 100, guest_health_changes=1 if phase >= 3 else 0,
                   queued=1 if phase == 3 else 0, resolved=1 if phase == 3 else 0,
                   overflows=0, cancelled=0, missing_samples=0, authored_fallbacks=0, rejected_defence_times=0)
        row['guest_observation'] = row | dict(ai_ticks=0, sweep_calls=0, simulated_proxy=True, has_controller=False,
                                            owner_id='guest', owner_attempts=1, owner_blade_candidates=1)
        phases.append(row)
    hits = [dict(phase=phase, player_id=player, power=1, before=before, after=before-1,
                 player_action=10-before, enemy_guid=5, other_distance=600, other_speed=0)
            for phase, player, before in [(1,'guest',9),(2,'host',8)] + [(4,'guest',n) for n in range(7,0,-1)]]
    for hit in hits:
        hit['player_epoch'] = 1
        hit['input'] = dict(player=hit['player_id'], epoch=1, edge=hit['player_action'], phase=hit['phase'], action=hit['player_action'])
    bindings = [hit['input'] for hit in hits]
    for row in phases:
        row['bound_attack_actions'] = bindings
        for owner in (row, row['guest_observation']):
            owner['owner_attack_edges'] = [{k:v for k,v in b.items() if k != 'action'} for b in bindings if b['player'] == owner['owner_id']]
    claws = [dict(callbacks=1, outcome=0, victim='guest', damage=20, health_before=100, health_after=80)]
    result = dict(passed=True, net_guid=5, health=0, deaths=1, state=9, state_name='Dead', claw_damage=20, setup=setup, phases=phases, hits=hits, claws=claws)
    for name, data in [('enemy-result',result),('enemy-final',dict(passed=True,claws=claws)),
                       ('enemy-observed',dict(net_guid=5,health=0,death_changes=1,deaths=0,state=9,state_name='Dead',simulated_proxy=True,has_controller=False,ai_ticks=0,sweep_calls=0))]:
        (tmp_path/(name+'.json')).write_text(json.dumps(data))
    return tmp_path


def test_enemy_requires_real_attribution_replication_and_lifecycle(enemy):
    assert all(review.compare_enemy(enemy).values())


@pytest.mark.parametrize('edit', [
    lambda r: r['hits'][0].update(player_id='host'),
    lambda r: r['hits'][0].pop('input'),
    lambda r: r['hits'][0].update(player_epoch=2),
    lambda r: r['phases'][0]['guest_observation'].update(owner_attack_edges=[]),
    lambda r: r['hits'][0].update(after=7),
    lambda r: r['hits'][0].update(other_distance=50),
    lambda r: r['phases'][0]['guest_observation'].update(health=9),
    lambda r: r['phases'][0]['guest_observation'].update(owner_blade_candidates=0),
    lambda r: r['phases'][1].update(owner_attempts=0),
    lambda r: r['phases'][2]['guest_observation'].update(ai_ticks=1),
    lambda r: r['phases'][2]['guest_observation'].update(sweep_calls=1),
    lambda r: r['phases'][2].update(guest_health_changes=2),
    lambda r: r['phases'][2].update(overflows=1),
    lambda r: r['phases'][2].update(queued=0),
    lambda r: r['phases'][2].update(rejected_defence_times=1),
    lambda r: r['setup'].update(initial_maximum=9),
    lambda r: r['setup'].update(resume_count=2),
    lambda r: r.update(phases=[]),
    lambda r: r.update(claws=[]),
])
def test_enemy_rejects_false_passes(enemy, edit):
    path=enemy/'enemy-result.json'
    data=json.loads(path.read_text());edit(data);path.write_text(json.dumps(data))
    assert not all(review.compare_enemy(enemy).values())


def test_late_duplicate_after_guest_departure_fails(enemy):
    path=enemy/'enemy-final.json'
    data=json.loads(path.read_text());data['claws'][0]['callbacks']=2;path.write_text(json.dumps(data))
    assert not all(review.compare_enemy(enemy).values())
