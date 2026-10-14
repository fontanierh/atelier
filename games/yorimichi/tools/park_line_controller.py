"""Optional path tracking through ordinary left-stick input; never edits simulation state."""
import math
import numpy as np

from park_line_metrics import is_ground


class LineFollower:
    """@cc [owner:fontanierh,label:correctness] controller-input-only
    Following MUST use observed position/velocity and ordinary controller input only.
    It MUST emit neutral steering while airborne or offboard; no pose/velocity correction is permitted.
    A failed tracking trial MUST NOT be represented as proof of a geometry defect.
    """

    def __init__(self, path, config):
        self.path = path
        self.settings = dict(lookahead_m=5., lookahead_seconds=.45, gain=4., max_stick=.85,
                             smoothing_seconds=.15, min_speed_mps=.5)
        unknown = set(config)-set(self.settings)-{'mode'}
        if unknown or config.get('mode', 'pursuit') != 'pursuit':
            raise ValueError('Unknown line follower mode/settings: '+str(sorted(unknown)))
        self.settings.update({k: v for k, v in config.items() if k != 'mode'})
        if any(not math.isfinite(v) or v <= 0 for v in self.settings.values()):
            raise ValueError('Line follower settings must be finite and positive')
        if self.settings['max_stick'] > 1:
            raise ValueError('max_stick cannot exceed normalized controller range 1')
        self.previous = 0.
        self.active_frames = self.saturated_frames = 0

    def steering(self, row):
        if row is None or not is_ground(row['state']):
            self.previous = 0.
            return 0
        position = np.asarray(row['position'], 'f8')
        velocity = np.asarray(row['velocity'], 'f8')[[0, 2]]
        speed = float(np.linalg.norm(velocity))
        if speed < self.settings['min_speed_mps']:
            self.previous = 0.
            return 0
        station = float(self.path.project(position[None])[0][0])
        lookahead = self.settings['lookahead_m']+self.settings['lookahead_seconds']*speed
        target, _ = self.path.at(min(self.path.s[-1], station+lookahead))
        delta = target-position[[0, 2]]
        if np.linalg.norm(delta) < 1e-8:
            self.previous = 0.
            return 0
        heading = math.atan2(velocity[0], velocity[1])
        error = math.atan2(delta[0], delta[1])-heading
        error = math.atan2(math.sin(error), math.cos(error))
        # Native calibration: positive left.x turns velocity toward negative heading.
        requested = -self.settings['gain']*error
        limit = self.settings['max_stick']
        self.active_frames += 1
        self.saturated_frames += abs(requested) > limit
        target_stick = float(np.clip(requested, -limit, limit))
        blend = min(1., (1/60)/self.settings['smoothing_seconds'])
        self.previous += blend*(target_stick-self.previous)
        return int(round(self.previous*32767))

    def report(self):
        return dict(mode='pursuit', settings=self.settings, active_frames=self.active_frames,
                    saturated_frames=int(self.saturated_frames),
                    scope='Ground-only left-stick path tracking; controller failure is not proof of a geometry defect.')
