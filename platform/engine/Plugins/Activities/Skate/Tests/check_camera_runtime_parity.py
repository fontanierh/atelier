#!/usr/bin/env python3
"""Complete active camera comparison against byte-preserved frozen Rust.

Build and execution belong to the parent render guard. Runtime inputs are native
ATATTR01/ATGRPH01/ATCAM001; original collections/graphs/shakes are oracle and
conversion inputs only. All camera numeric owners, private state, callback order,
full active graph schedule, output and failure side effects are observed.
"""
import argparse
from collections import Counter, defaultdict
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import shutil
import struct
import subprocess

import camera_probe_schema as schema
import camera_reference_build as reference
from check_graph_parity import attribute, element, original_graph
from check_gesture_parity import converter, PLUGIN
from session_parity import REFERENCE_REVISION, digest

CODE = PLUGIN / 'Source/AtelierSkate/Private/Native'
UNITS = ('NativeMath', 'RigidBody', 'Geometry', 'GeometrySweep', 'WorldGeometry',
         'NameId', 'Settings', 'StockSettingsReader', 'Graph', 'GraphController',
         'CompiledGraph', 'GraphConditions', 'GraphGestureOperations',
         'AnimationName', 'Intents', 'CameraTracking', 'CameraSubject',
         'CameraShots', 'CameraWorld', 'CameraEffects', 'CameraRig',
         'CameraManager', 'CameraSettings', 'CameraGraphOperations', 'CameraRuntime')
COLLECTION = 'private/stock/skater-collections.json'
GRAPH = 'private/stock/data/script/camera/Default_cameragraph.stategraph'
SHAKES = ('private/stock/data/camera/1.shk', 'private/stock/data/camera/2.shk')
CONSTANT_FALSE = {'IsInWorldPainterRegion', 'SkaterIsUnderThreat'}
BOOLEAN = ('IsInObserverMode', 'IsWipingOut', 'IsBrokenBoneSlowMo', 'IsOffboard',
           'IsAirOffboard', 'IsInOnBoardAir', 'IsFixedInAir', 'IsPreparingToJump',
           'IsInManual', 'SkaterIsDroppingIn', 'SkaterIsMovingObject',
           'SkaterIsSkitching', 'SkaterIsPerformingFootPlant',
           'SkaterIsPerformingHandPlant', 'SkaterIsPerformingBoneless',
           'SkaterIsPerformingHippyJump', 'SkaterIsPerformingHippyHurdle',
           'SkaterIsGrinding', 'SkaterWasGrinding', 'IsPlayerSkateboardOnGround',
           'IsReentry', 'SkaterIsOnRoad', 'IsGrindLedgeLeft', 'IsGrindLedgeRight',
           'IsInWorldPainterRegion', 'SkaterIsUnderThreat', 'IsCameraInBadCollision')
NUMERIC = ('CameraSubjectSpeed', 'CameraSubjectSpeedY', 'CameraSubjectAcceleration',
           'PredictedAirTime', 'PredictedLandingHeight', 'PredictedMaxHeight',
           'PredictedHeightDistanceRatio', 'FrontsideAngle', 'TransferAngle',
           'LaunchInclineAngle', 'LandingInclineAngle', 'GrindInclineAngle',
           'InclineAngle', 'InclineAngleAbs', 'TurningCentredTime', 'TurningTime',
           'TimeSinceLastPlayerInput')


class Writer:
    def __init__(self): self.data = bytearray()
    def word(self, value): self.data.extend(struct.pack('<I', int(value) & 0xffffffff))
    def float(self, value): self.data.extend(struct.pack('<f', value))
    def string(self, value):
        raw = value.encode(); self.word(len(raw)); self.data.extend(raw)


def encode(kind, value, values):
    out = Writer(); schema.encoded_value(out, kind, value, values); return bytes(out.data)


def matrix(position, heading):
    s, c = math.sin(heading), math.cos(heading)
    return [[c, 0, -s, 0], [0, 1, 0, 0], [s, 0, c, 0], list(position)]


def snapshot(tick, case, values):
    """Every completed producer field is explicit, shared bytewise by both runs."""
    result = schema.zero_value('CameraSubjectSnapshot', values)
    t = tick + case * 11; mode = (t // 53) % 3
    yaw = math.sin(t * .023) * 1.7
    position = [math.sin(t * .017) * 2.3, 1.15 + math.sin(t * .019) * .43, t * .0317, 1]
    velocity = [math.cos(t * .017) * 2.3, math.cos(t * .019) * .43, 1.902, .137]
    center = [position[0] + .09, position[1] + .67, position[2] - .13, 1]
    root = matrix(position, yaw)
    result['tick'] = tick + 1
    subject, rig = result['subject'], result['subject']['rig']
    rig.update(transform=copy.deepcopy(root), skeleton_root=copy.deepcopy(root),
               hips_position=center, last_valid_ground_up=[.137, .983, .071, 0],
               context=case % 4, pumping_acceleration=math.sin(t * .137) * 7.31,
               state_height_32=1.01 + (t % 13) * .0731, in_ground_physics=int(mode == 0),
               grinding=int(mode == 2), trajectory_valid=int(mode == 1),
               wiping_out=int(170 <= t % 233 < 205), physically_pushing=int(t % 43 < 17),
               at_pushable_speed=int(t % 37 < 29), off_board=int(t % 179 > 139),
               air_flag_452=int(t % 71 > 53), state_flag_81=int(t % 61 > 40),
               broken_bone_slowmo=int(t % 191 > 163), subject_flag_328=int(t % 101 > 97))
    subject.update(board_offset_direction=[0, 1, 0, .0317], ground_normal=[.137, .983, .071, 0],
                   launch_position=[position[0] - .7, .8, position[2] - 1.2, 1],
                   launch_normal=[-.2, .95, .13, 0],
                   landing_position=[position[0] + 1.3, .37 + math.sin(t * .13) * .31, position[2] + 3.7, 1],
                   landing_normal=[.23, .95, -.137, 0],
                   apex_position=[position[0] + .2, 3.37, position[2] + 1.7, 1],
                   direction_424=[math.sin(yaw), 0, math.cos(yaw), 0],
                   look=[math.sin(t * .19) * .731, math.cos(t * .17) * .317],
                   steering=[math.sin(t * .07) * .87, 0, .1, -.13],
                   trajectory_time=(t % 53) * .02317, trajectory_duration=1.437,
                   apex_time=.637, value_512=.13 + (t % 19) * .037,
                   value_516=.27 + (t % 23) * .041, reset=int(tick == 0 or tick % 197 == 0),
                   flag_556=int(t % 67 > 43), stance_560=(t // 29) % 2,
                   stance_592=(t // 31) % 2, flag_652=int(t % 73 > 51),
                   shake_variant=(t // 17) % 2, special_effect=int(t % 157 > 133), flag_684=int(t % 79 > 63))
    result['pose'].update(physical_transform=copy.deepcopy(root), skeleton_root=copy.deepcopy(root),
                          center_of_mass=center,
                          reckoned_center_of_mass=[center[0] + .317, center[1] - .131, center[2] + .271, 1],
                          wiping_out=bool(rig['wiping_out']), state_flag_75=bool(t % 113 > 99))
    result['anchors'].update(board_position=position, board_velocity=velocity,
                             board_acceleration=[math.sin(t * .21) * 3, math.cos(t * .14), math.cos(t * .19) * 5, .31],
                             board_offset_direction=[0, 1, 0, .0317], center_of_mass=center,
                             damped_center_of_mass=[99, 98, 97, 96], skeleton_root_up=root[1],
                             grind_point=[position[0] + .7, position[1] + .13, position[2] - .3, 1],
                             grinding=bool(rig['grinding']), reset=bool(subject['reset']))
    result['reference_points'].update(head=[position[0], position[1] + 1.71, position[2], 1],
                                      hips=center, left_foot=[position[0] - .17, position[1] + .09, position[2] - .31, 1],
                                      right_foot=[position[0] + .19, position[1] + .07, position[2] + .29, 1],
                                      board=position, centre_of_mass=center, damped_centre_of_mass=[96, 97, 98, 99],
                                      grind_position=result['anchors']['grind_point'], tracked_anchor=[91, 92, 93, 94],
                                      incline_normal=[89, 88, 87, 86], grinding=rig['grinding'])
    result['compass'].update(skeleton_direction=root[2], look_target=[3.7, 1.8, position[2] + 7, 1],
                             board_velocity=velocity, trajectory_direction=[.27, .137, 1.7, .03], state_103=bool(t % 47 > 33))
    for i, (name, kind) in enumerate(values['CameraGraphSubject']['fields']):
        if kind == 'bool': result['graph'][name] = (t // (5 + i)) % 2 == 1
    result['graph'].update(time_since_player_input=0 if tick % 11 < 5 else .731 + (tick % 7) * .317,
                            wipeout_tweak=(t // 13) % 5, slow_motion_air_duration=1.13 + (t % 23) * .0137)
    return result


def environment(tick, case):
    return dict(camera_type=(tick // 19 + case) % 2, on_road=tick % 29 > 13,
                ledge_left=tick % 31 > 11, ledge_right=tick % 37 > 19,
                volumes=['region.extended', 'éclair.trail'] if tick % 7 < 3 else ['other'])


def moving(tick):
    count = (0, 1, 2, 50)[(tick // 23) % 4]
    return [dict(position=[-1.3 + i * .31, .73 + i * .021, tick * .0317 - 1.7, 1],
                 velocity=[.13 * (i % 3), -.071, .317, .137], radius=.371 + (i % 4) * .131)
            for i in range(count)]


def world():
    # Floor first duplicate establishes exact first-hit tie order; ramps/walls
    # exercise source TriangleSegment and real broad-phase candidate order.
    triangles = [([[-100, 0, -100], [-100, 0, 100], [100, 0, -100]], 11),
                 ([[-100, 0, -100], [-100, 0, 100], [100, 0, -100]], 99),
                 ([[100, 0, -100], [-100, 0, 100], [100, 0, 100]], 12),
                 ([[-7, 0, -4], [7, 0, -4], [-7, 7, -4]], 21),
                 ([[7, 0, -4], [7, 7, -4], [-7, 7, -4]], 22),
                 ([[-8, 0, 20], [-8, 2, 28], [8, 0, 20]], 31),
                 ([[8, 0, 20], [-8, 2, 28], [8, 2, 28]], 32)]
    out = Writer(); out.word(len(triangles))
    for vertices, tag in triangles:
        for vertex in vertices:
            for lane in vertex: out.float(lane)
        out.float(.017)
        for value in (.8, .9, 1): out.float(value)
        out.word(0)
        for value in (.53, .37, .07): out.float(value)
        out.word(tag)
    return bytes(out.data)


def advance(tick, case, values):
    out = Writer(); out.word(0); out.float((.00317, 1/60, .03125, .137)[(tick + case) % 4])
    out.data.extend(encode('CameraSubjectSnapshot', snapshot(tick, case, values), values))
    out.data.extend(encode('[f32;4]', [0, -9.81, 0, .0], values))
    out.data.extend(encode('CameraGraphEnvironment', environment(tick, case), values))
    out.data.extend(encode('Vec<PathObstacle>', moving(tick), values)); return bytes(out.data)


def choose(name, tick, case, values, force=True):
    out = Writer(); out.word(3); out.string(name); out.word(force)
    out.data.extend(encode('ManagerSubject', snapshot(tick, case, values)['subject'], values)); return bytes(out.data)


def condition_row(tick, case, values):
    out = Writer(); out.word(4); record = snapshot(tick, case, values)
    for kind, value in [('ManagerSubject', record['subject']), ('CameraGraphSubject', record['graph']),
                        ('CameraGraphEnvironment', environment(tick, case))]: out.data.extend(encode(kind, value, values))
    return bytes(out.data)


def operation(kind, value=None):
    out = Writer(); out.word(kind)
    if value is not None: out.float(value)
    return bytes(out.data)


def word_tests():
    rows = []
    for count in (0, 1, 3, 8, 16, 20, 32):
        for name in (f'raw{count}', f'text{count}', f'bad{count}', f'wide{count}'):
            out = Writer(); out.word(7)
            for text in ('camera_word_fixture', 'derived', name): out.string(text)
            out.word(count); rows.append(bytes(out.data))
    for category, key, name, count in [('camera_word_fixture', 'derived', 'alias', 3),
                                     ('camera_word_fixture', 'derived', 'missing', 1),
                                     ('camera_word_fixture', 'absent', 'raw1', 1),
                                     ('absent', 'derived', 'raw1', 1),
                                     ('camera_word_fixture', 'cycle-a', 'missing', 1)]:
        out = Writer(); out.word(7)
        for text in (category, key, name): out.string(text)
        out.word(count); rows.append(bytes(out.data))
    return rows


def add_word_records(collections):
    fields = {}
    for count in (0, 1, 3, 8, 16, 20, 32):
        raw = ''.join(f'{(0x80000000 + i * 0x131731) & 0xffffffff:08x}' for i in range(count))
        fields[f'raw{count}'] = dict(type='OpaqueWords', data=raw)
        fields[f'text{count}'] = dict(type='EA::Reflection::Text', data='\u2003' + '\u00a0'.join(raw[i:i+8] for i in range(0, len(raw), 8)) + '\u2029')
        fields[f'bad{count}'] = dict(type='EA::Reflection::Text', data=raw[:-1] + 'G' if count else 'G')
        fields[f'wide{count}'] = dict(type='EA::Reflection::Text', data=raw[:-1] + 'é' if count else 'é')
    fields[f'Hash_{converter.name_id("alias"):016X}'] = dict(type='EA::Reflection::Text', data='00000001 80000000 7fc00123')
    for key, parent, values in [('base', '', fields), ('derived', 'base', {}), ('cycle-a', 'cycle-b', {}), ('cycle-b', 'cycle-a', {})]:
        collections['collections'].append({'class': 'camera_word_fixture', 'key': key, 'parent': parent,
                                            'fields': values, 'source': 'camera-parity-fixture', 'sha256': ''})


def conditions_graph():
    nodes, names = [], []
    for name in BOOLEAN:
        nodes.append(element('condition', name, [attribute('mask', 'always')])); names.append(name)
    for name in NUMERIC:
        for style in ('Equal', 'NotEqual', 'LessThan', 'GreaterThan', 'LessEqual', 'GreaterEqual'):
            nodes.append(element('condition', name, [attribute('mask', 'always'), attribute('comparison', style), attribute('value', bits=0)])); names.append(name)
    for name, attributes in [('IsCameraTypeActive', [attribute('type', '+1')]),
                              ('IsPreviousShot', [attribute('shot1', 'low'), attribute('shot2', 'high'), attribute('shot4', 'ignored')]),
                              ('IsWipeoutBodyTweak', [attribute('tweak', 'JudoKick')]),
                              ('IsInVolume', [attribute('volume', 'éclair')])]:
        nodes.append(element('condition', name, [attribute('mask', 'always'), *attributes])); names.append(name)
    return element('state', 'root', children=[element('behaviour', 'CameraChooseShot', [attribute('shot1', 'low')]),
                                               element('expression', attributes=[attribute('op', 'or')], children=nodes)]), names


def transition_graph():
    states = []
    for name, style, shot in [('a', 'Equal', 'low'), ('b', 'NotEqual', 'high')]:
        states.append(element('state', name, [attribute('interruptable', 'root')], [
            element('expression', attributes=[attribute('op', 'and')], children=[element('condition', 'TimeSinceLastPlayerInput', [attribute('mask', 'always'), attribute('comparison', style), attribute('value', bits=0)])]),
            element('behaviour', 'CameraChooseShot', [attribute('shot1', shot), attribute('transitionIn', bits=struct.unpack('<I', struct.pack('<f', .317))[0]), attribute('transitionOut', bits=struct.unpack('<I', struct.pack('<f', .731))[0])]),
            element('behaviour', 'PrintText2D', [attribute('text', 'enter-' + name)]),
            element('behaviour', 'SlowMotionController')]))
    return element('state', 'root', children=[element('behaviour', 'PrintText2D', [attribute('text', 'root')]), *states])


def synthetic_shots(collections):
    low = next(r for r in collections['collections'] if r['class'] == 'camera_shots' and r['key'] == 'low')
    def field(kind, value): return dict(type=kind, data=value)
    def f(value): return struct.pack('>f', value).hex()
    def w(value): return f'{value:08x}'
    def ref(name): return f'f27dd93e059ef6cb{converter.name_hash(name) if name else 0:016x}0000000000000000'
    names = []
    for kind in range(24):
        name = f'camera_fixture_blend_{kind}'; record = copy.deepcopy(low); record['key'] = name
        a = record['fields']; a['CollectionName']['data'] = name
        for key, value in [('ShotType', 1), ('BlendType', kind), ('TransitionTimeUnits', kind % 3)]: a[key]['data'] = w(value)
        for key, value in [('BlendPoint1', -.731), ('BlendPoint2', .317), ('BlendPoint3', 1.731), ('BlendValue', .137), ('SmoothingBlendValue', .317), ('TransitionTime', .271)]: a[key]['data'] = f(value)
        for i, child in enumerate(('low', 'high', 'low'), 1): a[f'BlendShot{i}']['data'] = ref(child)
        collections['collections'].append(record); names.append(name)
    for name, children, points in [('camera_fixture_gap', ('low', None, 'high'), (0, 1, 2)),
                                    ('camera_fixture_tie', ('low', 'high', 'low'), (0, 0, 1)),
                                    ('camera_fixture_previous', (None, None, None), (0, 0, 0)),
                                    ('camera_fixture_cycle', ('camera_fixture_cycle', None, None), (0, 1, 2))]:
        record = copy.deepcopy(low); record['key'] = name; a = record['fields']; a['CollectionName']['data'] = name
        a['ShotType']['data'] = w(0 if name.endswith('previous') else 1)
        a['OptionUsePreviousShot']['data'] = '01' if name.endswith('previous') else '00'
        for i, child in enumerate(children, 1): a[f'BlendShot{i}']['data'] = ref(child)
        for i, point in enumerate(points, 1): a[f'BlendPoint{i}']['data'] = f(point)
        collections['collections'].append(record)
        if not name.endswith('cycle'): names.append(name)
    return names


def make_cases(values, stock_names):
    cases = []
    for case in range(8):
        rows = []
        for tick in range(384):
            if tick % 79 == 0: rows.append(operation(1, (16/9, 4/3, 2.35, 1)[(tick // 79 + case) % 4]))
            if tick % 41 == 0: rows.append(operation(2))
            rows.append(advance(tick, case, values))
        # Both outer runtime nonmonotonic errors precede all mutation.
        rows.extend([advance(383, case, values), advance(0, case, values)])
        cases.append(dict(name=f'stock-schedule-{case}', graph=None, rows=rows, bank='stock'))
    rows = [advance(0, 0, values)]; tick = 1
    for name in stock_names:
        rows.append(choose(name.upper(), tick, 0, values))
        for _ in range(6): rows.append(advance(tick, 0, values)); tick += 1
        rows.append(choose(name, tick, 0, values, False))
    rows.append(choose('missing-stock-shot', tick, 0, values))
    cases.append(dict(name='every-stock-shot', graph=element('state', 'root', children=[element('behaviour', 'CameraChooseShot', [attribute('shot1', 'low')])]), rows=rows, bank='stock'))
    graph, names = conditions_graph(); rows = []
    for tick in range(384): rows.extend([advance(tick, 2, values), condition_row(tick, 2, values)])
    cases.append(dict(name='all-condition-factories', graph=graph, condition_names=names, rows=rows, bank='stock'))
    cases.append(dict(name='end-begin-rate-order', graph=transition_graph(), rows=[advance(tick, 1, values) for tick in range(384)], bank='stock'))
    rows = [advance(0, 0, values)]; tick = 1
    for name in [f'camera_fixture_blend_{i}' for i in range(24)] + ['camera_fixture_gap', 'camera_fixture_tie', 'camera_fixture_previous']:
        rows.append(choose(name, tick, 3, values))
        for _ in range(29): rows.append(advance(tick, 3, values)); tick += 1
    rows.extend([choose('camera_fixture_cycle', tick, 3, values), choose('low', tick, 3, values), advance(tick, 3, values)])
    cases.append(dict(name='all-blends-and-partial-cycle', graph=element('state', 'root', children=[element('behaviour', 'CameraChooseShot', [attribute('shot1', 'low')])]), rows=rows, bank='synthetic'))
    rows = word_tests()
    for index in range(16):
        line = dict(start=[-.3 + index * .017, 3 + index * .131, -.7, 1], end=[-.3, -2, -.7, 1], radius=(0, .071, .317, .731)[index % 4])
        out = Writer(); out.word(5); out.data.extend(encode('FatLine', line, values)); rows.append(bytes(out.data))
        query = dict(position=[.3, 2 + index * .0731, .7, 1], velocity=[.13, .731 + index * .137, .317, 0], gravity=[0, -9.81, 0, 0], duration=.637 + index * .137, radius=.137 + index * .017, start_error=.0137, end_error=.0271)
        out = Writer(); out.word(6); out.data.extend(encode('TrajectoryQuery', query, values)); rows.append(bytes(out.data))
    for index in range(4):
        out = Writer(); out.word(5)
        out.data.extend(encode('FatLine', dict(start=[1000, 100, 1000, 1], end=[1000, 101 + index, 1000, 1], radius=.137), values)); rows.append(bytes(out.data))
    for radius in (-.137, float('nan')):
        out = Writer(); out.word(5)
        out.data.extend(encode('FatLine', dict(start=[0, 2, 0, 1], end=[0, -2, 0, 1], radius=radius), values)); rows.append(bytes(out.data))
    cases.append(dict(name='real-world-and-word-reader', graph=element('state', 'root'), rows=rows, bank='stock'))
    cases.append(dict(name='missing-selection-partial-publication', graph=element('state', 'root'), rows=[advance(0, 0, values)], bank='stock'))
    cases.append(dict(name='last-graph-error-partial-controller', graph=element('state', 'root', children=[element('behaviour', 'CameraChooseShot', [attribute('shot1', 'missing-first')]), element('behaviour', 'SlowMotionController'), element('behaviour', 'CameraChooseShot', [attribute('shot1', 'missing-last')])]), rows=[advance(0, 0, values)], bank='stock'))
    cases.append(dict(name='nonfinite-frame-failure', graph=element('state', 'root', children=[element('behaviour', 'CameraChooseShot', [attribute('shot1', 'low')])]), rows=[advance(0, 0, values), operation(1, float('nan')), advance(1, 0, values)], bank='stock'))
    failures = [('unknown-behavior', element('state', 'root', children=[element('behaviour', 'CameraUnknown')])),
                ('raw-case-behavior', element('state', 'root', children=[element('behaviour', ' camerachooseshot ')])),
                ('empty-choose', element('state', 'root', children=[element('behaviour', 'CameraChooseShot')])),
                ('missing-type', element('state', 'root', children=[element('expression', children=[element('condition', 'IsCameraTypeActive')])])),
                ('invalid-type', element('state', 'root', children=[element('expression', children=[element('condition', 'IsCameraTypeActive', [attribute('type', '4294967296')])])])),
                ('missing-volume', element('state', 'root', children=[element('expression', children=[element('condition', 'IsInVolume')])])),
                ('unknown-condition', element('state', 'root', children=[element('expression', children=[element('condition', 'isOffboard')])])),
                ('transition-hook', element('state', 'root', children=[element('transition', attributes=[attribute('target', 'root')], children=[element('hook', 'CameraHook')])]))]
    for name, graph in failures: cases.append(dict(name=name, graph=graph, rows=[], bank='stock', failure=True))
    for name, setting in [('slow-word-arity', ('slowmotion_controller', 'default', 'timescale', '00000000' * 31)),
                          ('angle-nonfinite', ('camera_tracker', 'heading', 'SpeedClamp', '7fc00123')),
                          ('curve-nonfinite', ('camera_lag_profile', 'push', 'Curve', '00000000' * 15 + '7fc00123'))]:
        cases.append(dict(name=name, graph=element('state', 'root'), rows=[], bank='stock', failure=True, setting=setting))
    return cases


class Reader:
    def __init__(self, data, values, label_at=None):
        self.data, self.values, self.at, self.labels, self.label_at = data, values, 0, [], label_at
    def label(self, path):
        if self.label_at is not None and self.at <= self.label_at: self.labels[:] = [(self.at, path)]
    def word(self, path):
        assert self.at + 4 <= len(self.data), (path, self.at)
        self.label(path); result = struct.unpack_from('<I', self.data, self.at)[0]; self.at += 4; return result
    def string(self, path):
        size = self.word(path + '.length'); assert size <= len(self.data) - self.at
        self.label(path); result = self.data[self.at:self.at+size].decode(); self.at += size; return result
    def value(self, kind, path):
        if '::' in kind: kind = kind.rsplit('::', 1)[-1]
        if kind in ('f32', 'u32', 'u8', 'i32', 'usize', 'bool'): return self.word(path)
        if kind == 'u64': return self.word(path + '.low') | (self.word(path + '.high') << 32)
        if kind == 'String': return self.string(path)
        if kind.startswith('['):
            child, count = re.fullmatch(r'\[(.+);(\d+)\]', kind).groups(); return [self.value(child, f'{path}[{i}]') for i in range(int(count))]
        if kind.startswith('Option<'):
            present = self.word(path + '.present'); assert present <= 1, (path, present)
            return self.value(kind[7:-1], path) if present else None
        if kind.startswith('Vec<'): return [self.value(kind[4:-1], f'{path}[{i}]') for i in range(self.word(path + '.count'))]
        if kind.startswith('PointGraph<'):
            count = kind[len('PointGraph<'):-1]; return dict(x=self.value(f'[f32;{count}]', path + '.x'), y=self.value(f'[f32;{count}]', path + '.y'))
        if kind == 'Basis3': return dict(columns=self.value('[[f32;3];3]', path + '.columns'))
        if kind.startswith('('):
            child = kind[1:-1]; depth = 0
            for i, c in enumerate(child):
                if c in '[<(': depth += 1
                elif c in ']> )'.replace(' ', ''): depth -= 1
                elif c == ',' and not depth: return [self.value(child[:i], path + '.0'), self.value(child[i+1:], path + '.1')]
            raise AssertionError(kind)
        return {field: self.value(field_kind, path + '.' + field) for field, field_kind in self.values[kind]['fields']}
    def status(self, path):
        okay = self.word(path); assert okay <= 1
        return (bool(okay), None if okay else self.string(path + '.error'))
    def runtime(self, path):
        out = {'manager': self.value('CameraMan', path + '.manager'), 'subject': self.value('SubjectPublisher', path + '.subject')}
        out['controller'] = dict(dt=self.value('f32', path + '.controller.dt'), current=self.value('Option<usize>', path + '.controller.current'), last=self.value('Option<usize>', path + '.controller.last'), state_times=self.value('Vec<Option<f32>>', path + '.controller.state_times'))
        out['active'] = [dict(behavior=self.word(path + '.active.behavior'), instance=self.word(path + '.active.instance')) for _ in range(self.word(path + '.active.count'))]
        for key, kind in [('slow', 'Vec<Option<SlowMotionController>>'), ('trajectories', '[TrajectoryResult;3]'), ('frame', 'Option<CameraFrame>'), ('latest', 'Option<CameraSubjectSnapshot>'), ('rates', 'Vec<SimulationRateRequest>'), ('messages', 'Vec<String>')]: out[key] = self.value(kind, path + '.' + key)
        return out


def decode(data, cases, values, label_at=None):
    reader = Reader(data, values, label_at); count = reader.word('cases'); assert count == len(cases)
    decoded = []
    for i, case in enumerate(cases):
        path = f'case[{i}].{case["name"]}'; assert reader.word(path + '.id') == i
        rows = reader.word(path + '.rows'); assert rows == len(case['rows']); okay, error = reader.status(path + '.load')
        item = dict(name=case['name'], loaded=okay, error=error, rows=[])
        if not okay: assert not rows; decoded.append(item); continue
        for name in ('ManagerSettings', 'CompassSettings', 'SlowMotionSettings'): item[name] = reader.value(name, path + '.' + name)
        item['shots'] = {}
        for _ in range(reader.word(path + '.shots.count')):
            key = reader.string(path + '.shots.key'); item['shots'][key] = reader.value('ShotDefinition', path + '.shots.' + key)
        item['shakes'] = reader.value('[ShakeSamples;2]', path + '.shakes'); item['initial'] = reader.runtime(path + '.initial')
        for index, raw in enumerate(case['rows']):
            rowpath = f'{path}.row[{index}]'; operation_id = reader.word(rowpath + '.operation'); assert operation_id == struct.unpack_from('<I', raw)[0]
            okay, error = reader.status(rowpath + '.status'); row = dict(operation=operation_id, okay=okay, error=error)
            if okay and operation_id in (0, 3, 4, 5, 6, 7): row['result'] = reader.value({0:'CameraFrame', 3:'bool', 4:'Vec<bool>', 5:'FatLineResult', 6:'f32', 7:'Vec<u32>'}[operation_id], rowpath + '.result')
            row['moving'] = [dict(position=reader.value('[f32;4]', rowpath + '.moving.position'), velocity=reader.value('[f32;4]', rowpath + '.moving.velocity'), radius=reader.value('f32', rowpath + '.moving.radius'), count=reader.word(rowpath + '.moving.count')) for _ in range(reader.word(rowpath + '.moving.calls'))]
            row['state'] = reader.runtime(rowpath + '.state'); item['rows'].append(row)
        decoded.append(item)
    assert reader.at == len(data), (reader.at, len(data)); return decoded, reader.labels


def coverage(decoded, cases):
    counters = Counter(); modes, frames, mirror, shakes, positioner, drops, selected = set(), set(), set(), set(), set(), set(), set()
    conditions = defaultdict(set); all_rates, obstacles = set(), set(); errors = []
    for item, case in zip(decoded, cases):
        assert item['loaded'] != case.get('failure', False), (case['name'], item['error'])
        if not item['loaded']: counters['factory_errors'] += 1; errors.append(item['error']); continue
        prior = item['initial']
        for row in item['rows']:
            counters[f'operation_{row["operation"]}'] += 1
            state = row['state']; manager = state['manager']; rig = manager['rig']; shot = manager['shots']['current']['definition']['name']; selected.add(shot)
            modes.add(rig['fields']['height_mode']); mirror.add(manager['state']['heading_mirror']['position'])
            positioner.add(tuple(manager['rig']['positioner']['position'])); drops.add(json.dumps(manager['drop']['pending'], sort_keys=True))
            shakes.add(tuple(manager['shake'][0]['translation']))
            for call in row['moving']: obstacles.add(call['count'])
            for rate in state['rates']: all_rates.add((rate['timestep'], rate['ticks']))
            if row['okay'] and row['operation'] == 0:
                frame = row['result']; frames.add(tuple(frame['position'])); counters['successful_frames'] += 1
                for word in (*frame['position'], *[lane for column in frame['basis']['columns'] for lane in column], frame['field_of_view_degrees']): assert math.isfinite(struct.unpack('<f', struct.pack('<I', word))[0])
            if not row['okay']:
                errors.append(row['error']); counters['operation_errors'] += 1
                if 'non-monotonic subject tick' in row['error']: assert state == prior; counters['unchanged_nonmonotonic'] += 1
            if row['operation'] == 4:
                assert row['okay']; assert len(row['result']) == len(case['condition_names'])
                for name, result in zip(case['condition_names'], row['result']): conditions[name].add(result)
            if row['operation'] == 5 and row['okay']: counters['world_hits' if row['result']['hit'] else 'world_misses'] += 1
            if row['operation'] == 7: counters['word_success' if row['okay'] else 'word_failure'] += 1
            prior = state
    # Meaningful complete-runtime excitation; no tolerance and no neutral fixtures.
    assert counters['successful_frames'] > 4000, counters
    assert modes == {0, 1, 2}, modes
    assert len(frames) > 1000 and len(positioner) > 1000, (len(frames), len(positioner))
    assert len(mirror) > 16 and len(shakes) > 32, (len(mirror), len(shakes))
    assert obstacles == {0, 1, 2, 50}, obstacles
    assert len(drops) > 5, len(drops)
    assert counters['unchanged_nonmonotonic'] == 16, counters
    assert counters['factory_errors'] == 11 and counters['word_success'] >= 15 and counters['word_failure'] >= 15, counters
    assert counters['world_hits'] > 8 and counters['world_misses'] == 4, counters
    queries = next(item for item in decoded if item['name'] == 'real-world-and-word-reader')['rows']
    assert next(row['result']['surface'] for row in queries if row['operation'] == 5 and row['okay'] and row['result']['hit']) == 11, 'first authored equal-distance triangle must win'
    assert [row['error'] for row in queries if row['operation'] == 5 and not row['okay']] == ['Invalid stock camera collision radius'] * 2
    stock = set(decoded[8]['shots']); assert stock <= {name.lower() for name in selected}, sorted(stock - selected)
    assert {f'camera_fixture_blend_{i}' for i in range(24)} <= selected
    assert len(conditions) == 48, len(conditions)
    for name in CONSTANT_FALSE: assert conditions[name] == {0}, (name, conditions[name])
    for name in set(BOOLEAN) - CONSTANT_FALSE - {'IsCameraInBadCollision', 'IsReentry'}: assert conditions[name] == {0, 1}, (name, conditions[name])
    for name in NUMERIC: assert conditions[name] == {0, 1}, (name, conditions[name])
    for name in ('IsCameraTypeActive', 'IsWipeoutBodyTweak', 'IsInVolume'): assert conditions[name] == {0, 1}, (name, conditions[name])
    order = next(item for item in decoded if item['name'] == 'end-begin-rate-order')
    assert len(order['rows'][-1]['state']['messages']) > 30
    # Controller::update exits, enters, then updates the active behavior. Inspect
    # this operation's new requests; a transition emits End, Begin, Update.
    previous_rates = order['initial']['rates']; begin_rate = None; rate_transitions = 0
    for index, row in enumerate(order['rows']):
        rates = row['state']['rates']; assert rates[:len(previous_rates)] == previous_rates
        new_rates = rates[len(previous_rates):]
        ticks = [rate['ticks'] for rate in new_rates]
        if index == 0:
            assert ticks == [1, 1], (index, new_rates)
            begin_rate = new_rates[0]
        elif 0 in ticks:
            assert ticks == [0, 1, 1], (index, new_rates)
            assert new_rates[0] == {'timestep': 0x3c888889, 'ticks': 0}, (index, new_rates)
            assert new_rates[1] == begin_rate, (index, new_rates)
            rate_transitions += 1
        else:
            assert ticks == [1], (index, new_rates)
        previous_rates = rates
    assert rate_transitions > 32, 'SlowMotion transitions must publish source-ordered End, Begin, Update requests'
    last = next(item for item in decoded if item['name'] == 'last-graph-error-partial-controller')['rows'][0]
    assert last['error'] == 'Missing stock camera shot missing-last' and any(v is not None for v in last['state']['slow']) and not last['state']['rates']
    assert any('cyclic' in (error or '').lower() for error in errors), errors
    nonfinite = next(item for item in decoded if item['name'] == 'nonfinite-frame-failure')['rows'][-1]
    assert not nonfinite['okay'] and nonfinite['error'].startswith('Normal gameplay camera produced a non-finite frame:')
    assert nonfinite['state']['latest']['tick'] == 2 and nonfinite['state']['frame'] is not None
    return dict(counters=counters, position_variants=len(frames), positioner_variants=len(positioner), mirror_variants=len(mirror), shake_variants=len(shakes), drop_pending_variants=len(drops), selected_shots=len(selected), moving_counts=sorted(obstacles), conditions={name:sorted(v) for name,v in conditions.items()}, simulation_rate_variants=len(all_rates), source_ordered_rate_transitions=rate_transitions, errors=errors)


def build_native(output, values):
    snapshot_dir = output / 'native-source'; snapshot_dir.mkdir(exist_ok=True)
    files = list(CODE.glob('*.h')) + [CODE / (name + '.cpp') for name in UNITS]
    records = {}
    for source in files:
        destination = snapshot_dir / source.name; shutil.copy2(source, destination); records[source.name] = digest(source); assert digest(destination) == records[source.name]
    template = PLUGIN / 'Tests/Native/camera_runtime_probe.cpp'; raw = template.read_text()
    assert raw.count('// @CPP_OBSERVERS@') == 1
    observer = schema.cpp_observers(values).replace('// @CPP_GENERIC_WRITERS@', schema.CPP_GENERIC_WRITERS)
    generated = snapshot_dir / 'camera_runtime_probe.cpp'; generated.write_text(raw.replace('// @CPP_OBSERVERS@', observer))
    records[generated.name] = digest(generated)
    binary = output / 'camera-runtime-native'
    command = ['clang++', '-std=c++17', '-O2', '-fno-exceptions', '-ffp-contract=off', '-Wall', '-Wextra', '-Werror', '-I', str(snapshot_dir), *[str(snapshot_dir / (name + '.cpp')) for name in UNITS], str(generated), '-o', str(binary)]
    (output / 'native-source-provenance.json').write_text(json.dumps(dict(source_sha256=records, template_sha256=digest(template), compile_flags=command[1:9]), indent=2) + '\n')
    subprocess.run(command, check=True)
    for name, sha in records.items(): assert digest(snapshot_dir / name) == sha
    return binary


def prepare_fixtures(assets, output, data_probe, values):
    fixtures = output / 'fixtures'; fixtures.mkdir(exist_ok=True)
    stock = json.loads((assets / COLLECTION).read_text()); add_word_records(stock)
    synthetic = copy.deepcopy(stock); synthetic_shots(synthetic)
    decoded_packages, packages = {}, {}
    for name, collections in [('stock', stock), ('synthetic', synthetic)]:
        folder = output / (name + '-bank'); (folder / 'private/stock/data/camera').mkdir(parents=True, exist_ok=True)
        (folder / COLLECTION).write_text(json.dumps(collections))
        for relative in SHAKES: shutil.copy2(assets / relative, folder / relative)
        base = output / (name + '-decoded'); identity = 'camera-' + name + ':' + hashlib.sha256((folder / COLLECTION).read_bytes()).hexdigest()
        subprocess.run([str(data_probe), str(folder), str(base), identity], check=True)
        spec = importlib.util.spec_from_file_location('camera_conversion', PLUGIN / 'Tools/convert_camera_data.py'); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        decoded = json.loads(base.with_suffix('.json').read_text()); package = module.pack_camera(decoded)
        assert package == base.with_suffix('.raw').read_bytes()
        packages[name] = package; decoded_packages[name] = decoded
    cases = make_cases(values, [d['name'] for d in decoded_packages['stock']['shots']])
    manifests = []
    for case_id, case in enumerate(cases):
        folder = fixtures / f'case-{case_id}'; (folder / 'private/stock/data/script/camera').mkdir(parents=True, exist_ok=True); (folder / 'private/stock/data/camera').mkdir(parents=True, exist_ok=True)
        collections = copy.deepcopy(stock if case['bank'] == 'stock' else synthetic)
        if 'setting' in case:
            category, key, name, raw = case['setting']
            record = next(r for r in collections['collections'] if r['class'] == category and r['key'] == key)
            record['fields'][name]['data'] = raw
        (folder / COLLECTION).write_text(json.dumps(collections))
        for relative in SHAKES: shutil.copy2(assets / relative, folder / relative)
        graph_path = folder / GRAPH
        if case['graph'] is None: shutil.copy2(assets / GRAPH, graph_path)
        else: graph_path.write_bytes(original_graph(case['graph']))
        (folder / 'settings.native').write_bytes(converter.encode_settings(folder / COLLECTION))
        (folder / 'graph.native').write_bytes(converter.encode_graph(converter.read_graph(graph_path)))
        (folder / 'camera.native').write_bytes(packages[case['bank']])
        manifests.append(dict(case=case_id, name=case['name'], rows=len(case['rows']), bank=case['bank'], original_graph_sha256=digest(graph_path), native_graph_sha256=digest(folder / 'graph.native'), original_settings_sha256=digest(folder / COLLECTION), native_settings_sha256=digest(folder / 'settings.native'), camera_sha256=digest(folder / 'camera.native')))
    out = Writer(); out.word(len(cases))
    for i, case in enumerate(cases):
        out.word(i); out.data.extend(world()); out.word(len(case['rows']))
        for row in case['rows']: out.data.extend(row)
    (output / 'fixture-manifest.json').write_text(json.dumps(manifests, indent=2) + '\n')
    (output / 'input.bin').write_bytes(out.data)
    return fixtures, cases, packages, bytes(out.data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--target-dir', type=Path, required=True); args = parser.parse_args()
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    data_probe = reference.build_data_probe(output, args.target_dir / 'export')
    rust, values = reference.build_runtime_probe(output, args.target_dir / 'runtime')
    native = build_native(output, values)
    fixtures, cases, packages, corpus = prepare_fixtures(args.assets.resolve(), output, data_probe, values)
    for name, package in packages.items():
        path = output / (name + '.camera'); path.write_bytes(package)
        assert subprocess.check_output([str(native), '--dump', str(path)]) == package
    expected = subprocess.check_output([str(rust), str(fixtures)], input=corpus); (output / 'reference.bin').write_bytes(expected)
    actual = subprocess.check_output([str(native), str(fixtures)], input=corpus); (output / 'native.bin').write_bytes(actual)
    difference_at = next((i for i,(a,b) in enumerate(zip(actual,expected)) if a != b), min(len(actual),len(expected))) if actual != expected else None
    decoded, labels = decode(expected, cases, values, difference_at)
    if actual != expected:
        at = difference_at
        field = next((path for offset,path in reversed(labels) if offset <= at), 'end-of-stream')
        failure = dict(byte=at, field=field, reference_bytes=len(expected), native_bytes=len(actual), reference_hex=expected[max(0,at-16):at+32].hex(), native_hex=actual[max(0,at-16):at+32].hex())
        (output / 'first-divergence.json').write_text(json.dumps(failure, indent=2) + '\n'); raise AssertionError(failure)
    proof = coverage(decoded, cases)
    malformed = []
    valid = packages['stock']
    for i, raw in enumerate((b'', valid[:7], valid[:19], valid[:-1], valid+b'\0', b'BADxxxxx'+valid[8:])):
        path = output / f'invalid-native-{i}.camera'; path.write_bytes(raw)
        run = subprocess.run([str(native), '--dump', str(path)], capture_output=True)
        assert run.returncode == 2 and not run.stdout, (i, run.returncode); malformed.append(run.stderr.decode().strip())
    report = dict(passed=True, comparison='Exact complete active camera outputs, settings, all stock shot fields/centered samples, every clock/owner/private state, original graph callback order, moving-obstacle callbacks, real world queries and failure side effects', reference_revision=REFERENCE_REVISION, cases=len(cases), operations=sum(len(c['rows']) for c in cases), bytes=len(expected), sha256=hashlib.sha256(expected).hexdigest(), input_sha256=hashlib.sha256(corpus).hexdigest(), schema_types=len(values), schema_fields=sum(len(v['fields']) for v in values.values()), stock_shots=len(decoded[8]['shots']), coverage=proof, malformed_native_package_errors=malformed, boundary='Runtime native ATATTR01/ATGRPH01/ATCAM001 only. Complete original source prefixes and appended observation-only implementations are hashed in reference-provenance.json; immutable native snapshot is hashed separately. No numerical method or executed callback is replaced. Completed physical/animation subject records, authored world region membership, query gravity and moving obstacle list remain explicit live producer inputs. Root simulation scheduling and Unreal camera presentation are not claimed by this isolated comparison. Native rejection of invalid/nonadvancing trajectory steps, invalid angle conversion and out-of-capacity anchor/compass indexes is outside original valid domain; hanging/panicking original cases are excluded from parity claims.')
    (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n'); print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__': main()
