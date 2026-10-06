"""The hippodrome rhythm charts (assets/audio/hippodrome/make.py): composed without rendering any audio, they keep the
chart rules (sorted, lanes 0-3, nothing before the gate, holds that never overlap their lane, densities per cup), and
a built charts.json, when there is one, is exactly what the composition gives."""
from pathlib import Path
import importlib.util
import json
import unittest

MAKE = Path(__file__).resolve().parents[1] / 'assets' / 'audio' / 'hippodrome' / 'make.py'
_spec = importlib.util.spec_from_file_location('hippodrome_make', MAKE)
make = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(make)

CHARTS = make.charts()
DENSITY = {'maiden': (1.3, 1.7), 'stakes': (2.0, 2.6), 'cup': (2.7, 3.3)}


class ChartTest(unittest.TestCase):
    def test_every_cup_has_a_valid_chart(self):
        self.assertEqual(set(CHARTS), {'maiden', 'stakes', 'cup'})
        for cup, c in CHARTS.items():
            with self.subTest(cup=cup):
                self.assertEqual(make.chart_problems(c, cup), [])

    def test_timing_fields(self):
        for cup, c in CHARTS.items():
            with self.subTest(cup=cup):
                beat = 60 / c['bpm']
                self.assertEqual(len(c['count_in']), 4)
                for a, b in zip(c['count_in'], c['count_in'][1:] + [c['start']]):
                    self.assertAlmostEqual(b - a, beat, places=4)
                self.assertGreater(c['loop_from'], c['start'])
                self.assertGreater(c['loop_to'], c['loop_from'])
                self.assertAlmostEqual(c['loop_to'] - c['loop_from'], 8 * 4 * beat, places=3)
                self.assertGreaterEqual(c['loop_to'] - c['start'], 110 if cup == 'cup' else 75)
                self.assertLessEqual(c['loop_to'], c['length'])

    def test_notes(self):
        for cup, c in CHARTS.items():
            with self.subTest(cup=cup):
                notes = c['notes']
                beat = 60 / c['bpm']
                self.assertEqual(notes, sorted(notes, key=lambda n: (n['t'], n['lane'])))
                self.assertTrue(all(n['lane'] in (0, 1, 2, 3) for n in notes))
                self.assertGreaterEqual(notes[0]['t'], c['start'] + beat - 1e-4)
                self.assertLessEqual(notes[-1]['t'], c['length'])
                for n in notes:
                    self.assertTrue(n['hold'] == 0 or .4 <= n['hold'] <= 1.6, n)
                last = {}
                for n in notes:
                    if n['lane'] in last:
                        p = last[n['lane']]
                        self.assertGreaterEqual(n['t'], p['t'] + p['hold'] + 1e-4, (p, n))
                    last[n['lane']] = n
                lo, hi = DENSITY[cup]
                self.assertTrue(lo <= len(notes) / (c['loop_to'] - c['start']) <= hi)
                times = [n['t'] for n in notes]
                chords = len(times) - len(set(times))
                if cup == 'maiden': self.assertEqual(chords, 0)
                else: self.assertGreater(chords, 0)
                self.assertGreater(sum(1 for n in notes if n['hold']), 0)
                self.assertEqual({n['lane'] for n in notes}, {0, 1, 2, 3})

    def test_notes_sit_on_lead_notes_or_drum_hits(self):
        for cup, c in CHARTS.items():
            with self.subTest(cup=cup):
                song = make.compose(cup)
                onsets = {round(e['t'], 6) for e in song['events'] if e['inst'] in ('lead', 'don', 'ka') and not e.get('count')}
                self.assertTrue(all(n['t'] in onsets for n in c['notes']))

    def test_built_charts_match(self):
        built = make.OUT / 'charts.json'
        if not built.is_file():
            self.skipTest('audio.hippodrome not built here')
        self.assertEqual(json.loads(built.read_text())['cups'], json.loads(json.dumps(CHARTS)))


if __name__ == '__main__':
    unittest.main()
