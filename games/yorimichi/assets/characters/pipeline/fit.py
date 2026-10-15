"""How well a character's exported clips fit its body, gated: the merged move set (adventure/retarget.py), the bike
moves (vehicles/bike/rider.py) and the horseback moves (horses/rider.py) each have their export.json checked here by
the character's fit step, which fails when a clip fits worse than it should.

    python games/yorimichi/assets/characters/pipeline/fit.py --character nox [--record] [--build DIR]

Per clip, the metrics are the exported ones, measured on the solved skeleton before Unreal: `ankle_cm` (the farther of
the two ankles from where the leg solve was asked to put it), `lowest_toe_cm` (the lowest toe, cm above the floor),
the stance checks of a clip with an adventure.toml [stance] (stance_*_cm), and on the bike and the horse
`reach_<limb>_cm` (how far a hand or foot fell short of its grip, pedal, stirrup, rein or the ground). Grip contacts
rendered in the game (grips/check.py) and skin contacts in Unreal (Scripts/import_character.py) are checked where they
are made, not here.

A clip fails when:
- a metric is missing, not finite, or the clip has no frames;
- `ankle_cm` or a reach is above BOUNDS, unless character.toml waives it ([[fit]]: report, clip, metric, a bound
  and the reason) or SHARED does for every character;
- the report has no clips, or lacks one its baseline has (without a baseline: one every other mover's baseline of
  that report has);
- the character has a baseline (assets/characters/fit/<id>.json, written by --record from a reviewed build and
  committed) and the clip has another frame count, or a metric is worse than the baseline by more than MARGIN.

A new character needs no baseline: its clips are held to BOUNDS until one is recorded.
"""
from pathlib import Path
import argparse
import json
import math
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import definition  # noqa: E402

REPORTS = ('adventure', 'bike', 'horse')
FIT = Path(__file__).resolve().parents[1] / 'fit'   # the baselines: outside the character's folder, an input of its exports
BOUNDS = {'ankle_cm': 4.0, 'reach_cm': 4.0}   # cm: above every current character's grounded clips, waivers aside
LIMBS = ('hand_L', 'hand_R', 'foot_L', 'foot_R')   # each bike or horse clip's reaches
RIDES = ('bike', 'horse')   # reports whose every clip holds both hands and both feet to a contact
MARGIN = 0.5                                   # cm a metric may worsen against the baseline
# Waivers every character shares, as character.toml's [[fit]]: the donor's own clips are retargeted onto everyone.
SHARED = [
    {'report': 'adventure', 'clip': 'DoubleJump', 'metric': 'ankle_cm', 'bound': 25.0,
     'reason': "the donor's double jump: the solved ankles fall up to 19.5 cm short of their goals on every character "
               "retargeted from it (Modori 18.96, Kaede 19.49 when the gate was adopted)"},
]


def metrics(report, clip):
    """{metric: (value, higher_is_worse)} of one clip's export.json entry."""
    if report in RIDES:
        reach = clip.get('reach_error_cm', {})
        return {f'reach_{limb}_cm': (reach.get(limb, math.nan), True) for limb in sorted(set(LIMBS) | set(reach))}
    ankles = [clip.get('ankle_L_cm', math.nan), clip.get('ankle_R_cm', math.nan)]
    # Each ankle is checked before the farther is taken: max() would hide a missing or NaN one.
    finite = all(isinstance(v, (int, float)) and math.isfinite(v) for v in ankles)
    out = {'ankle_cm': (max(ankles) if finite else math.nan, True),
           'lowest_toe_cm': (clip.get('lowest_toe_cm', math.nan), False)}
    out.update({k: (v, True) for k, v in clip.items() if k.startswith('stance_') and k.endswith('_cm')})
    return out


def clips(character, report, build=None):
    """{clip: export.json entry} of a character's report: the move set's clips and the donor's own, or the ride's.
    `build`: the game's build folder (default: this checkout's)."""
    if build is None:
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'world'))
        import yori
        build = yori.OUT
    path = Path(build) / character.output / report / 'export.json'
    data = json.loads(path.read_text())
    return {**data['clips'], **data.get('own', {})}


def baseline(character):
    path = FIT / f'{character.id}.json'
    return json.loads(path.read_text()) if path.exists() else {}


def expected(character, report):
    """The clips a report must hold: its baseline's, or without one the clips every other mover's baseline of that
    report shares (the merged move set, or a ride's moves)."""
    if names := set(baseline(character).get(report, {})):
        return names
    others = [set(json.loads(p.read_text()).get(report, {})) for p in sorted(FIT.glob('*.json')) if p.stem != character.id]
    others = [o for o in others if o]
    return set.intersection(*others) if others else set()


def bound(character, report, clip, metric):
    """The waived bound, or BOUNDS' (None: the metric has no absolute bound)."""
    for waiver in [*character.fit, *SHARED]:
        if (waiver['report'], waiver['clip'], waiver['metric']) == (report, clip, metric):
            return waiver['bound']
    return BOUNDS['reach_cm'] if metric.startswith('reach_') else BOUNDS.get(metric)


def check(character, report, found):
    """Failures (strings) of one report's clips, `found` as in clips()."""
    failures, base = [], baseline(character).get(report, {})
    if not found:
        failures.append('no clips exported')
    for name in sorted(expected(character, report) - set(found)):
        failures.append(f'{name}: expected, not exported')
    for name, clip in sorted(found.items()):
        if not clip.get('frames'):
            failures.append(f'{name}: no frames')
            continue
        was = base.get(name)
        if was and was['frames'] != clip['frames']:
            failures.append(f"{name}: {clip['frames']} frames, the baseline {was['frames']}")
        values = metrics(report, clip)
        if not values:
            failures.append(f'{name}: no metrics')
        for metric in sorted(set(was or {}) - set(values) - {'frames'}):
            failures.append(f'{name} {metric}: in the baseline, not exported')   # a bike limb, say
        for metric, (value, worse_up) in sorted(values.items()):
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                failures.append(f'{name} {metric}: {value}')
                continue
            limit = bound(character, report, name, metric)
            if worse_up and limit is not None and value > limit:
                failures.append(f'{name} {metric}: {value} > {limit}')
            if was and metric not in was:
                failures.append(f'{name} {metric}: not in the baseline')
            elif was and (value - was[metric] if worse_up else was[metric] - value) > MARGIN:
                failures.append(f'{name} {metric}: {value}, the baseline {was[metric]} (margin {MARGIN})')
    for waiver in character.fit:
        if waiver['report'] == report and waiver['clip'] not in found:
            failures.append(f"waiver for {waiver['clip']} {waiver['metric']}: no such clip")
    return failures


def gate(character, report):
    """Raise when one of the character's reports fails; called at the end of its export step."""
    character = definition.load(character) if isinstance(character, str) else character
    failures = check(character, report, clips(character, report))
    for line in failures:
        print(f'FIT {character.id} {report}: {line}', flush=True)
    assert not failures, f'{character.id} {report}: {len(failures)} fit failures'
    print(f'FIT {character.id} {report}: passed', flush=True)


def record(character, build=None):
    """fit/<id>.json from the character's current reports: review the values before committing it."""
    out = {}
    for report in REPORTS:
        try:
            found = clips(character, report, build)
        except FileNotFoundError:
            continue
        out[report] = {name: {'frames': clip['frames'], **{m: v for m, (v, _) in metrics(report, clip).items()}}
                       for name, clip in sorted(found.items())}
    lines = [f'  "{report}": {{\n' + ',\n'.join(f'   {json.dumps(name)}: {json.dumps(values, sort_keys=True)}'
                                             for name, values in clips_.items()) + '\n  }'
             for report, clips_ in out.items()]
    (FIT / f'{character.id}.json').write_text('{\n' + ',\n'.join(lines) + '\n}\n')   # one clip per line, for review
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--character', required=True)
    parser.add_argument('--record', action='store_true', help="write fit/<id>.json from the character's current reports")
    parser.add_argument('--build', help="the game's build folder holding the reports (default: this checkout's)")
    args = parser.parse_args()
    character = definition.load(args.character)
    if args.record:
        print(json.dumps({r: len(c) for r, c in record(character, args.build).items()}))
        sys.exit(0)
    receipt = {}
    for report in REPORTS:
        try:
            found = clips(character, report, args.build)
        except FileNotFoundError:
            continue
        failures = check(character, report, found)
        receipt[report] = {'clips': len(found), 'failures': failures}
        print(f'{character.id} {report}: {len(found)} clips,', 'passed' if not failures else f'{len(failures)} failures')
        for line in failures:
            print('  ' + line)
    assert receipt, f'{character.id}: no adventure, bike or horse report'
    passed = not any(r['failures'] for r in receipt.values())
    if args.build is None:   # the build step's receipt: build/<game>/<output>/fit.json
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'world'))
        import yori
        (yori.OUT / character.output / 'fit.json').write_text(json.dumps({'passed': passed, **receipt}, indent=1) + '\n')
    sys.exit(0 if passed else 1)
