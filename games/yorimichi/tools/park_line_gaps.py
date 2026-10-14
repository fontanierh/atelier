"""Named gap requirements measured within one continuous native Session trace."""
import math
import numpy as np


def validate_gap_specs(world):
    specs = world.spec.get('required_airs', [])
    if not isinstance(specs, list):
        raise ValueError('required_airs must be a list')
    normalized = []
    names, takeoffs = set(), set()
    allowed = {'id', 'takeoff', 'landing', 'knuckle_s_m', 'knuckle_y_m', 'landing_end_s_m',
               'min_knuckle_margin_m', 'min_air_m', 'min_takeoff_speed_mps'}
    for spec in specs:
        if not isinstance(spec, dict):
            raise ValueError('Each required air must be an object')
        spec = dict(spec)
        if set(spec)-allowed:
            raise ValueError('Unknown required_airs fields: '+', '.join(sorted(set(spec)-allowed)))
        for key in ('id', 'takeoff', 'landing'):
            if not isinstance(spec.get(key), str) or not spec[key]:
                raise ValueError('Each required air needs nonempty id, takeoff and landing names')
        if spec['id'] in names or spec['takeoff'] in takeoffs:
            raise ValueError('Required air IDs and takeoff names must be unique')
        names.add(spec['id']); takeoffs.add(spec['takeoff'])
        if world.sections.get(spec['takeoff'], {}).get('role') != 'takeoff':
            raise ValueError('Required air takeoff must name a tagged takeoff surface')
        if world.sections.get(spec['landing'], {}).get('role') not in ('landing', 'transition'):
            raise ValueError('Required air landing must name a tagged landing or transition surface')
        for key in ('knuckle_s_m', 'landing_end_s_m'):
            if key not in spec or not math.isfinite(float(spec[key])):
                raise ValueError('Required airs need finite knuckle_s_m and landing_end_s_m')
            spec[key] = float(spec[key])
        if not 0 <= spec['knuckle_s_m'] < spec['landing_end_s_m'] <= world.path.s[-1]:
            raise ValueError('Required air landing interval must lie within the route')
        for key in ('min_knuckle_margin_m', 'min_air_m', 'min_takeoff_speed_mps'):
            value = float(spec.get(key, 0))
            if not math.isfinite(value) or value < 0:
                raise ValueError(key+' must be finite and nonnegative')
            spec[key] = value
        if 'knuckle_y_m' in spec and not math.isfinite(float(spec['knuckle_y_m'])):
            raise ValueError('knuckle_y_m must be finite')
        if 'knuckle_y_m' in spec:
            spec['knuckle_y_m'] = float(spec['knuckle_y_m'])
        normalized.append(spec)
    return normalized


def check_required_airs(airs, positions, progress, world):
    """@cc [owner:fontanierh,label:correctness] paired-gap-acceptance
    Each declared gap MUST have its own completed, safe flight from the named takeoff to the named receiver,
    in declaration order, with the configured distance, speed and touchdown interval. A later or different
    successful air MUST NOT hide a missed gap. Clearance observations MUST NOT replace landing safety checks.
    """
    results = []; previous_end = -1
    for spec in validate_gap_specs(world):
        candidates = [i for i, a in enumerate(airs) if a['takeoff_surface'] == spec['takeoff']]
        result = dict(id=spec['id'], takeoff=spec['takeoff'], landing=spec['landing'],
                      requirements=spec, air_index=candidates[0] if candidates else None,
                      touchdown_margin_m=None, vertical_clearance_at_knuckle_m=None,
                      clearance_method='Interpolated 60 Hz animated root at route station minus supplied knuckle height; not wheel clearance.')
        fail = []
        if not candidates:
            fail.append('no observed flight from required takeoff')
        else:
            a = airs[candidates[0]]
            if len(candidates) > 1:
                fail.append('multiple flights from required takeoff; inspect the continuous trace')
            if a['takeoff_frame'] <= previous_end:
                fail.append('required gaps were not ridden in declaration order')
            if a['landing_frame'] is not None:
                previous_end = max(previous_end, a['landing_frame'])
            if not a['safe_landing_pass']:
                fail.append('flight failed landing/takeoff/recovery safety checks')
            support = a['landing_support']
            if support is None or support['surface'] != spec['landing']:
                fail.append('flight did not touch down on its named receiver')
            if min(a['horizontal_distance_m'], a['forward_progress_m']) < spec.get('min_air_m', 0):
                fail.append('flight is shorter than this gap requires')
            if a['takeoff_speed_mps'] < spec.get('min_takeoff_speed_mps', 0):
                fail.append('takeoff speed is below this gap requirement')
            if a['landing_frame'] is not None:
                station = a['landing_station_m']
                margin = station-spec['knuckle_s_m']
                result['touchdown_margin_m'] = margin
                if margin < spec.get('min_knuckle_margin_m', 0):
                    fail.append('touchdown is too close to or before the knuckle')
                if station > spec['landing_end_s_m']:
                    fail.append('touchdown is beyond the intended sloped receiver')
            # Report vertical clearance only for an observed forward crossing in this flight.
            if 'knuckle_y_m' in spec:
                begin = max(0, a['takeoff_frame']-1)
                end = a['termination_frame'] if a['termination_frame'] is not None else len(progress)-1
                s0, s1 = progress[begin:end], progress[begin+1:end+1]
                crossing = np.flatnonzero((s0 <= spec['knuckle_s_m']) & (s1 >= spec['knuckle_s_m']) & (s1 > s0))
                if len(crossing):
                    i = begin+int(crossing[0])
                    t = (spec['knuckle_s_m']-progress[i])/(progress[i+1]-progress[i])
                    result['vertical_clearance_at_knuckle_m'] = float(
                        positions[i, 1]*(1-t)+positions[i+1, 1]*t-spec['knuckle_y_m'])
        result.update(passed=not fail, failures=fail)
        results.append(result)
    return results
