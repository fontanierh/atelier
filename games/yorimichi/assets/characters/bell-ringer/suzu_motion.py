"""Suzu's accessory motion and her slower, shorter NPC clips over the villager kit's contact solver."""
from copy import deepcopy

import animate as compact

SECONDARY = {
    # The bun is light and tied tight: it lags a little behind the head.
    'bun': dict(kind='pendulum', length=.055, stiffness=150, damping=11,
                limit_x=(-.10, .10), limit_y=(-.10, .10)),
    # The hand bell swings on its cord from the knot at her hip.
    'bell': dict(kind='pendulum', length=.13, stiffness=52, damping=6, limit_x=(-.34, .12), limit_y=(-.20, .20),
                 bounce=dict(stiffness=420, damping=14, limit=.010)),
    # The folded cloth in the obi moves with the skirt.
    'cloth': dict(kind='pendulum', length=.17, stiffness=46, damping=6, limit_x=(-.34, .08), limit_y=(-.16, .16)),
}

KEEP = ('Idle', 'Walk', 'Jog', 'CrouchIdle', 'CrouchWalk', 'JumpStart', 'JumpRise', 'Fall', 'Land',
        'Interact', 'Wave', 'SitDown', 'SitIdle', 'StandUp', 'TurnLeft', 'TurnRight')
ACTIONS = {name: deepcopy(compact.ACTIONS[name]) for name in KEEP}

# An old woman walks at .62 m/s with a short, flat stride, and turns slowly. Nothing about her should read as a
# fighter: the arms swing only a little and the torso stays quiet.
ACTIONS['Walk'].update(duration=64/60, speed=.62, stance=.64, lift=.030, arm=.17, lean=2.5)
ACTIONS['Jog'].update(duration=52/60, speed=1.15, stance=.36, lift=.075, arm=.30, lean=5.)
ACTIONS['CrouchWalk'].update(duration=1.2, speed=.40, lift=.024)
ACTIONS['TurnLeft'].update(duration=.95)
ACTIONS['TurnRight'].update(duration=.95)
ACTIONS['Wave'].update(duration=2.8)
for settings in ACTIONS.values():
    settings['frames'] = round(settings['duration']*60)+1
    settings['duration'] = (settings['frames']-1)/60


def build_actions(arm, out):
    compact.build_actions(arm, out, ACTIONS, SECONDARY)
