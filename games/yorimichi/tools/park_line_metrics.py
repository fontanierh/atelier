"""Measurements from actual Session frames; inferred geometry is labelled separately."""
import math
import numpy as np
from park_line_gaps import check_required_airs
from park_line_vert import VertReturns

DEFAULTS = dict(huge_air_m=25., min_landing_slope_deg=5., max_landing_mismatch_deg=20.,
                max_takeoff_angle_deg=80., max_ground_slope_deg=85., bump_loss_mps=2.,
                bump_window_s=.25, landing_recovery_s=.5, gravity_mps2=9.81,
                max_landing_normal_speed_mps=7.)


def is_ground(state):
    return state in ('PhysicsGround', 'RevertGround')


def is_bail(state):
    return any(s in state.lower() for s in ('wipeout', 'bail', 'ragdoll', 'biped'))


def pitch(v):
    return math.degrees(math.atan2(v[1], math.hypot(v[0], v[2])))


def slope(normal, velocity):
    n, v = np.asarray(normal), np.asarray(velocity)[[0, 2]]
    d = np.linalg.norm(v)
    return math.degrees(math.atan2(-float(n[[0, 2]]@v)/max(d, 1e-12), n[1]))


def analyze(rows, world):
    """@cc [owner:fontanierh,label:correctness] measured-line-acceptance
    A huge-air pass MUST require a completed flight, an identified intended transition landing,
    recovery observations, no bailout during flight/recovery, and the configured distance and alignment thresholds.
    Unknown support and unfinished flights MUST NOT count as successful landings.
    A landing MUST also pass the normal-speed limit using the largest of its
    last three airborne velocities, so an early contact response cannot hide
    a hard impact. The limit MUST NOT exceed 7 m/s.
    Explicit required_airs MAY complete shorter secondary gaps only through the named-gap safety verdict;
    Route mode MUST still contain a qualifying huge air and pass all existing global safety checks.
    Explicit vert_return diagnostic mode MAY omit the hero air, but MUST require a declared wall air-out.
    """
    rules = {**DEFAULTS, **world.spec.get('acceptance', {})}
    normal_limit = rules['max_landing_normal_speed_mps']
    if not math.isfinite(normal_limit) or not 0 < normal_limit <= 7.:
        raise ValueError('landing normal-speed limit must be positive and at most 7 m/s')
    vert = VertReturns(world)
    if not rows:
        return dict(passed=False, failures=['no observations'], airs=[])
    p = np.array([r['position'] for r in rows]); v = np.array([r['velocity'] for r in rows])
    speed = np.linalg.norm(v, axis=1); states = [r['state'] for r in rows]
    times = np.array([r['time_s'] for r in rows])
    progress, lateral = world.path.project(p)
    ground = np.array([is_ground(s) for s in states])
    airborne = np.array(['Air' in s and not is_bail(s) for s in states])
    bail = [i for i, s in enumerate(states) if is_bail(s)]
    supports = [world.support(q) if g else None for q, g in zip(p, ground)]
    nearby = vert.nearest_ground(p, ground)
    for i, support in enumerate(nearby):
        if vert.on_wall(support):
            supports[i] = support
    changes = np.flatnonzero(np.r_[True, airborne[1:] != airborne[:-1]])
    airs = []
    for begin, end in zip(changes, np.r_[changes[1:], len(rows)]):
        if not airborne[begin]:
            continue
        before = max(0, begin-1); landed = end < len(rows) and ground[end]
        last = end if end < len(rows) else len(rows)-1
        incoming = v[max(begin, end-1)]
        support = supports[end] if landed else None
        departure_frame = next((i for i in range(before, -1, -1)
                                if times[begin]-times[i] <= .15 and supports[i] is not None), None)
        departure = supports[departure_frame] if departure_frame is not None else None
        vert_departure_frame = next((i for i in range(before, -1, -1)
                                     if times[begin]-times[i] <= .15 and nearby[i] is not None), None)
        vert_departure = nearby[vert_departure_frame] if vert_departure_frame is not None else None
        if vert_departure is not None:
            departure_frame, departure = vert_departure_frame, vert_departure
            support = nearby[end] if landed else None
        takeoff = v[begin]
        angle = pitch(takeoff)
        horizontal = float(np.linalg.norm((p[last]-p[before])[[0, 2]]))
        forward = float(progress[last]-progress[before])
        peak = float(p[begin:last+1, 1].max())
        fail = []
        if not landed:
            fail.append('flight did not end in a riding-ground state')
        if support is None:
            fail.append('landing support unknown')
        landing_slope = slope(support['normal'], incoming) if support else None
        mismatch = abs(pitch(incoming)-landing_slope) if support else None
        vert_return = None
        if vert_departure is not None:
            vert_return = vert.flight(departure, support, begin, end, p, v, states, times, rules)
            fail.extend(vert_return['failures'])
        else:
            if support and (support['role'] not in ('landing', 'transition') or abs(landing_slope) < rules['min_landing_slope_deg']):
                fail.append('landing is not an intended sloped transition')
            if mismatch is not None and mismatch > rules['max_landing_mismatch_deg']:
                fail.append('incoming trajectory does not match landing slope')
        if vert_return is None and not world.spec.get('intended_vert', False) and abs(angle) > rules['max_takeoff_angle_deg']:
            fail.append('unintended near-vertical takeoff')
        recovery_end = times[last]+rules['landing_recovery_s']
        if landed and times[-1] < recovery_end:
            fail.append('insufficient observations after landing')
        if any(before <= i and times[i] <= recovery_end for i in bail):
            fail.append('bail/slam state during flight or recovery')
        normal_peak = float(np.max(np.abs(v[max(begin, end-3):end] @ support['normal']))) if support else None
        if normal_peak is not None and normal_peak > normal_limit:
            fail.append('landing normal speed exceeds the impact limit')
        safe_landing = not fail
        if min(horizontal, forward) < rules['huge_air_m']:
            fail.append('air is shorter than the required forward distance')
        airs.append(dict(takeoff_frame=int(begin), landing_frame=int(end) if landed else None,
                         termination_frame=int(end) if end < len(rows) else None,
                         termination_state=states[end] if end < len(rows) else 'frame_budget',
                         takeoff_position=p[before].tolist(), end_position=p[last].tolist(),
                         takeoff_station_m=float(progress[before]),
                         landing_station_m=float(progress[end]) if landed else None,
                         completed=bool(landed), duration_s=float(times[last]-times[before]),
                         takeoff_speed_mps=float(speed[begin]), takeoff_angle_deg=angle,
                         takeoff_surface=departure['surface'] if departure else None,
                         takeoff_support_frame=departure_frame,
                         horizontal_distance_m=horizontal, forward_progress_m=forward,
                         peak_height_m=peak, rise_above_takeoff_m=peak-float(p[before, 1]),
                         incoming_speed_mps=float(np.linalg.norm(incoming)), incoming_angle_deg=pitch(incoming),
                         landing_speed_mps=float(speed[end]) if landed else None,
                         landing_support=support, landing_slope_deg=landing_slope,
                         landing_normal_speed_mps=abs(float(np.dot(incoming,support['normal']))) if support else None,
                         landing_normal_speed_peak_3frames_mps=normal_peak,
                         landing_mismatch_deg=mismatch, safe_landing_pass=safe_landing,
                         huge_air_pass=not fail and vert_return is None, failures=fail,
                         **({'vert_return': vert_return} if vert_return is not None else {})))
    # Potential bump losses: gravity-corrected speed over uninterrupted, unbraked ground windows.
    # This does not distinguish friction from collisions and is not a contact impulse measurement.
    losses = []
    for end in range(1, len(rows)):
        start = int(np.searchsorted(times, times[end]-rules['bump_window_s']))
        if times[end]-times[start] < rules['bump_window_s']-.02 or times[start] < .3 or not ground[start:end+1].all():
            continue
        if any(r.get('buttons', 0) & 0x2000 for r in rows[start:end+1]):
            continue
        expected = math.sqrt(max(0., speed[start]**2+2*rules['gravity_mps2']*(p[start, 1]-p[end, 1])))
        loss = expected-speed[end]
        if loss > rules['bump_loss_mps']:
            event = dict(frame=end, time_s=float(times[end]), path_s_m=float(progress[end]),
                         speed_before_mps=float(speed[start]), speed_after_mps=float(speed[end]),
                         gravity_corrected_loss_mps=float(loss), position=p[end].tolist())
            if losses and times[end]-losses[-1]['time_s'] < rules['bump_window_s']:
                if loss > losses[-1]['gravity_corrected_loss_mps']:
                    losses[-1] = event
            else:
                losses.append(event)
    failures = []
    successful = [a for a in airs if a['huge_air_pass']]
    gap_checks = check_required_airs(airs, p, progress, world)
    for gap in gap_checks:
        if not gap['passed']:
            failures.append('required gap '+gap['id']+': '+'; '.join(gap['failures']))
    vert_checks = vert.summarize(airs)
    for check in vert_checks:
        if not check['passed']:
            failures.append('required vert return '+check['id']+': '+'; '.join(check['failures']))
    if not successful and vert.mode == 'route':
        failures.append('no completed qualifying huge air')
    required = world.spec.get('required_takeoffs', [name for name, s in world.sections.items() if s.get('role') == 'takeoff'])
    completed_takeoffs = {a['takeoff_surface'] for a in successful} | {g['takeoff'] for g in gap_checks if g['passed']}
    missing = sorted(set(required)-completed_takeoffs)
    if missing:
        failures.append('required takeoffs not completed: '+', '.join(missing))
    if bail:
        failures.append('bail/slam/offboard states observed')
    if losses:
        failures.append('excess ground speed-loss events')
    if any(a['duration_s'] >= .1 and not a['completed'] for a in airs):
        failures.append('unlanded flight')
    if any(a['duration_s'] >= .1 and any(reason != 'air is shorter than the required forward distance'
                                       for reason in a['failures']) for a in airs):
        failures.append('flight has an unsafe or unverified landing/takeoff')
    # A diagnostic wide lane never widens the authored route's acceptance corridor.
    if lateral.max() > world.design_width/2:
        failures.append('rider left the designed rideable corridor')
    finish = world.finish_m
    if progress.max() < finish:
        failures.append('line finish not reached')
    steep = [i for i, s in enumerate(supports) if s and s['surface'] not in vert.requirements
             and math.degrees(math.acos(np.clip(s['normal'][1], -1, 1))) > rules['max_ground_slope_deg']]
    if steep and not world.spec.get('intended_vert', False):
        failures.append('unintended near-vertical ground surface')
    unknown_mask = np.array([g and s is None for g, s in zip(ground, supports)])
    unknown = int(unknown_mask.sum())
    consecutive = longest = 0
    for missing_support in unknown_mask:
        consecutive = consecutive+1 if missing_support else 0
        longest = max(longest,consecutive)
    if longest/60 > .15:
        failures.append('sustained ground state with unidentified supporting collision')
    return dict(passed=not failures, failures=failures, thresholds=rules, frames=len(rows),
                validation_mode=vert.mode, vert_checks=vert_checks,
                duration_s=float(times[-1]), speed_mps=dict(min=float(speed.min()), max=float(speed.max()),
                final=float(speed[-1])), path_progress_m=float(progress.max()), finish_s_m=finish,
                max_lateral_error_m=float(lateral.max()), rideable_width_m=world.design_width,
                diagnostic_lane_width_m=world.width, airs=airs, gap_checks=gap_checks, bump_candidates=losses,
                speed_along_line=[dict(time_s=float(times[i]),path_s_m=float(progress[i]),
                                      speed_mps=float(speed[i]),height_m=float(p[i,1]),state=states[i])
                                  for i in range(0,len(rows),15)],
                bail_events=[dict(frame=i,time_s=float(times[i]),state=states[i],position=p[i].tolist())
                             for i in bail if i == 0 or not is_bail(states[i-1])],
                unknown_ground_support_frames=unknown,
                longest_unknown_ground_support_s=longest/60,
                support_method='Vertical triangle query; declared vert walls also use nearby 3D collision. Both inferred, not exported contacts.',
                normal_speed_method='Last airborne velocity and peak absolute normal component of the last three airborne velocities against the inferred landing plane; not contact impulse or a universal impact limit.',
                bump_method='Gravity-corrected speed loss on uninterrupted unbraked ground; friction/collision cause is not identified.',
                flight_method='60 Hz published animated-root positions and velocities; endpoints are frame-resolution observations.')
