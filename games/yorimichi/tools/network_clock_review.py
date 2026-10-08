"""Non-vacuous receipt gates for injected movement outages; no tolerance changes."""
import math


def clock_checks(server, guest, movement_ms, skate_ms):
    def measured(key, milliseconds):
        value = guest.get(key)
        return (isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value) and
                milliseconds / 1000 <= value <= milliseconds / 1000 + .1)

    def count(receipt, key, expected):
        value = receipt.get(key)
        return type(value) is int and value == expected

    timeout = int(movement_ms > 750)
    checks = dict(clock_host_timeout_count=count(server, 'timeout_corrections', timeout),
                  clock_guest_timeout_count=count(guest, 'timeout_corrections', timeout),
                  clock_no_spurious_budget_reset=count(server, 'time_budget_corrections', 0) and
                      count(guest, 'time_budget_corrections', 0),
                  clock_no_honest_budget_rejection=count(server, 'time_budget_rejected', 0))
    if movement_ms:
        checks['clock_real_movement_hitch'] = measured('movement_hitch_seconds', movement_ms)
    # The 229ms regression is below UE's ordinary 250ms forced-update interval.
    # A separate 500ms outage proves the deferred branch without timing out.
    if movement_ms > 250:
        checks['clock_host_deferred_forced_update'] = type(server.get('deferred_forced_updates')) is int and server['deferred_forced_updates'] > 0
    if skate_ms:
        checks['clock_real_skate_hitch'] = measured('skate_hitch_seconds', skate_ms)
    if timeout:
        began = guest.get('movement_hitch_at_seconds')
        checks['clock_timeout_setup_bounded'] = type(began) in (float, int) and math.isfinite(began) and .65 < began < 5.
        speed, driving = guest.get('movement_hitch_speed_cm_s'), guest.get('timeout_drive_seconds')
        checks['clock_timeout_was_driving'] = (type(speed) in (float, int) and math.isfinite(speed) and speed > 40 and
            type(driving) in (float, int) and math.isfinite(driving) and .15 <= driving < 5.)
        checks['clock_timeout_cleared_live_holds'] = guest.get('guard_before_timeout') is True and guest.get('cleared_timeout_holds') is True
        checks['clock_timeout_old_epoch_refused'] = (count(guest, 'stale_probe_sent', 1) and count(server, 'stale_probe_rejected', 1) and
            type(server.get('stale_probe_root_cm')) in (float, int) and server['stale_probe_root_cm'] == 0 and
            type(server.get('stale_probe_clock_delta')) in (float, int) and server['stale_probe_clock_delta'] == 0)
        checks['clock_neutral_wait_stops_driving'] = (type(server.get('neutral_max_acceleration')) in (float, int) and
            server['neutral_max_acceleration'] == 0 and type(server.get('neutral_late_ground_frames')) is int and
            server['neutral_late_ground_frames'] > 0 and type(server.get('neutral_late_max_speed')) in (float, int) and
            0 <= server['neutral_late_max_speed'] < 1)
        checks['clock_ground_handoff_stationary'] = (count(server, 'clock_arrivals', 1) and
            all(type(server.get(k)) in (float, int) and math.isfinite(server[k]) and 0 <= server[k] <= .01
                for k in ('neutral_path_cm', 'clock_arrival_drift_cm')))
    return checks
