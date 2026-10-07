"""Compare native shared-hunter observations, never stimulus files."""
import json


def compare_enemy(folder):
    def read(name):
        data = json.loads((folder / (name + '.json')).read_text())
        if data.get('error'):
            raise RuntimeError(f'{name}: {data["error"]}')
        return data

    result, final, guest = [read(name) for name in ('enemy-result', 'enemy-final', 'enemy-observed')]
    setup, hits, claws, phases = [result.get(k, {} if k == 'setup' else []) for k in ('setup', 'hits', 'claws', 'phases')]
    claw = claws[0] if len(claws) == 1 else {}
    checks = {'enemy_native_complete': result.get('passed') is True and final.get('passed') is True,
              'enemy_setup': setup.get('pause_unchanged') is True and setup.get('resume_count') == 1 and
                  setup.get('paused_ai_ticks') == 0 and setup.get('initial_maximum') == 6 and
                  setup.get('frozen_maximum') == 9 and setup.get('paused_movement_mode') == setup.get('movement_mode_at_notice') == 1 and
                  0 <= setup.get('host_notice_distance', -1) < 900 and 0 <= setup.get('guest_notice_distance', -1) < 900 and
                  setup.get('settle_displacement_cm', -1) >= 0,
              'enemy_phase_count': [r.get('phase') for r in phases] == [1, 2, 3, 4],
              'enemy_final_identity': bool(result.get('net_guid')) and result.get('net_guid') == guest.get('net_guid'),
              'enemy_shared_death': result.get('health') == guest.get('health') == 0 and result.get('deaths') == 1 and
                  guest.get('death_changes') == 1 and guest.get('deaths') == 0 and
                  result.get('state_name') == guest.get('state_name') == 'Dead',
              'enemy_final_guest_proxy': guest.get('simulated_proxy') is True and guest.get('has_controller') is False and
                  guest.get('ai_ticks') == guest.get('sweep_calls') == 0,
              'enemy_claw_exactly_once_final': len(claws) == 1 and final.get('claws') == claws and
                  claw.get('callbacks') == 1 and claw.get('outcome') == 0 and
                  claw.get('victim') == setup.get('guest_id') and claw.get('damage', 0) > 0 and claw.get('damage') == result.get('claw_damage') and
                  abs(claw.get('health_before', -1000) - claw.get('health_after', 1000) - claw.get('damage', 0)) < .01,
              'enemy_real_sword_hits': len(hits) >= 3 and all(h.get('power', 0) > 0 and h.get('player_action', 0) > 0 and
                  h.get('enemy_guid') == result.get('net_guid') and
                  h.get('before', -1) - h.get('after', -1) == min(h.get('power', 0), h.get('before', 0)) for h in hits)}
    for row in phases:
        phase, peer = row.get('phase'), row.get('guest_observation', {})
        checks[f'enemy_phase_{phase}_replicated'] = (row.get('net_guid') == peer.get('net_guid') == result.get('net_guid') and
            row.get('health') == peer.get('health') and row.get('maximum_health') == peer.get('maximum_health') == 9 and
            row.get('action_serial') == peer.get('action_serial') and peer.get('simulated_proxy') is True and
            peer.get('has_controller') is False and peer.get('ai_ticks') == peer.get('sweep_calls') == 0)
        checks[f'enemy_phase_{phase}_frames'] = all(r.get('frame_count', 0) > 0 and
            0 < r.get('frame_min', 0) <= r.get('frame_max', 0) <= .2 for r in (row, peer))
        if phase in (1, 2):
            identity = setup.get('guest_id' if phase == 1 else 'host_id')
            credited = [hit for hit in hits if hit.get('phase') == phase]
            owner = peer if phase == 1 else row
            checks[f'enemy_phase_{phase}_attribution'] = (bool(identity) and bool(credited) and
                all(h.get('player_id') == identity and h.get('other_distance', -1) > 350 and
                    0 <= h.get('other_speed', -1) < 5 for h in credited) and
                row.get('phase_start_health', -1) - row.get('health', -1) == sum(h['before'] - h['after'] for h in credited))
            origins = owner.get('owner_attack_edges', [])
            bindings = row.get('bound_attack_actions', [])
            checks[f'enemy_phase_{phase}_input_causality'] = bool(credited) and all(
                (binding := h.get('input')) and binding in bindings and binding.get('player') == identity and
                binding.get('action') == h.get('player_action') and binding.get('epoch') == h.get('player_epoch') and
                dict(player=identity, epoch=binding.get('epoch'), edge=binding.get('edge'), phase=phase) in origins
                for h in credited)
            checks[f'enemy_phase_{phase}_one_cut_per_edge'] = len(bindings) == len({
                (b.get('player'), b.get('epoch'), b.get('edge')) for b in bindings})
            checks[f'enemy_phase_{phase}_owner_swing'] = (owner.get('owner_id') == identity and
                owner.get('owner_attempts', 0) > 0 and owner.get('owner_blade_candidates', 0) > 0)
        if phase == 3:
            checks['enemy_claw_real_host_sweep'] = row.get('ai_ticks', 0) > 0 and row.get('sweep_calls', 0) > 0
            checks['enemy_claw_replicated_health'] = (row.get('guest_health') == peer.get('guest_health') == claw.get('health_after') and
                row.get('guest_health_changes') == peer.get('guest_health_changes') == 1)
            checks['enemy_claw_resolver'] = (row.get('queued') == row.get('resolved') == 1 and
                all(row.get(k) == 0 for k in ('overflows', 'cancelled', 'missing_samples', 'authored_fallbacks', 'rejected_defence_times')))
    return checks
