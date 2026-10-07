"""Skate pier module placements and grind lines come from the committed pin, not from the private meshes."""
import itertools
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'world'))
import yori  # noqa: E402,F401
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'world'/'regions'/'skatepark'))
import modules as M  # noqa: E402
import layout as L  # noqa: E402


def placements():
    return list(L.MODULES) + [m for t in L.TERRACES for m in L.terrace_modules(t)]


class PierModules(unittest.TestCase):
    def test_placements_name_pinned_parts(self):
        parts = M.spec()['parts']
        for item in placements():
            self.assertIn(item['part'], parts, item['id'])
            self.assertEqual(item['yaw'] % 90, 0, item['id'])
        for t in L.TERRACES:
            self.assertIn('line', parts[t['handrail']])

    def test_grind_lines_are_continuous(self):
        for g in L.GRIND_LINES:
            pts = L.grind_line(g['pieces'])
            self.assertGreater(len(pts), 1, g['id'])
            lines = [M.line(L.MODULE[piece]) for piece in g['pieces']]
            for a, b in zip(lines, lines[1:]):
                self.assertLess(min(math.dist(a[-1], b[0]), math.dist(a[0], b[-1])), .05, g['id'])

    def test_handrails_follow_the_stairs(self):
        for t in L.TERRACES:
            for _, line in L.terrace_rails(t):
                top = max(z for _, z in line)
                self.assertGreater(top, t['height'], t['id'])
                self.assertLessEqual(min(x for x, _ in line), t['x1'] + t['tread'], t['id'])
                self.assertGreaterEqual(max(x for x, _ in line), t['x1'] + t['steps']*t['tread'] - .01, t['id'])

    def test_free_standing_modules_do_not_overlap(self):
        boxes = {m['id']: M.footprint(m) for m in L.MODULES}
        for (a, p), (b, q) in itertools.combinations(boxes.items(), 2):
            overlap = min(p[1], q[1]) - max(p[0], q[0]), min(p[3], q[3]) - max(p[2], q[2])
            self.assertFalse(overlap[0] > .01 and overlap[1] > .01, f'{a} overlaps {b}')

    def test_rails_have_unique_ids(self):
        ids = [r['id'] for r in L.rails()]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == '__main__':
    unittest.main()
