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


def saved_definition(item: dict) -> dict:
    """What objects.saved.json records for an object: objects.py's definition (its entry without `about`, with the models and
    groups load_objects derives)."""
    models = [item['model']] if isinstance(item['model'], str) else list(item['model'])
    return {'id': item['id'], 'route': list(item['route']), 'model': item['model'], 'models': models, 'groups': []}


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


# --- the files a step names ----------------------------------------------------------------------------------------------

def pending_of(game: Path) -> dict | None:
    path = game / PENDING_REL
    if not path.is_file():
        return None
    try:
        body = json.loads(path.read_text())
    except ValueError as error:
        raise PylonError(f'{PENDING_REL} is not JSON: {error}') from None
    if body.get('schema') != 1 or set(body) != {'schema', 'groups', 'replacements'}:
        raise PylonError(f'{PENDING_REL} has an unknown shape')
    return body


def pending_text(pending: dict) -> str:
    return json.dumps(pending, indent=2, sort_keys=True) + '\n'


def group_listing(game: Path, gid: str) -> dict:
    """A group's record and its files and actor packages as they are on disk: what retirement deletes."""
    folder = game / 'assets' / gid
    asset = records.load_asset(folder / 'asset.toml')
    files = [p.relative_to(game).as_posix() for p in sorted(folder.rglob('*')) if p.is_file()]
    packages = []
    for output in asset.outputs:
        packages += [rel for rel in apply.package_rels(game, output.package) if (game / rel).is_file()]
    if not any(rel.endswith(records.PACKAGE_EXTENSIONS) for rel in packages):
        raise PylonError(f'{gid}: its actor package {[o.package for o in asset.outputs]} is missing')
    return {'files': files, 'packages': sorted(set(packages))}


def group_checks(game: Path, items: list[dict], saved: dict) -> None:
    """Each listed group: its record names it and its models, and objects.saved.json records its definition."""
    for item in items:
        gid = item['id']
        record = game / 'assets' / gid / 'asset.toml'
        if not record.is_file():
            raise PylonError(f'{gid}: its record {record.relative_to(game)} is missing')
        asset = records.load_asset(record)
        if asset.id != gid or sorted(asset.references) != sorted(saved_definition(item)['models']):
            raise PylonError(f'{gid}: its record does not name this group or its models')
        if saved.get(gid) != saved_definition(item):
            raise PylonError(f'{gid}: objects.saved.json does not record its objects.toml definition')


def saved_of(game: Path) -> dict:
    path = game / SAVED_REL
    return json.loads(path.read_text()).get('objects', {}) if path.is_file() else {}


def objects_of(game: Path) -> dict:
    return {i['id']: i for i in tomllib.loads((game / OBJECTS_REL).read_text()).get('objects', [])}


def receipt_ok(game: Path, pid: str, item: dict, saved: dict) -> bool:
    """A replacement's accepted receipt: its saved entry equals its definition, its record names it, and its verified.json
    hashes each of its actor packages as they are on disk."""
    if saved.get(pid) != saved_definition(item):
        return False
    record, verified = game / 'assets' / pid / 'asset.toml', game / 'assets' / pid / 'verified.json'
    if not record.is_file() or not verified.is_file():
        return False
    asset = records.load_asset(record)
    if asset.id != pid or not asset.outputs:
        return False
    files = json.loads(verified.read_text()).get('files', {})
    for output in asset.outputs:
        path = next((p for p in records.package_files(game, output.package) if p.is_file()), None)
        if path is None or files.get(path.relative_to(game).as_posix()) != records.sha256_file(path):
            return False
    return True


# --- the states --------------------------------------------------------------------------------------------------------

def state(game: Path, taken: list[dict]) -> tuple[str, str]:
    """(state, detail) of the tree: unprepared, prepared, saved, or done. Refuses a tree no step explains."""
    objects_now, saved = objects_of(game), saved_of(game)
    groups = [i for i in objects_now.values() if GROUP.match(i['id'])]
    pylons_listed = {i for i in objects_now if PYLON.match(i)}
    wanted = {p['object'] for p in taken}
    pending = pending_of(game)
    if pending is None:
        if groups and not pylons_listed:
            return 'unprepared', f'{len(groups)} pylon group(s) listed; prepare with --claim'
        group_left = any((game / 'assets' / g / 'asset.toml').is_file() or g in saved for g in GROUP_IDS)
        if not groups and wanted <= pylons_listed and not group_left:
            return 'done', 'the groups are retired and the ten pylon objects are listed'
        raise PylonError('objects.toml, objects.saved.json and the group records disagree and no pending file explains it')
    if groups or set(pending['replacements']) != pylons_listed:
        raise PylonError(f'{PENDING_REL} does not match objects.toml')
    for gid in pending['groups']:
        if gid not in saved or not (game / 'assets' / gid / 'asset.toml').is_file():
            raise PylonError(f'{gid} is pending retirement but its saved entry or record is gone')
    missing = [pid for pid in sorted(wanted) if not receipt_ok(game, pid, objects_now[pid], saved)]
    if missing:
        return 'prepared', f'{len(missing)} replacement(s) without an accepted receipt, e.g. {missing[0]}'
    return 'saved', f'all {len(wanted)} replacements have accepted receipts; retire with --retire --claim'


def claim_paths(game: Path, taken: list[dict]) -> dict:
    """Every path and scope the steps touch, for one claim: the W18 objects, the pending file, the groups' records and actor
    packages (as the pending file or the disk names them), the ten replacement records, and the manifest objects.py lists."""
    pending = pending_of(game)
    if pending is not None:
        listing = {g: {'files': v['files'], 'packages': v['packages']} for g, v in pending['groups'].items()}
    else:
        listing = {g: group_listing(game, g) for g in GROUP_IDS if (game / 'assets' / g / 'asset.toml').is_file()}
    rels = {OBJECTS_REL, SAVED_REL, PENDING_REL}
    for entry in listing.values():
        rels |= set(entry['files']) | set(entry['packages'])
    for p in taken:
        rels |= {f'assets/{p["object"]}/asset.toml', f'assets/{p["object"]}/verified.json'}
    rels.add(objects.MANIFEST[ENVIRONMENT])
    return {'paths': sorted(f'games/yorimichi_v2/{r}' for r in rels), 'scopes': sorted(SCOPES)}


def authorize(game: Path, taken: list[dict], claim: str | None, what: str) -> None:
    """The complete claim, checked before any byte of the step is written."""
    plan = claim_paths(game, taken)
    try:
        authority.authorize(plan['paths'], claim, what, scopes=SCOPES)
    except authority.Unauthorized as error:
        raise PylonError(str(error)) from None


# --- the steps ---------------------------------------------------------------------------------------------------------

def prepare(game: Path, taken: list[dict], claim: str, *, lockable=None, echo=print) -> str:
    """Step 1. A rerun when already prepared (or later) is a no-op. The claim is checked before any write."""
    apply.Journal(game).recover(claim)
    current, why = state(game, taken)
    if current != 'unprepared':
        echo(f'prepare: already {current} ({why}); nothing written')
        return current
    text = (game / OBJECTS_REL).read_text()
    data = runtime(game)
    objects_out = render(text, data, game)
    listed, saved = group_listing_all(game), saved_of(game)
    group_checks(game, [i for i in objects_of(game).values() if GROUP.match(i['id'])], saved)
    pending = {'schema': 1, 'groups': listed, 'replacements': sorted(p['object'] for p in taken)}
    authorize(game, taken, claim, 'gondola pylon prepare')
    ops = {'writes': {OBJECTS_REL: objects_out.encode(), PENDING_REL: pending_text(pending).encode()}, 'deletes': []}
    apply.execute(game, ops, scopes=SCOPES, **({'lockable': lockable} if lockable else {}))
    echo(f'prepare: {len(pending["replacements"])} pylon objects listed; {len(listed)} group(s) pending retirement')
    return 'prepared'


def group_listing_all(game: Path) -> dict:
    listed = {}
    for item in [i for i in objects_of(game).values() if GROUP.match(i['id'])]:
        listed[item['id']] = group_listing(game, item['id'])
    return listed


def retire(game: Path, taken: list[dict], claim: str, *, lockable=None, echo=print) -> str:
    """Step 3. Refuses, changing nothing, unless every replacement has an accepted receipt. A rerun after it is a no-op."""
    apply.Journal(game).recover(claim)
    current, why = state(game, taken)
    if current == 'done':
        echo(f'retire: already done ({why}); nothing written')
        return current
    if current != 'saved':
        raise PylonError(f'retire refused: the pylon objects are {current} ({why}); nothing changed')
    pending = pending_of(game)
    saved = saved_of(game)
    deletes = set([PENDING_REL])
    for gid, listing in pending['groups'].items():
        deletes |= {rel for rel in listing['files'] + listing['packages'] if (game / rel).is_file()}
        saved.pop(gid, None)
    body = json.loads((game / SAVED_REL).read_text())
    body['objects'] = saved
    authorize(game, taken, claim, 'gondola pylon retire')
    ops = {'writes': {SAVED_REL: (json.dumps(body, indent=2, sort_keys=True) + '\n').encode()},
           'deletes': sorted(deletes)}
    apply.execute(game, ops, scopes=SCOPES, **({'lockable': lockable} if lockable else {}))
    echo(f'retire: {len(pending["groups"])} group(s) removed; {len(deletes) - 1} file(s) deleted')
    return 'done'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Replace the gondola pylon groups with per-tower objects (see the docstring).')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='print the state of the tree; writes nothing')
    mode.add_argument('--paths', action='store_true', help='print the paths and scopes a claim must cover, and exit')
    mode.add_argument('--claim', metavar='TASK', help='prepare under this claim (step 1)')
    mode.add_argument('--retire', action='store_true', help='retire the groups; with --claim TASK (step 3)')
    parser.add_argument('--print', action='store_true', help='with --check, print the planned objects.toml diff')
    args = parser.parse_args(argv)
    try:
        data = runtime(GAME)
        taken = select(data)
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
