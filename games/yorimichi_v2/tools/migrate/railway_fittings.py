"""Split the W20 railway's track-fittings group into one object per fitting (12), in steps that each repeat safely.

    uv run python games/yorimichi_v2/tools/migrate/railway_fittings.py --check                 # the state of the tree; writes nothing
    uv run python games/yorimichi_v2/tools/migrate/railway_fittings.py --ids                   # the twelve object ids, in order; writes nothing
    uv run python games/yorimichi_v2/tools/migrate/railway_fittings.py --paths                 # every path and scope a claim needs
    uv run python games/yorimichi_v2/tools/migrate/railway_fittings.py --claim TASK            # 1. prepare
    uv run python games/yorimichi_v2/tools/migrate/objects.py region/w20-railway --environment region/w00-island \\
        --claim TASK --only object/railway/buffer-stop-0 ... --only object/railway/tunnel-portal-5   # 2. save the twelve
        (unchanged tool; one --only per id that --ids prints)
    uv run python games/yorimichi_v2/tools/migrate/railway_fittings.py --retire --claim TASK   # 3. retire the group

States: unprepared -> prepared (pending save) -> saved (pending retire) -> done. Each state is the tree after a step, and
a rerun of the step that produced it is a no-op.

Scope: the twelve individual fittings of track.json, each its own object with its own route, selection and saved placement.
Rendering stays batched: a group that has no saved row is still one component per mesh in the runtime.

Stable keys: every fitting is row `i` of its mesh's group (one group per mesh, key "": SM_TK_BufferStop#, SM_TK_StopBoard#,
SM_TK_Turnout#, SM_TK_Portal#). Its route name is "<mesh>#<key>@<i>" with `i` the row's index in the group's `instances`
array as track.json writes it (0-based), so the names are "SM_TK_BufferStop#@0", "SM_TK_BufferStop#@1", ..., "SM_TK_Portal#@5".
The "@" is the sub-unit separator towns.py already uses ("<key>@<x>_<y>"). The index is the file's own order: the names hold
while track.json is unchanged, and select() refuses a file whose count per mesh differs (a regenerated file is a new split).
UV2MigrationTravel::MigrateRailwayPieces saves one row of a group as its own patch (a group is still saved whole when its
name is routed), and BelmonteTrack.cpp skips a row the manifest lists as "railway:<mesh>#<key>@<i>" and builds the rest.

Selection (deterministic): the twelve rows, in the track-fittings group's route order, then row order: buffer stops 0-1, stop
boards 0-1, turnouts 0-1, tunnel portals 0-5. Each becomes `object/railway/<kind>-<i>` (kinds buffer-stop, stop-board, turnout,
tunnel-portal) with route = ["<mesh>#@<i>"] and model = adopted/belmontetrack/track-small (the record that already owns the
mesh). The track-fittings group is listed in objects.toml only until prepare.

1. Prepare (`--claim`): after one authorized check of every path and scope `--paths` names, one journaled write puts the twelve
   fitting objects into objects.toml, takes the track-fittings entry out, and records the pending retirement in
   world/regions/w20-railway/fittings-retire.json: the group's record files and actor packages, and the twelve replacement ids.
   The group's record, actor and saved key stay, so its fittings are still drawn.
2. Save: objects.py saves the twelve, one patch each. Its saved-definition check only looks at the objects it is given, and
   objects.saved.json keeps the group's key, so it accepts this state. Once the manifest lists a row, the runtime skips that
   row, so a fitting is drawn once, from its own object (the group's other rows, if any, stay batched).
3. Retire (`--retire --claim`): only when every replacement has an accepted receipt: its objects.saved.json entry equals its
   definition, its record names it, and its verified.json hashes its actor package. Then, under the journal, it deletes the
   group's record files and actor packages, drops its key from objects.saved.json and deletes fittings-retire.json.

Every write goes through brinecove_split_apply.Journal (recovered first) and execute, and authority.authorize with the W20 and
W00 scopes. The manifest entries are written by objects.py's save, not by these steps: they name "railway:<mesh>#@<i>" for the
twelve rows. ClimbExempt (source keys "railway:") is unchanged. The track pieces, the chunk, sleeper, lamp and tunnel objects,
the station, overbridge, viaducts and banks, and the route data (train service) are not touched. track.json is not changed.
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

REGION = 'w20-railway'
REGION_ID = f'region/{REGION}'
ENVIRONMENT = 'region/w00-island'
SCOPES = {REGION_ID, ENVIRONMENT}
REGION_REL = f'world/regions/{REGION}'
OBJECTS_REL = f'{REGION_REL}/objects.toml'
SAVED_REL = f'{REGION_REL}/objects.saved.json'
PENDING = 'fittings-retire.json'
PENDING_REL = f'{REGION_REL}/{PENDING}'
DATA_REL = 'unreal/Content/Data/belmonte_track/track.json'
MODEL = 'adopted/belmontetrack/track-small'
GROUP_ID = 'object/railway/track-fittings'
GROUP_ROUTE = ['SM_TK_BufferStop#', 'SM_TK_StopBoard#', 'SM_TK_Turnout#', 'SM_TK_Portal#']
GROUP = re.compile(r'object/railway/track-fittings$')
# (mesh, object slug, about): the group's route entries in its written order. Each row of a mesh's group is one object.
FITTINGS = (
    ('SM_TK_BufferStop', 'buffer-stop', 'a buffer stop at one end of the track'),
    ('SM_TK_StopBoard', 'stop-board', 'a stop board beside a buffer stop or platform'),
    ('SM_TK_Turnout', 'turnout', 'a track turnout (points) of the line'),
    ('SM_TK_Portal', 'tunnel-portal', 'a tunnel portal, the face of a tunnel mouth'),
)
# Row counts are the runtime file's (every mesh is one group with key ""); select() refuses a file that differs.
COUNTS = {'SM_TK_BufferStop': 2, 'SM_TK_StopBoard': 2, 'SM_TK_Turnout': 2, 'SM_TK_Portal': 6}
FITTING_IDS = {f'object/railway/{slug}-{row}' for mesh, slug, _ in FITTINGS for row in range(COUNTS[mesh])}
MIN_ROW_VALUES = 5   # a fitting row is [x, y, z, yaw, scale], as BelmonteTrack.cpp reads it


class FittingsError(RuntimeError):
    pass


def runtime(game: Path) -> dict:
    path = game / DATA_REL
    if not path.is_file() or records.is_lfs_pointer(path):
        raise FittingsError(f'{path} is missing or still a Git LFS pointer; fetch the data first')
    return json.loads(path.read_text())


def select(data: dict) -> list[dict]:
    """The twelve fitting objects, in the group's route order then row order: {name, mesh, object, about, model, row} each.
    name is the route entry "<mesh>#<key>@<row>" (key "" for every mesh)."""
    groups = {}
    for group in data['instances']:
        groups[f'{group["mesh"].rsplit("/", 1)[-1].split(".")[0]}#{group["key"]}'] = group
    taken = []
    for mesh, slug, about in FITTINGS:
        name = f'{mesh}#'
        group = groups.get(name)
        if group is None:
            raise FittingsError(f'{name} is no instanced group of {DATA_REL} (key "" per mesh)')
        rows = group['instances']
        if len(rows) != COUNTS[mesh]:
            raise FittingsError(f'{name} holds {len(rows)} fittings, {COUNTS[mesh]} expected')
        for row, values in enumerate(rows):
            if len(values) < MIN_ROW_VALUES:
                raise FittingsError(f'{name}@{row} is not a fitting row (five values expected)')
            taken.append({'name': f'{name}@{row}', 'mesh': mesh, 'object': f'object/railway/{slug}-{row}',
                          'about': f'{about}, {row + 1} of {len(rows)}', 'model': MODEL, 'row': row})
    if list(dict.fromkeys(t['name'].split('@')[0] for t in taken)) != GROUP_ROUTE:
        raise FittingsError('the split does not follow the track-fittings route order')
    return taken


def block_text(kind: dict) -> str:
    return '\n'.join([
        '[[objects]]', f'id = "{kind["object"]}"', f'route = ["{kind["name"]}"]', f'model = "{kind["model"]}"',
        f'about = "{kind["about"]}, saved on their own"',
    ])


def saved_definition(item: dict) -> dict:
    """What objects.saved.json records for an object: objects.py's definition (its entry without `about`, with the models and
    groups load_objects derives)."""
    models = [item['model']] if isinstance(item['model'], str) else list(item['model'])
    return {'id': item['id'], 'route': list(item['route']), 'model': item['model'], 'models': models, 'groups': []}


def model_exists(game: Path, taken: list[dict]) -> None:
    if not (game / 'assets' / MODEL / 'asset.toml').is_file():
        raise FittingsError(f'no record for {MODEL}; a fitting needs its existing mesh record')


def render(text: str, data: dict, game: Path = GAME) -> str:
    """objects.toml with the twelve fittings as objects of their own and the track-fittings entry removed."""
    head, *blocks = re.split(r'(?m)^(?=\[\[objects\]\])', text)
    taken = select(data)
    names = [t['name'] for t in taken]
    kept = []
    for block in blocks:
        item = tomllib.loads(block)['objects'][0]
        if GROUP.match(item['id']):
            if list(item['route']) != GROUP_ROUTE:
                raise FittingsError(f'{item["id"]} is not the four-entry group as written; split it by hand')
            continue
        kept.append(block)
    model_exists(game, taken)
    kept_items = [tomllib.loads(b)['objects'][0] for b in kept]
    ids = {item['id'] for item in kept_items}
    routed = {name for item in kept_items for name in item['route']}
    if any(t['object'] in ids for t in taken) or routed & set(names):
        raise FittingsError('a taken fitting already has an object')
    body = [b.strip('\n') for b in kept] + [block_text(t) for t in taken]
    return head.rstrip('\n') + '\n\n' + '\n\n'.join(body) + '\n'


# --- the files a step names ----------------------------------------------------------------------------------------------

def pending_of(game: Path) -> dict | None:
    path = game / PENDING_REL
    if not path.is_file():
        return None
    try:
        body = json.loads(path.read_text())
    except ValueError as error:
        raise FittingsError(f'{PENDING_REL} is not JSON: {error}') from None
    if body.get('schema') != 1 or set(body) != {'schema', 'groups', 'replacements'}:
        raise FittingsError(f'{PENDING_REL} has an unknown shape')
    return body


def pending_text(pending: dict) -> str:
    return json.dumps(pending, indent=2, sort_keys=True) + '\n'


def group_listing(game: Path, gid: str) -> dict:
    """The group's record and its files and actor packages as they are on disk: what retirement deletes."""
    folder = game / 'assets' / gid
    asset = records.load_asset(folder / 'asset.toml')
    files = [p.relative_to(game).as_posix() for p in sorted(folder.rglob('*')) if p.is_file()]
    packages = []
    for output in asset.outputs:
        packages += [rel for rel in apply.package_rels(game, output.package) if (game / rel).is_file()]
    if not any(rel.endswith(records.PACKAGE_EXTENSIONS) for rel in packages):
        raise FittingsError(f'{gid}: its actor package {[o.package for o in asset.outputs]} is missing')
    return {'files': files, 'packages': sorted(set(packages))}


def group_checks(game: Path, items: list[dict], saved: dict) -> None:
    """The listed group: its record names it and its model, and objects.saved.json records its definition."""
    for item in items:
        gid = item['id']
        record = game / 'assets' / gid / 'asset.toml'
        if not record.is_file():
            raise FittingsError(f'{gid}: its record {record.relative_to(game)} is missing')
        asset = records.load_asset(record)
        if asset.id != gid or sorted(asset.references) != sorted(saved_definition(item)['models']):
            raise FittingsError(f'{gid}: its record does not name this group or its models')
        if saved.get(gid) != saved_definition(item):
            raise FittingsError(f'{gid}: objects.saved.json does not record its objects.toml definition')


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
    listed = {i for i in objects_now if i in FITTING_IDS}
    wanted = {t['object'] for t in taken}
    pending = pending_of(game)
    if pending is None:
        if groups and not listed:
            return 'unprepared', 'the track-fittings group is listed; prepare with --claim'
        group_left = (game / 'assets' / GROUP_ID / 'asset.toml').is_file() or GROUP_ID in saved
        if not groups and wanted <= listed and not group_left:
            return 'done', f'the group is retired and the {len(wanted)} fitting objects are listed'
        raise FittingsError('objects.toml, objects.saved.json and the group record disagree and no pending file explains it')
    if groups or set(pending['replacements']) != listed:
        raise FittingsError(f'{PENDING_REL} does not match objects.toml')
    for gid in pending['groups']:
        if gid not in saved or not (game / 'assets' / gid / 'asset.toml').is_file():
            raise FittingsError(f'{gid} is pending retirement but its saved entry or record is gone')
    missing = [pid for pid in sorted(wanted) if not receipt_ok(game, pid, objects_now[pid], saved)]
    if missing:
        return 'prepared', f'{len(missing)} replacement(s) without an accepted receipt, e.g. {missing[0]}'
    return 'saved', f'all {len(wanted)} replacements have accepted receipts; retire with --retire --claim'


def claim_paths(game: Path, taken: list[dict]) -> dict:
    """Every path and scope the steps touch, for one claim: the W20 objects, the pending file, the group's record and actor
    packages (as the pending file or the disk names them), the twelve replacement records, and the manifest objects.py lists."""
    pending = pending_of(game)
    if pending is not None:
        listing = {g: {'files': v['files'], 'packages': v['packages']} for g, v in pending['groups'].items()}
    else:
        listing = {GROUP_ID: group_listing(game, GROUP_ID)} if (game / 'assets' / GROUP_ID / 'asset.toml').is_file() else {}
    rels = {OBJECTS_REL, SAVED_REL, PENDING_REL}
    for entry in listing.values():
        rels |= set(entry['files']) | set(entry['packages'])
    for t in taken:
        rels |= {f'assets/{t["object"]}/asset.toml', f'assets/{t["object"]}/verified.json'}
    rels.add(objects.MANIFEST[ENVIRONMENT])
    return {'paths': sorted(f'games/yorimichi_v2/{r}' for r in rels), 'scopes': sorted(SCOPES)}


def authorize(game: Path, taken: list[dict], claim: str | None, what: str) -> None:
    """The complete claim, checked before any byte of the step is written."""
    plan = claim_paths(game, taken)
    try:
        authority.authorize(plan['paths'], claim, what, scopes=SCOPES)
    except authority.Unauthorized as error:
        raise FittingsError(str(error)) from None


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
    listed = {GROUP_ID: group_listing(game, GROUP_ID)}
    saved = saved_of(game)
    group_checks(game, [i for i in objects_of(game).values() if GROUP.match(i['id'])], saved)
    pending = {'schema': 1, 'groups': listed, 'replacements': sorted(t['object'] for t in taken)}
    authorize(game, taken, claim, 'railway fittings prepare')
    ops = {'writes': {OBJECTS_REL: objects_out.encode(), PENDING_REL: pending_text(pending).encode()}, 'deletes': []}
    apply.execute(game, ops, scopes=SCOPES, **({'lockable': lockable} if lockable else {}))
    echo(f'prepare: {len(pending["replacements"])} fitting objects listed; {len(listed)} group pending retirement')
    return 'prepared'


def retire(game: Path, taken: list[dict], claim: str, *, lockable=None, echo=print) -> str:
    """Step 3. Refuses, changing nothing, unless every replacement has an accepted receipt. A rerun after it is a no-op."""
    apply.Journal(game).recover(claim)
    current, why = state(game, taken)
    if current == 'done':
        echo(f'retire: already done ({why}); nothing written')
        return current
    if current != 'saved':
        raise FittingsError(f'retire refused: the fitting objects are {current} ({why}); nothing changed')
    pending = pending_of(game)
    saved = saved_of(game)
    deletes = {PENDING_REL}
    for gid, listing in pending['groups'].items():
        deletes |= {rel for rel in listing['files'] + listing['packages'] if (game / rel).is_file()}
        saved.pop(gid, None)
    body = json.loads((game / SAVED_REL).read_text())
    body['objects'] = saved
    authorize(game, taken, claim, 'railway fittings retire')
    ops = {'writes': {SAVED_REL: (json.dumps(body, indent=2, sort_keys=True) + '\n').encode()},
           'deletes': sorted(deletes)}
    apply.execute(game, ops, scopes=SCOPES, **({'lockable': lockable} if lockable else {}))
    echo(f'retire: {len(pending["groups"])} group(s) removed; {len(deletes) - 1} file(s) deleted')
    return 'done'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Split the railway track-fittings group into one object per fitting (see the docstring).')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='print the state of the tree; writes nothing')
    mode.add_argument('--ids', action='store_true', help='print the twelve object ids in order, and exit; writes nothing')
    mode.add_argument('--paths', action='store_true', help='print the paths and scopes a claim must cover, and exit')
    mode.add_argument('--retire', action='store_true', help='retire the group; with --claim TASK (step 3)')
    parser.add_argument('--claim', metavar='TASK', help='claims task: alone, prepare (step 1); with --retire, retire (step 3)')
    parser.add_argument('--print', action='store_true', help='with --check, print the planned objects.toml diff')
    args = parser.parse_args(argv)
    try:
        data = runtime(GAME)
        taken = select(data)
        if args.claim and (args.check or args.paths or args.ids):
            raise FittingsError('--check, --ids and --paths write nothing and take no --claim')
        if args.ids:
            print('\n'.join(t['object'] for t in taken))
            return 0
        if args.paths:
            print(json.dumps(claim_paths(GAME, taken), indent=1))
            return 0
        if args.retire:
            if not args.claim:
                raise FittingsError('--retire needs --claim TASK')
            retire(GAME, taken, args.claim)
            return 0
        if args.claim:
            prepare(GAME, taken, args.claim)
            return 0
        current, why = state(GAME, taken)
        print(f'state: {current}; {why}')
        if args.print and current == 'unprepared':
            before = (GAME / OBJECTS_REL).read_text()
            sys.stdout.writelines(difflib.unified_diff(before.splitlines(True), render(before, data, GAME).splitlines(True),
                                                       'committed', 'planned'))
        return 0
    except (FittingsError, records.RecordError, apply.SplitError) as error:
        print(f'railway fittings: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
