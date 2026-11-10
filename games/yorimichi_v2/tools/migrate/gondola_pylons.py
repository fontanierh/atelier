"""Replace the W18 gondola's three pylon groups with one object per support tower, in steps that each repeat safely.

    uv run python games/yorimichi_v2/tools/migrate/gondola_pylons.py --check                 # the state of the tree; writes nothing
    uv run python games/yorimichi_v2/tools/migrate/gondola_pylons.py --paths                 # every path and scope a claim needs
    uv run python games/yorimichi_v2/tools/migrate/gondola_pylons.py --claim TASK            # 1. prepare
    uv run python games/yorimichi_v2/tools/migrate/objects.py region/w18-gondola --environment region/w00-island \\
        --claim TASK --only object/gondola/pylon-l1-0 ... --only object/gondola/pylon-l3-1  # 2. save the ten (unchanged tool)
    uv run python games/yorimichi_v2/tools/migrate/gondola_pylons.py --retire --claim TASK   # 3. retire the groups

States: unprepared -> prepared (pending save) -> saved (pending retire) -> done. Each state is the tree after a step, and
a rerun of the step that produced it is a no-op.

Selection (deterministic): the `GD_L<line>_<n>_Tower` entries of gondola/runtime.json's `static` list, lines in id order and,
within a line, by straight distance from the line's lower station (the one with the lower location z), ties by name. The
first LIMIT are taken. Each gets `object/gondola/pylon-l<line>-<n>`, route = its one entry, and model = the record that
already owns its mesh (`adopted/gondola/tower-l<line>-<n>`). A pylon group is listed in objects.toml only until prepare.

1. Prepare (`--claim`): after one authorized check of every path and scope `--paths` names, one journaled write puts the ten
   pylon entries into objects.toml, takes the three group entries out, and records the pending retirement in
   world/regions/w18-gondola/pylon-retire.json: each group's record files and actor packages, and the ten replacement ids.
   The groups' records, actors and saved keys stay, so the towers are still drawn.
2. Save: objects.py saves the ten. Its saved-definition check only looks at the objects it is given, and objects.saved.json
   keeps the groups' keys, so it accepts this state. The groups' actors stay on disk, so until step 3 their towers are drawn
   twice in the map.
3. Retire (`--retire --claim`): only when every replacement has an accepted receipt: its objects.saved.json entry equals its
   definition, its record names it, and its verified.json hashes its actor packages. Then, under the journal, it deletes the
   recorded records and actor packages, drops the three group keys from objects.saved.json and deletes pylon-retire.json.

Every write goes through brinecove_split_apply.Journal (recovered first) and execute, and authority.authorize with the W18 and
W00 scopes. The manifest actor is not written by these steps; its MigratedGroups keep the tower names.
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
sys.path.insert(0, str(HERE))
import brinecove_split_apply as apply  # noqa: E402  (Journal and execute: the journaled write every migrate step uses)
import group_split  # noqa: E402  (the shared prepare/save/retire lifecycle)
import objects  # noqa: E402  (record_text and MANIFEST: how a saved object's record and its map manifest are written)

REGION = 'w18-gondola'
REGION_ID = f'region/{REGION}'
ENVIRONMENT = 'region/w00-island'
SCOPES = {REGION_ID, ENVIRONMENT}
REGION_REL = f'world/regions/{REGION}'
OBJECTS_REL = f'{REGION_REL}/objects.toml'
SAVED_REL = f'{REGION_REL}/objects.saved.json'
PENDING = 'pylon-retire.json'
PENDING_REL = f'{REGION_REL}/{PENDING}'
DATA_REL = 'unreal/Content/Data/gondola/runtime.json'
LIMIT = 20   # the most pylons this makes objects; the file holds 10, so every tower is taken
MIN = 10     # fewer towers than this means the runtime file changed shape: refuse
TOWER = re.compile(r'GD_L(\d+)_(\d+)_Tower$')
GROUP = re.compile(r'object/gondola/pylons-l(\d+)$')
PYLON = re.compile(r'object/gondola/pylon-l\d+-\d+$')
GROUP_IDS = [f'object/gondola/pylons-l{n}' for n in (1, 2, 3)]


class PylonError(RuntimeError):
    pass


def runtime(game: Path) -> dict:
    path = game / DATA_REL
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


def tower_models_exist(game: Path, taken: list[dict]) -> None:
    missing = sorted(p['model'] for p in taken if not (game / 'assets' / p['model'] / 'asset.toml').is_file())
    if missing:
        raise PylonError(f'no record for {missing}; a pylon needs its existing mesh record')


def render(text: str, data: dict, game: Path = GAME) -> str:
    """objects.toml with the taken pylons as objects of their own and their emptied groups removed."""
    head, *blocks = re.split(r'(?m)^(?=\[\[objects\]\])', text)
    taken = select(data)
    names = {p['name'] for p in taken}
    kept = []
    for block in blocks:
        item = tomllib.loads(block)['objects'][0]
        if GROUP.match(item['id']):
            if set(item['route']) <= names:
                continue
            raise PylonError(f'{item["id"]} is only partly taken; split it by hand')
        kept.append(block)
    tower_models_exist(game, taken)
    ids = {tomllib.loads(b)['objects'][0]['id'] for b in kept}
    if any(p['object'] in ids for p in taken):
        raise PylonError('a taken pylon already has an object')
    body = [b.strip('\n') for b in kept] + [block_text(p) for p in taken]
    return head.rstrip('\n') + '\n\n' + '\n\n'.join(body) + '\n'


# --- the shared lifecycle (group_split.py) -------------------------------------------------------------------------------

SPLIT = group_split.Split(
    region=REGION, pending=PENDING, group=GROUP, group_ids=tuple(GROUP_IDS), is_replacement=lambda i: bool(PYLON.match(i)),
    error=PylonError, label='gondola pylon', noun='pylon',
    unprepared=lambda groups: f'{len(groups)} pylon group(s) listed; prepare with --claim',
    done=lambda wanted: 'the groups are retired and the ten pylon objects are listed')


def saved_definition(item: dict) -> dict:
    return group_split.saved_definition(item)


def pending_of(game: Path) -> dict | None:
    return group_split.pending_of(SPLIT, game)


def receipt_ok(game: Path, pid: str, item: dict, saved: dict) -> bool:
    return group_split.receipt_ok(game, pid, item, saved)


def state(game: Path, taken: list[dict]) -> tuple[str, str]:
    return group_split.state(SPLIT, game, taken)


def claim_paths(game: Path, taken: list[dict]) -> dict:
    return group_split.claim_paths(SPLIT, game, taken)


def prepare(game: Path, taken: list[dict], claim: str, *, lockable=None, echo=print) -> str:
    """Step 1 (group_split.prepare), rendering objects.toml from the runtime data file."""
    return group_split.prepare(SPLIT, game, taken, claim, lambda text: render(text, runtime(game), game), lockable=lockable, echo=echo)


def retire(game: Path, taken: list[dict], claim: str, *, lockable=None, echo=print) -> str:
    """Step 3 (group_split.retire): only once every replacement has an accepted receipt."""
    return group_split.retire(SPLIT, game, taken, claim, lockable=lockable, echo=echo)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Replace the gondola pylon groups with per-tower objects (see the docstring).')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='print the state of the tree; writes nothing')
    mode.add_argument('--paths', action='store_true', help='print the paths and scopes a claim must cover, and exit')
    mode.add_argument('--retire', action='store_true', help='retire the groups; with --claim TASK (step 3)')
    parser.add_argument('--claim', metavar='TASK', help='claims task: alone, prepare (step 1); with --retire, retire (step 3)')
    parser.add_argument('--print', action='store_true', help='with --check, print the planned objects.toml diff')
    args = parser.parse_args(argv)
    try:
        data = runtime(GAME)
        taken = select(data)
        if args.claim and (args.check or args.paths):
            raise PylonError('--check and --paths write nothing and take no --claim')
        if args.paths:
            print(json.dumps(claim_paths(GAME, taken), indent=1))
            return 0
        if args.retire:
            if not args.claim:
                raise PylonError('--retire needs --claim TASK')
            retire(GAME, taken, args.claim)
            return 0
        if args.claim:
            prepare(GAME, taken, args.claim)
            return 0
        current, why = state(GAME, taken)
        print(f'state: {current}; {why}')
        if args.print and current == 'unprepared':
            planned = render((GAME / OBJECTS_REL).read_text(), data, GAME)
            sys.stdout.writelines(difflib.unified_diff((GAME / OBJECTS_REL).read_text().splitlines(True),
                                                       planned.splitlines(True), 'committed', 'planned'))
        return 0
    except (PylonError, records.RecordError, apply.SplitError) as error:
        print(f'gondola pylons: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
