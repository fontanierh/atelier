"""A board a trick catches end for end stays so (FRideAnimator's board turn), offline.

Native's board is a body. A shove-it, a varial, a hardflip or an inward heelflip catches it turned half a turn, and it
rolls on nose trailing until another such trick turns it back. Ride shows the clips' board, and every clip after a
trick's air clip (its follow-through, the default air tree, the landings) stands on a board the right way round. So the
animator turns the shown deck half a turn about its normal from the handover on, whenever a trick's clip hands over to
a clip whose board points the other way along the ground (RideAnimator.cpp, Evaluate).

These tests read the clips the animator names (RideAnimator.cpp's trick table) from the tracked native bundle with the
stdlib decoder. They check that the rule turns the board for exactly the tricks the session spins half a turn
(RideSession.cpp's FlipInfo), only at the air clip's end, and that a flip on a turned board rolls the other way about
the board's own length. With the owner's car park take (ignored build folder) they also check Native's board: after the
take's nollie inward heelflip it stays end for end for the rest of the ride, through the kickflip and the nollie
heelflip that follow, which is why Ride's flips there looked mirrored before the board kept its turn.
"""
import importlib.util
import json
import math
import re
import sys
from pathlib import Path

import pytest

GAME = Path(__file__).resolve().parents[1]
REPO = GAME.parents[1]
SCRIPTS = GAME / 'unreal' / 'Scripts' / 'skate_ride'
BUNDLE = GAME / 'unreal' / 'Content' / 'Data' / 'SkateNative'
RIDE = REPO / 'platform/engine/Plugins/Activities/Skate/Source/AtelierSkate/Private/Ride'
TAKE = REPO / 'build/yorimichi/ride-record/carpark-1/frames.jsonl'

spec = importlib.util.spec_from_file_location('skate_ride_native_turn', SCRIPTS / 'native.py')
N = importlib.util.module_from_spec(spec)
sys.modules['skate_ride_native_turn'] = N
spec.loader.exec_module(N)

ANIMATOR = (RIDE / 'RideAnimator.cpp').read_text()
SESSION = (RIDE / 'RideSession.cpp').read_text()


def trick_table():
    """RideAnimator.cpp's TrickNames: trick -> (ground, air, follow, low), absent clips as None."""
    table = {}
    for trick, body in re.findall(r'\{Flick::(\w+), (TEXT\("\w+"\), TEXT\("\w+"\), (?:TEXT\("\w+"\)|nullptr)[^}]*)\}', ANIMATOR):
        clips = [None if c == 'nullptr' else re.match(r'TEXT\("(\w+)"\)', c).group(1)
                 for c in re.findall(r'TEXT\("\w+"\)|nullptr', body)]
        table[trick] = tuple((clips + [None] * 4)[:4])
    return table


def loaded(field):
    """A clip the animator loads by role (C.AirIdle = Load(TEXT("...")))."""
    return re.search(rf'C\.{field} = Load\(TEXT\("(\w+)"\)\)', ANIMATOR).group(1)


def flip_yaw():
    """RideSession.cpp's FlipInfo: trick -> the board's spin about its up (degrees)."""
    return {t: int(y) for t, _, y in re.findall(r"case Flick::(\w+): return \{(-?\d+), (-?\d+),", SESSION)}


class Clips:
    def __init__(self):
        self.bundle = N.Bundle(BUNDLE)
        rig = self.bundle.rig()
        self.ref = rig.named_pose(0, 'rig_tpose')
        self.deck = rig.index('SKATEBOARD_ROOT')
        self.paths = {p.stem: int(p.parent.name) for p in self.bundle.clip_paths()}
        rest = N.normalised(N.split_sample(self.ref.samples[self.deck])[1])
        back = (-rest[0], -rest[1], -rest[2], rest[3])
        # The deck's length (toward the nose) and normal in its own frame: the rig's forward (z) and up (y).
        self.nose = N.quaternion_rotate(back, (0., 0., 1.))
        self.up = N.quaternion_rotate(back, (0., 1., 0.))
        self.cache = {}

    def clip(self, name):
        if name not in self.cache:
            self.cache[name] = self.bundle.clip(self.paths[name], name)
        return self.cache[name]

    def board(self, name, frame):
        """The board's rotation under the trajectory at a frame (-1: the last)."""
        c = self.clip(name)
        return N.local_pose(c, frame % c.frame_count, self.deck, self.ref)[1]

    def flat_nose(self, name, frame):
        """The board's nose along the ground (native x and z), unnormalised: short for a board on its side."""
        v = N.quaternion_rotate(self.board(name, frame), self.nose)
        return v[0], v[2]


@pytest.fixture(scope='module')
def clips():
    return Clips()


def turned(a, b):
    """FRideAnimator's rule: both noses clear of the vertical and pointing apart along the ground."""
    return math.hypot(*a) > .5 and math.hypot(*b) > .5 and a[0] * b[0] + a[1] * b[1] < 0


def same_way(a, b):
    return math.hypot(*a) > .5 and math.hypot(*b) > .5 and a[0] * b[0] + a[1] * b[1] > 0


def test_the_half_turn_tricks_turn_the_board(clips):
    table, yaws = trick_table(), flip_yaw()
    assert len(table) == 30 and set(table) <= set(yaws)
    air_tree = [loaded(f) for f in ('AirIdle', 'AirLow', 'AirExtend')]
    lands = [loaded(f) for f in ('LandLow', 'LandHigh', 'LandGrab', 'LandSketchy')]
    half = set()
    for trick, (ground, air, follow, low) in table.items():
        # The pop hands over to the air clip the same way round.
        assert same_way(clips.flat_nose(ground, -1), clips.flat_nose(air, 0)), trick
        caught = clips.flat_nose(air, -1)
        after = [c for c in (follow, low) if c] or air_tree
        ways = {turned(caught, clips.flat_nose(c, 0)) for c in after + lands}
        assert len(ways) == 1, f'{trick}: the clips after {air} disagree'
        if ways.pop():
            half.add(trick)
        else:
            assert all(same_way(caught, clips.flat_nose(c, 0)) for c in after + lands), trick
    assert half == {t for t in table if abs(yaws[t]) == 180}
    assert {'ShoveIt', 'VarialKickflip', 'Hardflip', 'InwardHeelflip', 'NollieInwardHeelflip'} <= half
    assert not half & {'Kickflip', 'Heelflip', 'Shove360', 'TreFlip', 'NollieHeelflip', 'InwardHeelflip360'}


def test_the_clips_after_the_air_keep_their_way(clips):
    """Nothing after the catch hands the board over turned again: each follow-through, the air tree and the landings
    keep their board the way they start, so the turn holds until the next trick."""
    table = trick_table()
    names = {c for _, _, f, l in table.values() for c in (f, l) if c}
    names |= {loaded(f) for f in ('AirIdle', 'AirLow', 'AirExtend', 'LandLow', 'LandHigh', 'LandGrab', 'LandSketchy')}
    for name in sorted(names):
        start = clips.flat_nose(name, 0)
        frames = clips.clip(name).frame_count
        assert all(not turned(start, clips.flat_nose(name, f)) for f in range(frames)), name


def roll_about_length(clips, names, turn):
    """The board's roll about its own length over clips played one after the other (degrees), shown as is or turned
    half a turn about its normal."""
    half = (clips.up[0], clips.up[1], clips.up[2], 0.)
    total, last = 0., None
    for name, f in ((n, f) for n in names for f in range(clips.clip(n).frame_count)):
        q = clips.board(name, f)
        if turn:
            q = N.quaternion_multiply(q, half)
        if last is not None:
            # The step in the board's own frame: last^-1 q, as an axis times an angle.
            d = N.quaternion_multiply((-last[0], -last[1], -last[2], last[3]), q)
            if d[3] < 0:
                d = tuple(-x for x in d)
            s = math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2)
            angle = 2 * math.atan2(s, d[3])
            if s > 1e-9:
                total += math.degrees(angle) * sum(a * b for a, b in zip(d[:3], clips.nose)) / s
        last = q
    return total


def test_a_flip_on_a_turned_board_rolls_the_other_way(clips):
    """The same clip, the same roll for the rider: about the board's own length it reads the other way round once the
    board is end for end (how the take's goofy kickflip read +345 on Native's turned board and -350 on Ride's)."""
    # The kickflip's whole flip (its pop, air and follow-through); the nollie heelflip's air clip holds half of its
    # flip (the default air tree takes the board back upright).
    kickflip = trick_table()['Kickflip'][:3]
    for names, least in ((kickflip, 340), (('N_HEELFLIP_IN_HIGH_A',), 170)):
        straight, reversed_ = roll_about_length(clips, names, False), roll_about_length(clips, names, True)
        assert abs(straight) > least, (names, straight)
        assert abs(straight + reversed_) < 1, (names, straight, reversed_)


def take_rows():
    if not TAKE.exists():
        pytest.skip('the car park take is not recorded here')
    return [json.loads(line) for line in TAKE.read_text().splitlines() if line.strip()]


def heading(q):
    x, y, z, w = q
    return math.degrees(math.atan2(2 * (x * y + w * z), 1 - 2 * (y * y + z * z)))


def test_native_keeps_the_board_turned():
    rows = take_rows()
    modes = [int(re.search(r'\bmode=(\d+)', r['s']).group(1)) for r in rows]
    rel = [((heading(r['d'][3:7]) - heading(r['p'][3:7]) + 180) % 360) - 180 for r in rows]
    airs = [k for k in range(1, len(rows)) if modes[k] == 2 and modes[k - 1] != 2]
    first_land = next(k for k in range(airs[0], len(rows)) if modes[k] == 1)
    assert 'Inward Heelflip' in rows[first_land]['s'] and abs(rel[airs[0] - 5]) < 30
    # Rolling after the catch to the end of the ride: end for end, nose trailing.
    rolling = [k for k in range(first_land + 20, len(rows)) if modes[k] == 1]
    assert len(rolling) > 500
    assert sum(abs(rel[k]) > 150 for k in rolling) / len(rolling) > .95
    # The kickflip and the nollie heelflip after it pop from the turned board.
    assert len(airs) >= 3 and all(abs(rel[k - 3]) > 150 for k in airs[1:3])
