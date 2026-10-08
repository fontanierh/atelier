import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('clock_review', Path(__file__).resolve().parents[1] / 'tools/network_clock_review.py')
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def fixtures(timeout=False):
    server = dict(timeout_corrections=int(timeout), time_budget_corrections=0, time_budget_rejected=0,
                  deferred_forced_updates=4, stale_epoch_moves=0, stale_probe_rejected=1,
                  stale_probe_root_cm=0., stale_probe_clock_delta=0., neutral_max_acceleration=0.,
                  neutral_late_ground_frames=2, neutral_late_max_speed=0.,
                  clock_arrivals=1, neutral_path_cm=0., clock_arrival_drift_cm=0.)
    guest = dict(timeout_corrections=int(timeout), time_budget_corrections=0,
                 movement_hitch_seconds=1.051 if timeout else .230, skate_hitch_seconds=.230,
                 movement_hitch_at_seconds=1.2,
                 movement_hitch_speed_cm_s=142.7, timeout_drive_seconds=.2,
                 guard_before_timeout=True, cleared_timeout_holds=True, stale_probe_sent=1)
    return server, guest


@pytest.mark.parametrize('timeout', [False, True])
def test_hitch_and_timeout_require_observed_stimulus_and_exact_recovery(timeout):
    server, guest = fixtures(timeout)
    assert all(review.clock_checks(server, guest, 1050 if timeout else 229, 229).values())


def test_short_hitch_and_deferred_branch_are_separate_coverage():
    server, guest = fixtures()
    server['deferred_forced_updates'] = 0
    assert all(review.clock_checks(server, guest, 229, 229).values())
    guest['movement_hitch_seconds'] = .501
    assert not all(review.clock_checks(server, guest, 500, 0).values())
    server['deferred_forced_updates'] = 4
    assert all(review.clock_checks(server, guest, 500, 0).values())
    # A receipt from the shorter run cannot stand in for branch coverage.
    guest['movement_hitch_seconds'] = .230
    assert not all(review.clock_checks(server, guest, 500, 0).values())


@pytest.mark.parametrize('field,value', [('movement_hitch_seconds', 0), ('movement_hitch_seconds', float('nan')),
    ('movement_hitch_seconds', True), ('skate_hitch_seconds', .1), ('timeout_corrections', 2),
    ('timeout_corrections', True), ('time_budget_corrections', 1), ('guard_before_timeout', False),
    ('cleared_timeout_holds', False), ('movement_hitch_at_seconds', None),
    ('movement_hitch_at_seconds', True), ('movement_hitch_at_seconds', float('nan')),
    ('movement_hitch_at_seconds', .65), ('movement_hitch_at_seconds', 5.),
    ('movement_hitch_speed_cm_s', 0), ('movement_hitch_speed_cm_s', 40),
    ('movement_hitch_speed_cm_s', float('nan')), ('movement_hitch_speed_cm_s', True),
    ('timeout_drive_seconds', .1), ('timeout_drive_seconds', 5.),
    ('timeout_drive_seconds', None), ('timeout_drive_seconds', float('nan'))])
def test_vacuous_or_repeated_timeout_is_not_accepted(field, value):
    server, guest = fixtures(True); guest[field] = value
    assert not all(review.clock_checks(server, guest, 1050, 229).values())


@pytest.mark.parametrize('field,value', [('timeout_corrections', 0), ('time_budget_rejected', 1),
    ('time_budget_corrections', 1), ('stale_probe_rejected', 0), ('stale_probe_rejected', 2),
    ('stale_probe_root_cm', .1), ('stale_probe_clock_delta', .01), ('neutral_late_max_speed', 99.),
    ('neutral_late_ground_frames', 0), ('neutral_max_acceleration', 10.), ('deferred_forced_updates', 0),
    ('clock_arrivals', 0), ('clock_arrivals', 2), ('clock_arrivals', True),
    ('neutral_path_cm', .02), ('neutral_path_cm', float('nan')), ('neutral_path_cm', True),
    ('clock_arrival_drift_cm', .02), ('clock_arrival_drift_cm', float('nan')), ('clock_arrival_drift_cm', None)])
def test_host_must_observe_the_timeout_and_refuse_the_old_epoch(field, value):
    server, guest = fixtures(True); server[field] = value
    assert not all(review.clock_checks(server, guest, 1050, 229).values())
