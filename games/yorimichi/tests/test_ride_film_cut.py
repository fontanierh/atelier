"""The Mega Park Ride film's cut: kept parts in order, a replay at a third of the speed, sounds moved onto the film."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scenarios'))
from megapark_ride_film_mix import NEUTRAL_LOOPS, REPLAY_VOLUME, cut  # noqa: E402

BASE = 1000000


def shot(k, name, frames, keep=True, loops=None, replay=None, slowbuf=()):
    return {'k': k, 'name': name, 'dir': f'{k:02d}_{name}', 'frames': frames, 'keep': keep,
            'cams': [[i, 100. * k, 0., 0., 0., 300.] for i in range(frames)],
            'loops': [f'{k} 1 0 1 0 1 0 1 0 1'] * (2 * frames) if loops is None else loops,
            'replay': replay, 'slowbuf': list(slowbuf)}


def sound(frame, volume=1.):
    return {'frame': frame, 'sound': '/Game/Audio/Skate/catch/catch_01.catch_01', 'x': 0., 'y': 0., 'z': 0., 'volume': volume}


class CutTest(unittest.TestCase):
    def test_parts_follow_each_other_and_dropped_shots_leave_nothing(self):
        shots = [shot(0, 'a', 3), shot(1, 'b', 5, keep=False), shot(2, 'c', 2)]
        events = [sound(BASE + 4), sound(2 * BASE + 1), sound(3 * BASE + 1), sound(-1000000)]
        frames, cams, loops, out, marks = cut(shots, events, BASE)
        self.assertEqual(frames, ['parts/00_a/f00000.jpg', 'parts/00_a/f00001.jpg', 'parts/00_a/f00002.jpg',
                                  'parts/02_c/f00000.jpg', 'parts/02_c/f00001.jpg'])
        self.assertEqual([c[0] for c in cams], [0, 1, 2, 3, 4])
        self.assertEqual(cams[3][1], 200.)
        self.assertEqual(len(loops), 2 * len(frames))
        self.assertEqual([e['frame'] for e in out], [4, 6 + 1])      # shot c starts at 60 Hz frame 6
        self.assertEqual([m['shot'] for m in marks], ['a', 'c'])
        self.assertEqual(marks[1]['film_frame'], 3)

    def test_short_loop_rows_are_padded(self):
        frames, cams, loops, out, marks = cut([shot(0, 'a', 3, loops=['1 1 0 1 0 1 0 1 0 1'] * 4), shot(1, 'b', 1, loops=[])], [], BASE)
        self.assertEqual(loops, ['1 1 0 1 0 1 0 1 0 1'] * 6 + [NEUTRAL_LOOPS] * 2)

    def test_trimmed_frames_leave_with_their_sounds(self):
        loops = [f'{i} 1 0 1 0 1 0 1 0 1' for i in range(12)]
        events = [sound(BASE + 1), sound(BASE + 4), sound(BASE + 7.5), sound(BASE + 8.5), sound(BASE + 11), sound(2 * BASE + 1)]
        frames, cams, loops_out, out, marks = cut([shot(0, 'a', 6, loops=loops), shot(1, 'b', 2)], events, BASE,
                                                  {'a': [(2, 3), (5, None)]})
        self.assertEqual(frames[:3], ['parts/00_a/f00000.jpg', 'parts/00_a/f00001.jpg', 'parts/00_a/f00004.jpg'])
        self.assertEqual([c[0] for c in cams], [0, 1, 2, 3, 4])
        self.assertEqual(loops_out[:6], [loops[i] for i in (0, 1, 2, 3, 8, 9)])
        self.assertEqual([e['frame'] for e in out], [1, 4 + .5, 6 + 1])    # 60 Hz 4, 7.5 and 11 fell in the cuts
        self.assertEqual(marks[0]['seconds'], round(3 / 30., 2))

    def test_replay_stretches_the_air_three_times(self):
        # A 90 Hz shot: every sim frame saved, 2/3 of a 60 Hz frame apart; film frames at lv 0, 2, 4 ...
        buf, n, rep = [], 0, 0
        for i in range(30):
            lv = i * 2. / 3.
            if lv + 1e-6 >= 2 * n: name = f'f{n:05d}.jpg'; n += 1
            else: name = f'r{rep:05d}.jpg'; rep += 1
            buf.append([round(i / 90., 4), round(lv, 3), name, [1., 2., 3., 4., 5.], f'{i} 1 0 1 0 1 0 1 0 1'])
        s = shot(0, 'slow', n, replay={'from_t': 9 / 90., 'to_t': 20 / 90., 'stretch': 3}, slowbuf=buf)
        events = [sound(BASE + 2), sound(BASE + 6), sound(BASE + 8)]
        frames, cams, loops, out, marks = cut([s], events, BASE)
        self.assertEqual(len(frames), n + 12)                          # the window: sim frames 9 to 20
        self.assertEqual(frames[n:n + 2], [f'parts/00_slow/{buf[9][2]}', f'parts/00_slow/{buf[10][2]}'])
        self.assertEqual(len(loops), 2 * len(frames))
        self.assertEqual(loops[2 * n:2 * n + 2], [buf[9][4]] * 2)
        self.assertEqual([c[0] for c in cams], list(range(len(frames))))
        self.assertEqual([m['shot'] for m in marks], ['slow', 'slow (replay)'])
        # The window starts at lv 6: the sound at 6 replays at its start, the one at 8 two frames of 60 Hz later x3.
        replayed = out[3:]
        self.assertEqual([e['frame'] for e in replayed], [2 * n, 2 * n + 6])
        self.assertTrue(all(e['volume'] == REPLAY_VOLUME for e in replayed))
        self.assertEqual([e['frame'] for e in out[:3]], [2, 6, 8])
        frames, cams, loops, out, marks = cut([s], events, BASE, replays=['other'])     # its replay not chosen
        self.assertEqual((len(frames), [m['shot'] for m in marks], len(out)), (n, ['slow'], 3))


if __name__ == '__main__':
    unittest.main()
