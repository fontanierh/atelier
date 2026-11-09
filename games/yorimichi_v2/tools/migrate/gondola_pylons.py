"""Plan the W18 gondola's pylons as objects of their own: one object per support tower, not one per line.

    uv run python games/yorimichi_v2/tools/migrate/gondola_pylons.py --check        # compare, write nothing
    uv run python games/yorimichi_v2/tools/migrate/gondola_pylons.py --paths        # the paths a claim must cover
    uv run python games/yorimichi_v2/tools/migrate/gondola_pylons.py --claim TASK   # rewrite objects.toml

Selection (deterministic): the `GD_L<line>_<n>_Tower` entries of gondola/runtime.json's `static` list, lines in id order and,
within a line, by straight distance from the line's lower station (the one with the lower location z), ties by name. The
first LIMIT are taken. Each gets `object/gondola/pylon-l<line>-<n>`, route = its one entry, and model = the record that
already owns its mesh (`adopted/gondola/tower-l<line>-<n>`). No new record is needed: objects.py writes each object's
asset.toml when it saves the object.

A pylon group (object/gondola/pylons-l<line>) is removed from objects.toml when every one of its towers is taken; a group
only partly taken is refused. Station objects, and every other line of the file, are kept byte for byte.

This tool only edits objects.toml. The coordinator's editor step still has to retire the three saved group patches
(their actors and manifest entries) before objects.py saves the new objects, or the towers would be drawn twice; see
docs/inventory/transport-objects.md. The write needs a claim that covers REGION's objects.toml (`--paths` lists them).
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parents[1]
REPO = GAME.parents[1]
sys.path.insert(0, str(GAME / 'tools' / 'content'))
import authority  # noqa: E402
import records  # noqa: E402

REGION = 'w18-gondola'
REGION_ID = 'region/w18-gondola'
DATA = GAME / 'unreal/Content/Data/gondola/runtime.json'
OBJECTS = GAME / 'world/regions' / REGION / 'objects.toml'
LIMIT = 20   # the most pylons this step makes objects; the file holds 10, so every tower is taken
MIN = 10     # fewer towers than this means the runtime file changed shape: refuse
TOWER = re.compile(r'GD_L(\d+)_(\d+)_Tower$')
GROUP = re.compile(r'object/gondola/pylons-l(\d+)$')


class PylonError(RuntimeError):
    pass


def runtime(path: Path = DATA) -> dict:
    if not path.is_file() or records.is_lfs_pointer(path):
        raise PylonError(f'{path} is missing or still a Git LFS pointer; fetch the data first')
    return json.loads(path.read_text())


def select(data: dict, limit: int | None = None) -> list[dict]:
    """The pylons taken, in route order: {name, line, index, model, object} for each."""
    limit = LIMIT if limit is None else limit
    lower = {}
    for line in data['lines']:
        stations = {s['id']: s['location_cm'] for s in data['stations'] if s['id'] in line['stations']}
        lower[line['id']] = min(stations.values(), key=lambda p: p[2])
    towers = []
    for entry in data['static']:
        match = TOWER.match(entry['name'])
        if not match:
            continue
        line_id = f'L{match.group(1)}'
        if line_id not in lower:
            raise PylonError(f'{entry["name"]} is on no line of the file')
        origin = lower[line_id]
        distance = sum((a - b) ** 2 for a, b in zip(entry['location_cm'], origin)) ** 0.5
        towers.append((line_id, distance, entry['name'], int(match.group(2))))
    towers.sort(key=lambda t: (t[0], t[1], t[2]))
    if len(towers) < MIN:
        raise PylonError(f'{len(towers)} pylon towers found, {MIN} expected')
    taken = []
    for line_id, _, name, index in towers[:limit]:
        number = line_id[1:]
        taken.append({'name': name, 'line': number, 'index': index,
                      'model': f'adopted/gondola/tower-l{number}-{index}',
                      'object': f'object/gondola/pylon-l{number}-{index}'})
    return taken


def block_text(pylon: dict) -> str:
    return '\n'.join([
        '[[objects]]', f'id = "{pylon["object"]}"', f'route = ["{pylon["name"]}"]', f'model = "{pylon["model"]}"',
        f'about = "support tower {pylon["index"]} of the L{pylon["line"]} pylon line, saved on its own"',
    ])


def render(text: str, data: dict, *, root: Path = GAME) -> str:
    """objects.toml with the taken pylons as objects of their own and their emptied groups removed."""
    head, *blocks = re.split(r'(?m)^(?=\[\[objects\]\])', text)
    taken = select(data)
    names = {p['name'] for p in taken}
    kept, dropped = [], []
    for block in blocks:
        item = tomllib.loads(block)['objects'][0]
        if GROUP.match(item['id']):
            if set(item['route']) <= names:
                dropped.append(item['id'])
                continue
            raise PylonError(f'{item["id"]} is only partly taken; split it by hand')
        kept.append(block)
    _check_models(root, taken)
    ids = {tomllib.loads(b)['objects'][0]['id'] for b in kept}
    if any(p['object'] in ids for p in taken):
        raise PylonError('a taken pylon already has an object')
    body = [b.strip('\n') for b in kept] + [block_text(p) for p in taken]
    return head.rstrip('\n') + '\n\n' + '\n\n'.join(body) + '\n'


def _check_models(root: Path, taken: list[dict]) -> None:
    assets, _ = records.discover(root)
    known = {a.id for a in assets}
    missing = sorted(p['model'] for p in taken if p['model'] not in known)
    if missing:
        raise PylonError(f'no record for {missing}; a pylon needs its existing mesh record')


def paths(taken: list[dict]) -> list[str]:
    """Repository paths a claim for this change must cover: objects.toml, and the record folders of the pylon groups it
    removes (their asset.toml and verified.json) and the new objects' folders (created by objects.py)."""
    out = [f'games/yorimichi_v2/world/regions/{REGION}/objects.toml']
    for n in (1, 2, 3):
        out.append(f'games/yorimichi_v2/assets/object/gondola/pylons-l{n}/asset.toml')
        out.append(f'games/yorimichi_v2/assets/object/gondola/pylons-l{n}/verified.json')
    out += [f'games/yorimichi_v2/assets/{p["object"]}/asset.toml' for p in taken]
    return sorted(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Plan the per-pylon gondola objects (see the module docstring).')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='exit 1 when objects.toml differs from the plan; write nothing')
    mode.add_argument('--paths', action='store_true', help='print the paths the write needs under a claim, and exit')
    mode.add_argument('--claim', metavar='TASK', help='rewrite objects.toml under this claim')
    parser.add_argument('--print', action='store_true', help='with --check, print the planned objects.toml diff')
    args = parser.parse_args(argv)
    try:
        data = runtime()
        taken = select(data)
        if args.paths:
            print(json.dumps(paths(taken), indent=1))
            return 0
        current = OBJECTS.read_text()
        planned = render(current, data)
        if args.claim:
            authority.authorize([f'games/yorimichi_v2/world/regions/{REGION}/objects.toml'], args.claim,
                                'gondola pylon objects', scopes={REGION_ID})
            OBJECTS.write_text(planned)
            print(f'objects.toml rewritten: {len(taken)} pylon object(s); run objects.py after the group retirement')
            return 0
        same = planned == current
        print('objects.toml', 'matches the plan' if same else f'differs: {len(taken)} pylon objects planned')
        if args.print and not same:
            sys.stdout.writelines(difflib.unified_diff(current.splitlines(True), planned.splitlines(True), 'committed',
                                                       'planned'))
        return 0 if same else 1
    except (PylonError, authority.Unauthorized, records.RecordError) as error:
        print(f'gondola pylons: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
