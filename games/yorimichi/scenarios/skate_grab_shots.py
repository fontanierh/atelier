#!/usr/bin/env python3
"""Grab close-ups per rider: each trigger's grab with the right stick neutral and pushed four ways, frozen in the air.

Run against a running game (atelier play yorimichi):  atelier qa yorimichi skate_grab_shots [--riders Cairo,Nox,Modori]

The right stick picks the grab's variant (TweakX/TweakY in the simulation's ProduceTrick; README: the right trigger with
the stick held left is a tuck knee); --stick left holds the left stick instead (in the air it turns the body).
For each rider (switched in place) and each grab it airs out of the pier quarter (east_return at 9.5 m/s), holds the
trigger and stick from .08 s into the air, and .35 s into the grab stops time and records, in the deck's own frame
(world cm; x along the deck to the nose, y across, z up from the deck's top at its centre; SM_SkateDeck's origin):
- each leg's centre line (thigh_ hip joint, shin_ knee, foot_ ankle) and its lowest point over the deck's outline,
  against the deck's top there (the concave and the kicks, as SkateRetarget.cpp models them);
- each hand: wrist (hand_), middle knuckle (finger_1), middle finger's last joint (finger_end_1), thumb (thumb_end),
  the nearest point of the deck's edge to the knuckle (straight rails, round ends: the retarget's own grip target),
  how far the knuckle is from it, where the finger end sits against the edge and the slab, the palm's and the fingers'
  directions against the edge's, and how straight the arm is (1.0 is fully stretched: the arm cannot reach).
Bone joints are inside the skin: a knee's joint a few cm above the deck already shows the skin through it.
Then a side and a front close-up through a review camera (the board camera ignores a moved camera component).
Writes build/yorimichi/skateqa/grabs/<rider>-<grab>-{side,front}.png and grabs.json.
"""
import argparse
import json
import math
import time

import skate as qa

QUARTER = (57, 25)     # east_return's quarter, launched east at 950 cm/s (skate_ride.QUARTER)
STICKS = {'neutral': (0, 0), 'up': (0, 1), 'down': (0, -1), 'left': (-1, 0), 'right': (1, 0)}
HOLD = .35             # seconds into the grab when time stops
BONES = ('pelvis', 'thigh_L', 'thigh_R', 'shin_L', 'shin_R', 'foot_L', 'foot_R', 'toe_L', 'toe_R',
         'upperarm_L', 'upperarm_R', 'forearm_L', 'forearm_R', 'hand_L', 'hand_R',
         'finger_0_L', 'finger_0_R', 'finger_1_L', 'finger_1_R', 'finger_3_L', 'finger_3_R',
         'finger_tip_1_L', 'finger_tip_1_R', 'finger_end_1_L', 'finger_end_1_R', 'thumb_end_L', 'thumb_end_R')

FREEZE = r'''
live.AIR=[0.0, 0.0]; live.FROZEN=False
def grab(dt):
    if live.FROZEN: return
    air='mode=2 ' in live.skate_state()
    live.AIR[0]=live.AIR[0]+dt if air else 0.0
    live.AIR[1]=live.AIR[1]+dt if live.AIR[1] or (air and live.AIR[0]>.08) else 0.0
    if live.AIR[1] > 0: live.skate_input(**KEYS)
    if live.AIR[1] >= HOLD:
        live.FROZEN=True; live.GRABNAME=live.skate_state()
        unreal.GameplayStatics.set_global_time_dilation(live.L.game_world(), .0001)
live.behave('grab', grab)
'''
MEASURE = r'''
import json
P = live.L.player(); M = P.get_editor_property('mesh')
D = next(c for c in P.get_components_by_class(unreal.StaticMeshComponent) if c.get_name() == 'SkateDeck')
T = D.get_world_transform(); S = T.scale3d.x
box = D.get_editor_property('static_mesh').get_bounding_box()
def at(b):
    if M.get_bone_index(b) < 0: return None
    p = T.inverse_transform_location(M.get_socket_location(b)); return [round(p.x * S, 2), round(p.y * S, 2), round(p.z * S, 2)]
bones = {b: at(b) for b in BONES}
print(json.dumps(dict(bones=bones, scale=round(S, 4), deck=dict(min=[round(v * S, 2) for v in (box.min.x, box.min.y, box.min.z)],
    max=[round(v * S, 2) for v in (box.max.x, box.max.y, box.max.z)]), state=live.GRABNAME, mesh=str(M.get_skeletal_mesh_asset().get_name()))))
'''.replace('BONES', repr(BONES))


def sub(a, b): return [x - y for x, y in zip(a, b)]
def add(a, b): return [x + y for x, y in zip(a, b)]
def mul(a, k): return [x * k for x in a]
def dot(a, b): return sum(x * y for x, y in zip(a, b))
def norm(a): return math.sqrt(dot(a, a))
def unit(a): n = norm(a); return [x / n for x in a] if n > 1e-9 else [0., 0., 0.]
def cross(a, b): return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
def angle(a, b): return round(math.degrees(math.acos(max(-1., min(1., dot(unit(a), unit(b)))))), 1)


class Deck:
    """The deck's outline and top in its own frame, as SkateRetarget.cpp models it (concave .9 cm, 1.2 cm thick)."""
    CONCAVE, THICKNESS = .9, 1.2

    def __init__(self, deck, scale):
        lo, hi = deck['min'], deck['max']
        self.half_length, self.half_width = (hi[0] - lo[0]) / 2, (hi[1] - lo[1]) / 2
        self.flat = self.half_length - self.half_width
        self.kick_start = .675 * self.half_length
        self.kick_top = hi[2]; self.concave = self.CONCAVE * scale; self.thickness = self.THICKNESS * scale

    def kick(self, x):
        t = min(max((abs(x) - self.kick_start) / (self.half_length - self.kick_start), 0.), 1.)
        return t * t

    def top(self, x, y):
        """The top surface at (x, y): concave towards the rails, rising at the kicks."""
        return self.kick(x) * (self.kick_top - self.concave) + self.concave * min(1., (abs(y) / self.half_width) ** 2)

    def outside(self, x, y):
        """Distance outside the outline (negative inside): straight rails, round ends."""
        along = min(max(x, -self.flat), self.flat)
        return math.hypot(x - along, y) - self.half_width

    def edge(self, p):
        """The nearest point of the outline to p, at the rail's top, and its outward normal (retarget's grip target)."""
        along = min(max(p[0], -self.flat), self.flat)
        out = unit([p[0] - along, p[1], 0.])
        e = add([along, 0., 0.], mul(out, self.half_width))
        e[2] = self.concave + self.kick(e[0]) * (self.kick_top - self.concave)
        return e, out


def leg(bones, side, deck):
    """The leg's centre line over the deck: its lowest height above the top, where, and the knee's own."""
    hip, knee, ankle = (bones.get(f'{b}_{side}') for b in ('thigh', 'shin', 'foot'))
    if not (hip and knee and ankle):
        return None
    worst = None
    for a, b, part in ((hip, knee, 'thigh'), (knee, ankle, 'shin')):
        for i in range(21):
            p = add(a, mul(sub(b, a), i / 20))
            if deck.outside(p[0], p[1]) > 0:
                continue
            h = p[2] - deck.top(p[0], p[1])
            if worst is None or h < worst[0]:
                worst = (round(h, 1), part, round(i / 20, 2), [round(v, 1) for v in p])
    k_over = deck.outside(knee[0], knee[1]) <= 0
    return dict(knee=[round(v, 1) for v in knee], knee_over_deck=k_over,
                knee_above_top_cm=round(knee[2] - deck.top(knee[0], knee[1]), 1) if k_over else None,
                lowest_over_deck=dict(above_top_cm=worst[0], part=worst[1], at=worst[2], point=worst[3]) if worst else None,
                centre_line_through=bool(worst and -deck.thickness - 3 < worst[0] < 0))


def hand(bones, side, deck):
    wrist, knuckle, end, thumb = (bones.get(f'{b}_{side}') for b in ('hand', 'finger_1', 'finger_end_1', 'thumb_end'))
    upper, fore = bones.get(f'upperarm_{side}'), bones.get(f'forearm_{side}')
    if not (wrist and knuckle and upper and fore):
        return None
    edge, out = deck.edge(knuckle)
    r = dict(wrist=[round(v, 1) for v in wrist], knuckle=[round(v, 1) for v in knuckle], edge=[round(v, 1) for v in edge],
             knuckle_to_edge_cm=round(norm(sub(knuckle, edge)), 1),
             knuckle_outside_edge_cm=round(deck.outside(knuckle[0], knuckle[1]), 1),
             knuckle_above_rail_cm=round(knuckle[2] - edge[2], 1),
             arm_straightness=round(norm(sub(wrist, upper)) / max(norm(sub(fore, upper)) + norm(sub(wrist, fore)), 1e-6), 3))
    if end:
        r['finger_end'] = [round(v, 1) for v in end]
        r['finger_end_outside_edge_cm'] = round(deck.outside(end[0], end[1]), 1)
        r['finger_end_above_top_cm'] = round(end[2] - deck.top(end[0], end[1]), 1)
        r['finger_end_in_slab'] = deck.outside(end[0], end[1]) < 0 and -deck.thickness < end[2] - deck.top(end[0], end[1]) < 0
        # Fingers should run down past the edge (wrapped under): the knuckle-to-end direction against straight down.
        r['fingers_from_down_deg'] = angle(sub(end, knuckle), [0., 0., -1.])
    f0, f3 = bones.get(f'finger_0_{side}'), bones.get(f'finger_3_{side}')
    if f0 and f3 and thumb:
        along = unit(sub(knuckle, wrist)); across = unit(sub(f3, f0))
        normal = unit(cross(along, across))
        # The palm faces the thumb's side of the knuckle line's normal; the retarget turns it towards the deck (-out).
        if dot(normal, sub(thumb, wrist)) < 0:
            normal = mul(normal, -1)
        r['palm_from_inward_deg'] = angle(normal, mul(out, -1))
        r['hand_axis_from_down_deg'] = angle(along, [0., 0., -1.])
    r['on_board'] = r['knuckle_to_edge_cm'] < 8
    return r


def mount_ride():
    qa.py('live.L.skate_goofy(False); live.skate_park(); live.skate_input()')
    for _ in range(40):
        state = qa.py('print(live.skate_state())')
        if 'simulation=PhysicsGround' in state:
            return
        time.sleep(.5)
    raise RuntimeError('Ride did not mount: ' + state.strip())


AIM = r'''
P = live.L.player(); M = P.get_editor_property('mesh')
D = next(c for c in P.get_components_by_class(unreal.StaticMeshComponent) if c.get_name() == 'SkateDeck')
f = D.get_forward_vector(); f.z = 0; f = f.normal(); s = unreal.Vector(-f.y, f.x, 0)
at = (M.get_socket_location('pelvis') + D.get_world_location()) * .5
loc = at + (s if 'VIEW' == 'side' else f) * DIST + unreal.Vector(0, 0, 25)
unreal.MegaParkValidation.review_camera(loc, at, 40.0)
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--port', type=int, default=8830)
    parser.add_argument('--riders', default='Cairo,Nox,Modori')
    parser.add_argument('--grabs', default='grab_right,grab_left')
    parser.add_argument('--sticks', default=','.join(STICKS))
    parser.add_argument('--stick', choices=('right', 'left'), default='right', help='the stick held with the trigger')
    parser.add_argument('--dist', type=float, default=230.)
    args = parser.parse_args()
    qa.bridge.URL = f'http://127.0.0.1:{args.port}'
    qa.py((qa.GAME / 'scenarios/skate_live_skate.py').read_text())
    out = qa.yori.OUT / 'skateqa' / 'grabs'; out.mkdir(parents=True, exist_ok=True)
    path = out / 'grabs.json'
    results = json.loads(path.read_text()) if path.exists() else {}
    for rider in args.riders.split(','):
        print(qa.py(f"print(live.L.switch_character({rider!r}))").strip(), flush=True)
        time.sleep(3); mount_ride()
        for trigger in args.grabs.split(','):
            for stick in args.sticks.split(','):
                left = STICKS[stick]
                name = f"{rider.lower()}-{trigger.split('_')[1]}-{stick}" + ('' if args.stick == 'right' else '-leftstick')
                keys = {trigger: True} | ({args.stick: left} if stick != 'neutral' else {})
                qa.py(f"live.park.place({QUARTER[0]},{QUARTER[1]},0); live.park.look(-12,0); live.park.launch(950)\n"
                      + FREEZE.replace('KEYS', repr(keys)).replace('HOLD', repr(HOLD)))
                for _ in range(40):
                    time.sleep(.2)
                    if qa.py('print(live.FROZEN)').strip().endswith('True'):
                        break
                else:
                    qa.py("live.stop('grab'); live.skate_input()"); print(name, 'never grabbed', flush=True); continue
                try:
                    m = json.loads(qa.py(MEASURE).strip().splitlines()[-1])
                    deck = Deck(m['deck'], m['scale'])
                    m['trick'] = m['state'].split(' | ')[1][6:] if ' | ' in m['state'] else ''
                    m['legs'] = {s: leg(m['bones'], s, deck) for s in 'LR'}
                    m['hands'] = {s: hand(m['bones'], s, deck) for s in 'LR'}
                    m['deck_model'] = dict(half_length=round(deck.half_length, 1), half_width=round(deck.half_width, 1),
                                           kick_top=round(deck.kick_top, 1), thickness=round(deck.thickness, 2))
                    m['shots'] = [f'{name}-side.png', f'{name}-front.png']
                    results[name] = m
                    brief = {s: (v['knee_above_top_cm'], v['lowest_over_deck']['above_top_cm'] if v and v['lowest_over_deck'] else None)
                             for s, v in m['legs'].items() if v}
                    hands = {s: (v['knuckle_to_edge_cm'], v.get('finger_end_outside_edge_cm'), v.get('palm_from_inward_deg'), v['arm_straightness'])
                             for s, v in m['hands'].items() if v}
                    print(name, repr(m['trick']), 'legs(knee,lowest)', brief, 'hands(knuckle-edge,end-out,palm,straight)', hands, flush=True)
                    for view in ('side', 'front'):
                        qa.py(AIM.replace('VIEW', view).replace('DIST', repr(args.dist)))
                        time.sleep(.6)
                        qa.py(f"live.L.screenshot({str(out / f'{name}-{view}.png')!r})")
                        time.sleep(1.)
                finally:
                    qa.py("live.stop('grab'); live.skate_input(); "
                          "unreal.GameplayStatics.set_global_time_dilation(live.L.game_world(), 1.); "
                          "unreal.MegaParkValidation.restore_player_camera()")
                    time.sleep(1.5)
                path.write_text(json.dumps(results, indent=1) + '\n')
    print('wrote', path, flush=True)


if __name__ == '__main__':
    try:
        main()
    finally:
        qa.py("live.stop('grab'); live.skate_release(); unreal.GameplayStatics.set_global_time_dilation(live.L.game_world(), 1.); "
              "unreal.MegaParkValidation.restore_player_camera()")
