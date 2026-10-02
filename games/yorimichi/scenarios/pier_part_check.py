"""Summarise a Sunset Pier rehearsal and refuse bail or incomplete film takes."""
import argparse
import json
from collections import defaultdict
from pathlib import Path

from skate import parse


def assess(take):
    rows = json.loads((take / 'states.json').read_text())
    done = json.loads((take / 'done.json').read_text())
    by_shot = defaultdict(list)
    for row in rows: by_shot[row['shot']].append(row)
    shots = {}
    requirements = {mark['shot']: mark.get('needs',{}) for mark in done['shots']}
    for name, ride in by_shot.items():
        states = [parse(row['state']) for row in ride]
        bails = sum(s.get('mode') == '4' for s in states)
        bails_counter = int(states[-1].get('bails', 0)) - int(states[0].get('bails', 0))
        distance = sum(((b['x']-a['x'])**2 + (b['y']-a['y'])**2)**.5 for a, b in zip(ride, ride[1:]))
        combos = list(dict.fromkeys(s['combo'] for s in states if s.get('combo')))
        grind = sum(s.get('mode') == '3' for s in states) / 60
        grind_runs=sum(s.get('mode')=='3' and (i==0 or states[i-1].get('mode')!='3') for i,s in enumerate(states))
        air = sum(s.get('mode') == '2' for s in states) / 60
        manual = sum(s.get('manual') == '1' for s in states) / 60
        needed=requirements.get(name,{})
        meets=(not needed.get('grind') or grind>.05) and grind_runs>=needed.get('grind_runs',0) and (not needed.get('manual') or manual>.05) and (not needed.get('air') or air>.05)
        shots[name] = dict(ok=not bails and not bails_counter and distance > 8 and meets and states[-1].get('mode')=='1',
                           seconds=round(len(ride)/60, 2), distance_m=round(distance, 2),
                           requirements=needed, manual_seconds=round(manual,2),
                           grind_seconds=round(grind, 2), grind_runs=grind_runs, air_seconds=round(air, 2),
                           bail_frames=bails, bails=max(0, bails_counter), combos=combos,
                           start=[ride[0][k] for k in ('x', 'y', 'z')],
                           end=[ride[-1][k] for k in ('x', 'y', 'z')])
    frames = list(take.glob('frame_*.png')) if done['filmed'] else []
    complete = not done['filmed'] or len(frames) == done['film_frames']
    report = dict(ok=complete and bool(shots) and all(s['ok'] for s in shots.values()),
                  complete_frames=complete, expected_frames=done['film_frames'], actual_frames=len(frames), shots=shots)
    (take / 'review.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('take', type=Path)
    report = assess(ap.parse_args().take)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['ok'] else 1)
