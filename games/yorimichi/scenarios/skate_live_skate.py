"""In-game helpers for skate tests and films (run through the live bridge: atelier live py - < this file).

Adds to the `live` module:
  live.park.ue(x, y, z)            park-local metres -> UE cm
  live.park.place(x, y, heading)   on the board, stopped, heading in degrees counter-clockwise from east
  live.park.launch(speed, heading) give the board a speed
  live.park.look(pitch, yaw)       point the camera (yaw in park degrees)
  live.scenario(x, y, heading, speed, events, duration, pitch, cam)
                                   events: (time, inputs) or (time, ('flick', name, left, load)); records every frame
  live.result()                    mode runs and the last state; live.REC holds every frame's state
"""
import json, math, os
import unreal

_park = json.load(open(os.path.join(live.ROOT, 'games/yorimichi/world/regions/skatepark/park.json')))
_OX, _OY, _OZ = _park['origin']


class _Park:
    @staticmethod
    def ue(lx, ly, lz=0.0):
        return unreal.Vector((_OX + lx) * 100, -(_OY + ly) * 100, (_OZ + lz) * 100)

    @staticmethod
    def place(lx, ly, heading=0.0):
        live.skate_place(live.L.ground_at(_Park.ue(lx, ly, 3.0)), -heading)

    @staticmethod
    def launch(speed, heading=0.0):
        h = math.radians(heading)
        live.L.skate_launch(unreal.Vector(speed * math.cos(h), -speed * math.sin(h), 0))

    @staticmethod
    def look(pitch, yaw):
        pc = unreal.GameplayStatics.get_player_controller(live.L.game_world(), 0)
        pc.set_control_rotation(unreal.Rotator(0, pitch, -yaw))   # unreal.Rotator(roll, pitch, yaw)


live.park = _Park


def scenario(lx, ly, heading, speed, events, duration=4.0, pitch=-12, cam=None, height=0.0, velocity_heading=None):
    live.park.place(lx, ly, heading); live.park.look(pitch, heading if cam is None else cam)
    if height:
        ground = live.L.ground_at(live.park.ue(lx, ly, 3.0))
        live.skate_place(ground + unreal.Vector(0, 0, height * 100), -heading)
    live.park.launch(speed, heading if velocity_heading is None else velocity_heading)
    expanded = []
    for when, what in events:
        if isinstance(what, tuple) and what[0] == 'flick':
            pts = live.FLICKS[what[1]]; left = what[2] if len(what) > 2 else (0, 0); load = what[3] if len(what) > 3 else .16
            expanded.append((when, {'right': pts[0], 'left': left}))
            t = when + load
            for p in pts[1:]:
                expanded.append((t, {'right': p, 'left': left})); t += .03
            expanded.append((t, {'right': (0, 0), 'left': left}))
        else:
            expanded.append((when, what))
    expanded.sort(key=lambda e: e[0])
    steps = []
    if expanded and expanded[0][0] > 0: steps.append((expanded[0][0], {}))
    for i, (when, what) in enumerate(expanded):
        nxt = expanded[i + 1][0] if i + 1 < len(expanded) else duration
        steps.append((max(0.0, nxt - when), what))
    if not steps: steps = [(duration, {})]
    live.REC = []
    live.behave('rec', lambda dt: live.REC.append(live.L.skate_state()))
    live.skate_script(steps)


def result():
    live.stop('rec')
    modes = ''.join(s.split('mode=')[1][0] for s in live.REC)
    runs, prev, count = [], None, 0
    for m in modes:
        if m == prev: count += 1
        else:
            if prev is not None: runs.append(f'{prev}x{count}')
            prev, count = m, 1
    if prev is not None: runs.append(f'{prev}x{count}')
    return ' '.join(runs) + ' | ' + (live.REC[-1].split(' | ', 1)[1] if live.REC else '')


live.scenario = scenario
live.result = result
