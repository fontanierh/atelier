"""Measurements from actual Session frames; inferred geometry is labelled separately."""
import math
import numpy as np

DEFAULTS = dict(huge_air_m=25., min_landing_slope_deg=5., max_landing_mismatch_deg=20.,
                max_takeoff_angle_deg=80., max_ground_slope_deg=85., bump_loss_mps=2.,
                bump_window_s=.25, landing_recovery_s=.5, gravity_mps2=9.81)


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
    """
    rules = {**DEFAULTS, **world.spec.get('acceptance', {})}
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
        if support and (support['role'] not in ('landing', 'transition') or abs(landing_slope) < rules['min_landing_slope_deg']):
            fail.append('landing is not an intended sloped transition')
        if mismatch is not None and mismatch > rules['max_landing_mismatch_deg']:
            fail.append('incoming trajectory does not match landing slope')
        if not world.spec.get('intended_vert', False) and abs(angle) > rules['max_takeoff_angle_deg']:
            fail.append('unintended near-vertical takeoff')
        recovery_end = times[last]+rules['landing_recovery_s']
        if landed and times[-1] < recovery_end:
            fail.append('insufficient observations after landing')
        if any(before <= i and times[i] <= recovery_end for i in bail):
            fail.append('bail/slam state during flight or recovery')
        if min(horizontal, forward) < rules['huge_air_m']:
            fail.append('air is shorter than the required forward distance')
        airs.append(dict(takeoff_frame=int(begin), landing_frame=int(end) if landed else None,
                         termination_frame=int(end) if end < len(rows) else None,
                         termination_state=states[end] if end < len(rows) else 'frame_budget',
                         takeoff_position=p[before].tolist(), end_position=p[last].tolist(),
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
                         landing_mismatch_deg=mismatch, huge_air_pass=not fail, failures=fail))
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
    if not successful:
        failures.append('no completed qualifying huge air')
    required = world.spec.get('required_takeoffs', [name for name, s in world.sections.items() if s.get('role') == 'takeoff'])
    missing = sorted(set(required)-{a['takeoff_surface'] for a in successful})
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
    steep = [i for i, s in enumerate(supports) if s and math.degrees(math.acos(np.clip(s['normal'][1], -1, 1))) > rules['max_ground_slope_deg']]
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
                duration_s=float(times[-1]), speed_mps=dict(min=float(speed.min()), max=float(speed.max()),
                final=float(speed[-1])), path_progress_m=float(progress.max()), finish_s_m=finish,
                max_lateral_error_m=float(lateral.max()), rideable_width_m=world.design_width,
                diagnostic_lane_width_m=world.width, airs=airs, bump_candidates=losses,
                speed_along_line=[dict(time_s=float(times[i]),path_s_m=float(progress[i]),
                                      speed_mps=float(speed[i]),height_m=float(p[i,1]),state=states[i])
                                  for i in range(0,len(rows),15)],
                bail_events=[dict(frame=i,time_s=float(times[i]),state=states[i],position=p[i].tolist())
                             for i in bail if i == 0 or not is_bail(states[i-1])],
                unknown_ground_support_frames=unknown,
                longest_unknown_ground_support_s=longest/60,
                support_method='Vertical triangle query under animated root; inferred, not exported simulator contacts.',
                bump_method='Gravity-corrected speed loss on uninterrupted unbraked ground; friction/collision cause is not identified.',
                flight_method='60 Hz published animated-root positions and velocities; endpoints are frame-resolution observations.')
