"""Whether the game holds every posed grip exactly: each hand on its prop, sample by sample, against the poser's.

    uv run python games/yorimichi/assets/characters/grips/check.py ROWS.jsonl [--character modori] [--out REPORT.json]

ROWS.jsonl is sample.py --held's rows (or a JSON list of the same rows, with a `film` frame number each, from a film).
For each grip (a prop and a hand), over the rows where the animation evaluated it at full weight (the grip report's
`pose.weight`, not the move set's, which can be a tick ahead while a grip blends in):

- `hand_mm_from_poser`: how far the hand bone is from the place game.py gave it on the prop (world millimetres);
- `spread_mm`: how far each measured bone (the hand, the index's base and tip, the thumb's and the ring finger's tips)
  wanders on the prop across the rows: 0 when the grip stays the same through every clip;
- `turn_spread_deg`: likewise for the hand's turn on the prop;
- `ik_miss_max_cm`: the grip node's largest miss (an arm too short for its pinned hand's place, after its collar's reach);
- `worst`: the moves (or film labels) with the largest spread.

The prop's frame is its mesh's (the sword's static mesh, the glider's skeletal mesh), in centimetres, unscaled.
"""
from pathlib import Path
import argparse
import collections
import json
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402

BONES = ('hand_{s}', 'finger_1_{s}', 'finger_end_1_{s}', 'thumb_end_{s}', 'finger_end_3_{s}')


def rot(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def angle(A, B):
    return float(np.degrees(np.arccos(np.clip((np.trace(A.T @ B) - 1) / 2, -1, 1))))


def main(args):
    text = args.rows.read_text()
    rows = json.loads(text) if text.lstrip().startswith('[') else [json.loads(l) for l in text.splitlines() if l.strip()]
    grips = json.loads((yori.GAME / 'unreal' / 'Content' / 'Data' / args.character / 'grips.json').read_text())['grips']
    held = collections.defaultdict(list)
    for r in rows:
        if 'move' not in r:
            continue
        hands = r.get('grip', {}).get('hands') or [{}, {}]
        prop = 'glider' if r['move'].get('mode') == 'glide' else 'sword'
        for i, side in enumerate('RL'):
            if hands[i].get('pose', {}).get('weight', 0.) >= .999 and prop in r and f'{prop}_{side}' in grips:
                held[f'{prop}_{side}'].append(r)
    report = {}
    for gid, rs in sorted(held.items()):
        prop, side = gid.split('_')
        bones = [b.format(s=side) for b in BONES]
        want = np.asarray(grips[gid]['hand']['location'])
        local, turns, off = collections.defaultdict(list), [], []
        labels = []
        for r in rs:
            tp, qp, sp = r[prop]
            Rp = rot(qp)
            for b in bones:
                local[b].append(Rp.T @ (np.asarray(r[b][0]) - tp) / sp)
            off.append(float(np.linalg.norm(local[bones[0]][-1] - want) * sp * 10.))
            turns.append(Rp.T @ rot(r[bones[0]][1]))
            labels.append(r.get('label') or r['move'].get('action') or r['move'].get('mode') or '')
        sp = rs[0][prop][2]
        mid = {b: np.median(np.array(v), 0) for b, v in local.items()}
        spread = {b: [float(np.linalg.norm(p - mid[b]) * sp * 10.) for p in v] for b, v in local.items()}
        worst = collections.defaultdict(float)
        for k, label in enumerate(labels):
            worst[label] = max(worst[label], max(spread[b][k] for b in bones))
        report[gid] = {
            'rows': len(rs),
            'hand_mm_from_poser': {'median': round(float(np.median(off)), 3), 'max': round(max(off), 3)},
            'spread_mm': {b: round(max(v), 3) for b, v in spread.items()},
            'turn_spread_deg': round(max(angle(turns[len(turns) // 2], T) for T in turns), 4),
            'ik_miss_max_cm': round(max(float((r.get('grip', {}).get('hands') or [{}, {}])['RL'.index(side)].get('pose', {}).get('miss', 0.)) for r in rs), 3),
            'worst': sorted(((round(v, 2), k) for k, v in worst.items()), reverse=True)[:5],
        }
    out = json.dumps(report, indent=1)
    print(out)
    if args.out:
        args.out.write_text(out + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('rows', type=Path)
    parser.add_argument('--character', default='modori')
    parser.add_argument('--out', type=Path)
    main(parser.parse_args())
