"""Imagegen-directed compact gaits on the proven continuous contact solver."""
from copy import deepcopy
import animate as compact
from accessories import SECONDARY

ACTIONS=deepcopy(compact.ACTIONS)
ACTIONS['Walk'].update(duration=56/60,speed=.90,stance=.60,lift=.043,arm=.28,lean=3.)
ACTIONS['Jog'].update(duration=46/60,speed=1.80,stance=.34,lift=.105,arm=.43,lean=7.)
ACTIONS['Run'].update(duration=38/60,speed=3.00,stance=.25,lift=.145,arm=.57,lean=9.)
ACTIONS['CrouchWalk'].update(duration=1.15,speed=.50,lift=.035)
for cfg in ACTIONS.values():
    cfg['frames']=round(cfg['duration']*60)+1
    cfg['duration']=(cfg['frames']-1)/60

def build_actions(arm,out):
    compact.build_actions(arm,out,ACTIONS,SECONDARY)
