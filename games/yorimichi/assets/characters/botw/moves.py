"""A character's move set (moves.toml) as the game reads it: export.py bakes its clips with the character and calls
`record` for the `moves` entry of export.json.

Each action gets its clip's timing from BOTW's action timelines (mechanics.json, frames at 30 per second): the rate
it plays at, where it starts and ends, how long it blends in, and its windows in clip seconds (`active` when hits land,
`input` from when the next press is read, `cancel` from when anything may follow, `guard` when a hit is parried,
`idle` when it is over, `bind` and `unbind` when equipment changes hands; -1 when the timeline has none). A driven
clip keeps its root path, converted to the actor's frame: per frame forward, right and up in game centimetres and the
turn in degrees (Unreal's yaw, positive to the right).

Blend samples and gait actions (`gait = true`, the lock-on strafes) get their speeds (cm/s, at the game scale) from
the clip's ground speed at the rate the timeline plays it. The equipment is baked beside the character: a prop as a
static mesh in its rig's space, the glider skinned with its clip; each slot's carry offset is converted to Unreal bone
space (centimetres and an (x, y, z, w) quaternion).
"""
import json
import math
import tomllib
from pathlib import Path

import numpy as np

import bake
import library

TIMELINE = 'GameROMPlayer/Actor/AS/{}.bas'
MODES = ('keep', 'strip', 'drive')
# BOTW action timeline events (zeldamods.org/wiki/Bas): hold 3 hits land, 45 the next input is read, 2 anything may
# follow, 14 a guard parries; trigger 4 the action is over, 29 a weapon is taken in hand, 30 it goes back.
HOLDS = {'active': 3, 'input': 45, 'cancel': 2, 'guard': 14}
TRIGGERS = {'idle': 4, 'bind': 29, 'unbind': 30}
# glTF (y up, right-handed) to Unreal (z up, left-handed) as the Interchange glTF importer converts: swap y and z.
GLTF_TO_UNREAL = np.array([[1., 0., 0.], [0., 0., 1.], [0., 1., 0.]])


def load(path):
    spec = tomllib.loads(Path(path).read_text())
    for name, action in spec['action'].items():
        if action.get('root', 'keep') not in MODES:
            raise ValueError(f'{path}: action {name} has root {action["root"]!r}, not one of {MODES}')
    return spec


def clips(spec):
    """Every clip the move set plays, in order of first use."""
    out = []
    for name in [a['clip'] for a in spec['action'].values()] + \
                [s['clip'] for samples in spec['blend'].values() for s in samples]:
        if name not in out:
            out.append(name)
    return out


def modes(spec):
    """The clips to strip and to drive (bake.bake's `strip` and `drive`); a clip has one mode across its actions."""
    seen = {}
    for name, action in spec['action'].items():
        mode = action.get('root', 'keep')
        if seen.setdefault(action['clip'], mode) != mode:
            raise ValueError(f"{action['clip']} is played with root modes {seen[action['clip']]} and {mode}")
    return ({clip for clip, mode in seen.items() if mode == 'strip'},
            {clip for clip, mode in seen.items() if mode == 'drive'})


def element(timelines, timeline, clip):
    """The first element of an action timeline that plays `clip`."""
    elements = timelines.get(TIMELINE.format(timeline))
    if elements is None:
        raise ValueError(f'mechanics.json has no action timeline {timeline}')
    for item in elements:
        if item['parameters'].get('FileName') == clip:
            return item
    raise ValueError(f'{timeline} never plays {clip}')


def timing(item, frames, fps):
    """Rate, start, end, blend and windows (clip seconds) of one timeline element; `frames` is the clip's last frame."""
    control = {key: value for entry in item['frame_control'] for key, value in entry.items()} if item else {}
    second = lambda frame: round(min(max(float(frame), 0.), frames) / fps, 4)
    end = control.get('EndFrame', -1)
    out = {'rate': round(float(control.get('Rate', 1.)), 4), 'start': second(control.get('StartFrame', 0)),
           'end': second(frames if end < 0 else end),
           'blend': round(float(item['parameters'].get('Morph', 0.)) / fps, 4) if item else 0.}
    holds = item['hold_events'] if item else []
    triggers = item['trigger_events'] if item else []
    for key, kind in HOLDS.items():
        spans = [[second(h['StartFrame']), second(frames if h['EndFrame'] < 0 else h['EndFrame'])]
                 for h in holds if h['TypeIndex'] == kind]
        out[key] = spans if key in ('active', 'guard') else (spans[0][0] if spans else -1)
    for key, kind in TRIGGERS.items():
        out[key] = next((second(t['Frame']) for t in triggers if t['TypeIndex'] == kind), -1)
    return out


def actor_path(path, scale):
    """A baked root path (clip space metres, radians) as actor-frame centimetres and Unreal yaw degrees."""
    out = []
    for x, y, z, yaw in path:
        out.append([round(z * 100. * scale, 2), round(-x * 100. * scale, 2), round(y * 100. * scale, 2),
                    round(-math.degrees(yaw), 2)])
    return out


def unreal_offset(offset, rotation):
    """A carry offset in a glTF bone's frame (metres, BOTW Euler XYZ degrees) in the imported bone's frame."""
    matrix = bake.matrices_from_quat(bake.quat_xyzw_from_euler_xyz(np.radians(rotation)))
    turned = GLTF_TO_UNREAL @ matrix @ GLTF_TO_UNREAL
    quat = bake.quat_from_matrices(turned)
    return {'location': [round(float(v) * 100., 3) for v in GLTF_TO_UNREAL @ np.asarray(offset, float)],
            'rotation': [round(float(v), 6) for v in quat]}


def equipment(spec, character, out):
    """Bake each equipment slot beside the character: build/.../glb/<Character><Slot>.glb."""
    slots = {}
    for slot, item in spec.get('equipment', {}).items():
        source = library.entry(item['id'])
        target = out / f"{character}{slot.capitalize()}.glb"
        record = {'id': item['id'], 'glb': str(target), 'hand': item.get('hand', ''), 'back': item.get('back', '')}
        if 'clip' in item:
            summary = bake.bake(source['glb'], source['curves'], target, clips=[item['clip']])
            record['clip'] = summary['clips'][0]['name']
            record['frames'] = summary['clips'][0]['frames']
        else:
            bake.static(source['glb'], target)
        if 'offset' in item:
            record['carry'] = unreal_offset(item['offset'], item['rotation'])
        slots[slot] = record
    return slots


def record(spec, curves, summary, scale, out, rename, speed):
    """The `moves` entry of a character's export record. `summary` is bake.bake's for the character, `rename` makes a
    clip name Unreal-safe and `speed(clip)` measures a locomotion clip's ground speed in m/s."""
    mechanics = json.loads(library.mechanics().read_text())
    timelines = mechanics['animation_timelines']
    fps = summary['fps']
    baked = {clip['source']: clip for clip in summary['clips']}
    by_source = {clip['name']: clip for clip in curves['animations']}
    actions = {}
    for name, action in spec['action'].items():
        clip = baked[action['clip']]
        item = element(timelines, action['as'], action['clip']) if 'as' in action else None
        if item is not None and 'events' in action:
            # Its windows are another element's of the same timeline (BOTW keeps them on one element).
            donor = element(timelines, action['as'], action['events'])
            item = {**item, 'hold_events': donor['hold_events'], 'trigger_events': donor['trigger_events']}
        entry = {'clip': rename(action['clip']), 'length': round(clip['frames'] / fps, 4),
                 'loop': bool(action.get('loop', clip['loop'])), 'root': action.get('root', 'keep'),
                 **timing(item, clip['frames'], fps)}
        if 'path' in clip:
            entry['path'] = actor_path(clip['path'], scale)
        elif action.get('gait'):
            entry['speed'] = round((speed(by_source[action['clip']]) or 0.) * entry['rate'] * scale * 100., 1)
        actions[name] = entry
    blends = {}
    for blend, samples in spec['blend'].items():
        rows = []
        for index, sample in enumerate(samples):
            rate = sample.get('rate')
            if rate is None:
                rate = timing(element(timelines, sample['as'], sample['clip']), 0, fps)['rate'] if 'as' in sample else 1.
            rows.append({'clip': rename(sample['clip']), 'rate': round(float(rate), 4),
                         'speed': 0. if index == 0 else round(speed(by_source[sample['clip']]) * rate * scale * 100., 1)})
        blends[blend] = rows
    # The armed blend plays the upper body over the locomotion: it takes the locomotion's sample speeds.
    if 'armed' in blends:
        for row, base in zip(blends['armed'], blends['locomotion']):
            row['speed'] = base['speed']
    params = {}
    for cls in spec['params']['actions']:
        found = next((a for a in mechanics['player_actions'] if a['Def']['ClassName'] == cls), None)
        if found is None:
            raise ValueError(f'mechanics.json has no player action {cls}')
        params.update({f'{cls}.{key}': value for key, value in found['SInst'].items()
                       if isinstance(value, (int, float))})
    for key in spec['params']['globals']:
        params[key] = mechanics['player_parameters'][key]
    params['SwimHang'] = round(float(spec['params']['swim_hang']) * 100. * scale, 2)
    return {'actions': actions, 'blends': blends, 'params': params,
            'equipment': equipment(spec, spec['character'], out)}
