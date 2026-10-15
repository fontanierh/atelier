"""Optional path tracking through ordinary left-stick input; never edits simulation state."""
import math
import numpy as np

from park_line_metrics import is_ground
from park_line_geometry import RouteProgress


class LineFollower:
    """@cc [owner:fontanierh,label:correctness] controller-input-only
    Following MUST use observed position/velocity and ordinary controller input only.
    It MUST emit neutral steering while airborne or offboard; no pose/velocity correction is permitted.
    A failed tracking trial MUST NOT be represented as proof of a geometry defect.
    """

    def __init__(self, path, config, *, start_m=None):
        self.path = path
        self.progress = RouteProgress(path,start_m)
        self.settings = dict(lookahead_m=5., lookahead_seconds=.45, gain=4., max_stick=.85,
                             smoothing_seconds=.15, min_speed_mps=.5)
        unknown = set(config)-set(self.settings)-{'mode', 'zones'}
        if unknown or config.get('mode', 'pursuit') != 'pursuit':
            raise ValueError('Unknown line follower mode/settings: '+str(sorted(unknown)))
        self.settings.update({k: v for k, v in config.items() if k not in ('mode', 'zones')})
        if any(not math.isfinite(v) or v <= 0 for v in self.settings.values()):
            raise ValueError('Line follower settings must be finite and positive')
        if self.settings['max_stick'] > 1:
            raise ValueError('max_stick cannot exceed normalized controller range 1')
        zones = config.get('zones', [])
        if not isinstance(zones, list):
            raise ValueError('follower zones must be a list')
        self.zones = []
        for zone in zones:
            if not isinstance(zone, dict) or set(zone) - set(self.settings) - {'start_s_m', 'end_s_m'}:
                raise ValueError('Unknown follower zone fields')
            a, b = float(zone.get('start_s_m', -1)), float(zone.get('end_s_m', -1))
            values = {k: v for k, v in zone.items() if k in self.settings}
            if (not math.isfinite(a) or not math.isfinite(b) or not 0 <= a < b <= path.s[-1]
                    or any(not math.isfinite(v) or v <= 0 for v in values.values())
                    or values.get('max_stick', 1) > 1):
                raise ValueError('Invalid follower zone bounds or settings')
            self.zones.append(dict(start_s_m=a, end_s_m=b, **values))
        self.zones.sort(key=lambda z: z['start_s_m'])
        if any(a['end_s_m'] > b['start_s_m'] for a, b in zip(self.zones[:-1], self.zones[1:])):
            raise ValueError('follower zones cannot overlap')
        self.previous = 0.
        self.active_frames = self.saturated_frames = 0

    def steering(self, row):
        if row is None:
            self.previous = 0.
            return 0
        position = np.asarray(row['position'], 'f8')
        velocity = np.asarray(row['velocity'], 'f8')[[0, 2]]
        speed = float(np.linalg.norm(velocity))
        station,_ = self.progress.update(position,speed)
        if not is_ground(row['state']):
            self.previous = 0.
            return 0
        settings = self.settings
        for zone in self.zones:
            if zone['start_s_m'] <= station < zone['end_s_m']:
                settings = {**self.settings, **zone}
                break
        if speed < settings['min_speed_mps']:
            self.previous = 0.
            return 0
        lookahead = settings['lookahead_m']+settings['lookahead_seconds']*speed
        target, _ = self.path.at(min(self.path.s[-1], station+lookahead))
        delta = target-position[[0, 2]]
        if np.linalg.norm(delta) < 1e-8:
            self.previous = 0.
            return 0
        heading = math.atan2(velocity[0], velocity[1])
        error = math.atan2(delta[0], delta[1])-heading
        error = math.atan2(math.sin(error), math.cos(error))
        # Native calibration: positive left.x turns velocity toward negative heading.
        requested = -settings['gain']*error
        limit = settings['max_stick']
        self.active_frames += 1
        self.saturated_frames += abs(requested) > limit
        target_stick = float(np.clip(requested, -limit, limit))
        blend = min(1., (1/60)/settings['smoothing_seconds'])
        self.previous = float(np.clip(self.previous + blend*(target_stick-self.previous), -limit, limit))
        return int(round(self.previous*32767))

    def report(self):
        return dict(mode='pursuit', settings=self.settings, zones=self.zones, active_frames=self.active_frames,
                    saturated_frames=int(self.saturated_frames),
                    scope='Ground-only left-stick path tracking; controller failure is not proof of a geometry defect.')
