"""Explicit same-wall vert-return observations; collision normals remain inferred."""
import math
import numpy as np


class VertReturns:
    def __init__(self, world):
        self.world = world
        self.mode = world.spec.get('validation_mode', 'route')
        if self.mode not in ('route', 'vert_return'):
            raise ValueError('validation_mode must be route or vert_return')
        self.requirements = {}
        self.ground_touches = set()
        names = set()
        specs = world.spec.get('required_vert_returns', [])
        if not isinstance(specs, list):
            raise ValueError('required_vert_returns must be a list')
        defaults = dict(max_contact_distance_m=.25, max_departure_distance_m=.75,
                        min_apex_above_coping_m=.5)
        allowed = set(defaults) | {'id', 'surface', 'coping_y_m', 'max_normal_speed_mps', 'require_air'}
        for original in specs:
            if not isinstance(original, dict) or set(original)-allowed:
                raise ValueError('Unknown or invalid required_vert_returns fields')
            spec = {**defaults, **original}
            spec.setdefault('require_air', True)
            if not isinstance(spec['require_air'], bool):
                raise ValueError('Vert require_air must be a boolean')
            if self.mode == 'vert_return' and not spec['require_air']:
                raise ValueError('Vert-only trials must require their wall air-out')
            for key in ('id', 'surface'):
                if not isinstance(spec.get(key), str) or not spec[key]:
                    raise ValueError('Vert returns need nonempty id and surface names')
            if spec['id'] in names or spec['surface'] in self.requirements:
                raise ValueError('Vert return IDs and surface names must be unique')
            if world.sections.get(spec['surface'], {}).get('role') not in ('vert', 'transition'):
                raise ValueError('Vert return surface must name a vert or transition region')
            for key in ('coping_y_m', 'max_normal_speed_mps', *defaults):
                if key not in spec or not math.isfinite(float(spec[key])):
                    raise ValueError('Vert return bounds and coping height must be finite')
                spec[key] = float(spec[key])
                if key != 'coping_y_m' and spec[key] <= 0:
                    raise ValueError('Vert return bounds must be positive')
            if spec['max_contact_distance_m'] > .5 or spec['max_departure_distance_m'] > 1:
                raise ValueError('Vert proximity bounds exceed .5 m contact or 1 m departure limit')
            if spec['max_normal_speed_mps'] > 7.:
                raise ValueError('Vert normal-speed limit must be at most 7 m/s')
            names.add(spec['id']); self.requirements[spec['surface']] = spec
        if self.mode == 'vert_return' and (not specs or world.spec.get('required_airs')):
            raise ValueError('Vert-only trials need required_vert_returns and cannot declare gap trials')

    def nearest_ground(self, positions, ground):
        """Globally nearest collision faces, never a search restricted to a desired return region."""
        result = [None]*len(positions)
        if not self.requirements or not ground.any():
            return result
        indices = np.flatnonzero(ground)
        distance, faces, weights = self.world.tree.nearest(positions[indices])
        for i, d, f, bary in zip(indices, distance, faces, weights):
            if f < 0:
                continue
            name = str(self.world.labels[f])
            if name not in self.requirements or d > self.requirements[name]['max_departure_distance_m']:
                continue
            n = self.world.normal[f]
            if n[1] < -1e-6 or self.world.area[f] < 1e-12:
                continue
            result[i] = dict(face=int(f), surface=name, role=self.world.sections[name]['role'],
                             height_m=float(bary @ self.world.triangles[f, :, 1]), normal=n.tolist(),
                             distance_m=float(d), method='globally nearest 3D collision triangle; inferred')
            if d <= self.requirements[name]['max_contact_distance_m'] and n[1] <= math.cos(math.radians(15.)):
                self.ground_touches.add(name)
        return result

    def on_wall(self, support):
        return support is not None and support['distance_m'] <= self.requirements[support['surface']]['max_contact_distance_m']

    def flight(self, departure, landing, begin, end, positions, velocities, states, times, rules):
        """@cc [owner:fontanierh,label:correctness] scoped-vert-return
        Only an explicit same-wall return MAY replace the directional slope/mismatch check. It MUST have
        nearby collision on that named wall, bounded inferred normal speed, an apex above the declared coping,
        and riding-ground recovery. Ordinary gap flights MUST retain their existing landing checks.
        Vert returns MUST NOT count as the route's required huge air.
        """
        spec = self.requirements[departure['surface']]
        fail = []; impact = wall_slope = None
        landed = end < len(states) and states[end] in ('PhysicsGround', 'RevertGround')
        if not landed or landing is None or landing['surface'] != spec['surface'] or not self.on_wall(landing):
            fail.append('vert return lacks nearby collision on its named wall')
        else:
            n = np.asarray(landing['normal'])
            # Last three airborne frames (up to 50 ms) reduce reliance on a velocity already altered by contact.
            impact = float(np.max(np.abs(velocities[max(begin, end-3):end] @ n)))
            wall_slope = math.degrees(math.acos(float(np.clip(n[1], -1, 1))))
            if wall_slope < rules['min_landing_slope_deg']:
                fail.append('vert return landed on a flat deck or apron')
            if impact > min(spec['max_normal_speed_mps'], rules['max_landing_normal_speed_mps']):
                fail.append('vert return exceeds inferred normal-speed limit')
            recovery = (times >= times[end]) & (times <= times[end]+rules['landing_recovery_s'])
            if not all(states[i] in ('PhysicsGround', 'RevertGround') for i in np.flatnonzero(recovery)):
                fail.append('vert return did not retain riding-ground recovery')
        last = min(end, len(positions)-1)
        apex = float(positions[begin:last+1, 1].max()-spec['coping_y_m'])
        if apex < spec['min_apex_above_coping_m']:
            fail.append('vert flight did not clear the declared coping height')
        return dict(id=spec['id'], surface=spec['surface'], requirements=spec,
                    return_support=landing, inferred_normal_speed_mps=impact, wall_slope_deg=wall_slope,
                    apex_above_coping_m=apex, failures=fail,
                    method='Peak absolute normal component of last three airborne velocities against nearest return face; not a contact impulse.')

    def summarize(self, airs):
        """@cc [owner:fontanierh,label:correctness] optional-grounded-vert
        Route-only require_air=false MAY accept a grounded carve only with
        nearby named collision on a wall at least fifteen degrees steep. Any
        observed wall flight MUST still pass the same air-out safety checks.
        This option MUST NOT replace the route hero air or relax impact limits.
        """
        result = []
        for surface, spec in self.requirements.items():
            candidates = [i for i, a in enumerate(airs) if a.get('vert_return', {}).get('surface') == surface]
            grounded = not candidates and not spec['require_air'] and surface in self.ground_touches
            passed = grounded or bool(candidates) and all(airs[i]['safe_landing_pass'] for i in candidates)
            result.append(dict(id=spec['id'], surface=surface, air_indices=candidates, passed=passed,
                               grounded_carve=grounded,
                               failures=[] if passed else ['required same-wall air-out was absent or failed']))
        return result
