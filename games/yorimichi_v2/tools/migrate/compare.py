"""Parity oracle for the one-time migration: compare two scene dumps of the same bounds.

    uv run python games/yorimichi_v2/tools/migrate/compare.py ORIGINAL.json V2.json [--json]

Both dumps come from tools/migrate/dump.py: ORIGINAL from the running original game, V2 from the running V2 map.
For every mesh it compares the placed copies (static components and instances alike, by world transform) and
the settings each copy is drawn with (collision, shadow, cull distances, visibility, tags). Transforms match
within 0.1 cm and 0.01 degrees; scale within 1e-4. It reports per mesh: copies only in one dump, and settings
that differ between matched copies. Exit 0 only when nothing differs or every difference is listed in
--explained (a JSON object mesh → reason, kept beside the region's record).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

POSITION_CM = 0.1
ANGLE_DEG = 0.01
SCALE = 1e-4
SETTINGS = ('collision_profile', 'collision_enabled', 'cast_shadow', 'visible', 'hidden_in_game', 'cull_distance')
# Tags the migration adds to name a component's runtime list (V2ScenePatch.h): not a difference.
V2_TAG_PREFIX = 'V2Role:'


def angle_close(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0) <= ANGLE_DEG


def close(a, b):
    return (all(abs(a[i] - b[i]) <= POSITION_CM for i in range(3)) and
            all(angle_close(a[i], b[i]) for i in range(3, 6)) and
            all(abs(a[i] - b[i]) <= SCALE * max(1.0, abs(a[i])) for i in range(6, 9)))


def copies(dump):
    """mesh → [(transform, settings)] for every drawn copy, static or instanced."""
    found = defaultdict(list)
    for record in dump['meshes']:
        settings = {k: record.get(k) for k in SETTINGS}
        settings['tags'] = sorted(t for t in record.get('tags', []) if not t.startswith(V2_TAG_PREFIX))
        rows = record.get('instances') or [record['transform']]
        for row in rows:
            found[record['mesh']].append((row, settings))
    return found


def match(left, right):
    """Pair copies by transform with a coarse grid, so each lookup scans only its neighbourhood."""
    cell = 10.0
    grid = defaultdict(list)
    for index, (row, _) in enumerate(right):
        grid[(math.floor(row[0] / cell), math.floor(row[1] / cell))].append(index)
    used, pairs, only_left = set(), [], []
    for row, settings in left:
        gx, gy = math.floor(row[0] / cell), math.floor(row[1] / cell)
        hit = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for index in grid.get((gx + dx, gy + dy), ()):
                    if index not in used and close(row, right[index][0]):
                        hit = index
                        break
                if hit is not None:
                    break
            if hit is not None:
                break
        if hit is None:
            only_left.append(row)
        else:
            used.add(hit)
            pairs.append((settings, right[hit][1]))
    only_right = [right[i][0] for i in range(len(right)) if i not in used]
    return pairs, only_left, only_right


def compare(original, v2):
    a, b = copies(original), copies(v2)
    report = {}
    for mesh in sorted(set(a) | set(b)):
        pairs, only_a, only_b = match(a.get(mesh, []), b.get(mesh, []))
        settings = defaultdict(int)
        for left, right in pairs:
            for key in left:
                if left[key] != right[key]:
                    settings[f'{key}: {left[key]!r} -> {right[key]!r}'] += 1
        if only_a or only_b or settings:
            report[mesh] = {'original': len(a.get(mesh, [])), 'v2': len(b.get(mesh, [])),
                            'only_original': len(only_a), 'only_v2': len(only_b),
                            'settings': dict(settings), 'sample_only_original': only_a[:3],
                            'sample_only_v2': only_b[:3]}
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('original', type=Path)
    parser.add_argument('v2', type=Path)
    parser.add_argument('--explained', type=Path, help='JSON object: mesh path -> why it differs on purpose')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    original, v2 = (json.loads(p.read_text()) for p in (args.original, args.v2))
    if original.get('bounds_cm') != v2.get('bounds_cm'):
        print(f'the dumps cover different bounds: {original.get("bounds_cm")} vs {v2.get("bounds_cm")}', file=sys.stderr)
        return 2
    report = compare(original, v2)
    explained = json.loads(args.explained.read_text()) if args.explained else {}
    unexplained = {mesh: row for mesh, row in report.items() if mesh not in explained}
    if args.json:
        print(json.dumps({'differences': report, 'unexplained': sorted(unexplained)}, indent=2, sort_keys=True))
    else:
        total_a = sum(len(v) for v in copies(original).values())
        total_b = sum(len(v) for v in copies(v2).values())
        print(f'original {total_a} copies, V2 {total_b}; {len(report)} mesh(es) differ, {len(unexplained)} unexplained')
        for mesh, row in report.items():
            why = f'  (explained: {explained[mesh]})' if mesh in explained else ''
            print(f'  {mesh}: original {row["original"]}, V2 {row["v2"]}, only original {row["only_original"]}, '
                  f'only V2 {row["only_v2"]}{why}')
            for change, count in sorted(row['settings'].items()):
                print(f'      {count} x {change}')
    return 1 if unexplained else 0


if __name__ == '__main__':
    sys.exit(main())
