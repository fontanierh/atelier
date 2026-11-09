"""Plan the W18 gondola's pylons as objects of their own: one object per support tower, not one per line.

    uv run python games/yorimichi_v2/tools/migrate/gondola_pylons.py --check        # compare, write nothing
    uv run python games/yorimichi_v2/tools/migrate/gondola_pylons.py --paths        # the paths a claim must cover
    uv run python games/yorimichi_v2/tools/migrate/gondola_pylons.py --claim TASK   # retire the groups, write the pylons
    uv run python games/yorimichi_v2/tools/migrate/objects.py region/w18-gondola --environment region/w00-island \
        --claim TASK --only object/gondola/pylon-l1-0 ... --only object/gondola/pylon-l3-1   # save the ten objects

Selection (deterministic): the `GD_L<line>_<n>_Tower` entries of gondola/runtime.json's `static` list, lines in id order and,
within a line, by straight distance from the line's lower station (the one with the lower location z), ties by name. The
first LIMIT are taken. Each gets `object/gondola/pylon-l<line>-<n>`, route = its one entry, and model = the record that
already owns its mesh (`adopted/gondola/tower-l<line>-<n>`). No new record is needed: objects.py writes each object's
asset.toml when it saves the object.

A pylon group (object/gondola/pylons-l<line>) is removed from objects.toml when every one of its towers is taken; a group
only partly taken is refused. Station objects, and every other line of the file, are kept byte for byte.

The `--claim` step is one journaled write (brinecove_split_apply.Journal and execute, as brinecove_ships retires its
placements): it deletes the three groups' record folders and actor packages, drops their keys from objects.saved.json,
and writes objects.toml. Nothing else changes. The manifest actor is not written here; its MigratedGroups keep the tower
names, so objects.py's save, which must follow in the same claim, lists the same names again. Until that save runs the
towers are skipped by the runtime and not drawn. `--paths` lists the step's paths and the save's paths; a claim covers both.
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
import objects  # noqa: E402  (MANIFEST: the map manifest a save lists its groups in)

REGION = 'w18-gondola'
REGION_ID = 'region/w18-gondola'
DATA = GAME / 'unreal/Content/Data/gondola/runtime.json'
REGION_FOLDER = GAME / 'world/regions' / REGION
OBJECTS = REGION_FOLDER / 'objects.toml'
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


# --- retire the three pylon groups, then the write -----------------------------------------------------------------------

def saved_definition(item: dict) -> dict:
    """What objects.saved.json records for an object (objects.py's definition: its entry without `about`, with the models
    and groups load_objects derives)."""
    models = [item['model']] if isinstance(item['model'], str) else list(item['model'])
    return {'id': item['id'], 'route': list(item['route']), 'model': item['model'], 'models': models, 'groups': []}


def retire_plan(game: Path, taken: list[dict], objects_text: str, saved_text: str) -> dict:
    """Everything the step does, computed in memory and checked before any byte is written.

    Each pylon group listed in objects.toml must be fully taken; its record (asset.toml) must be the object's own and name
    the same models; its objects.saved.json entry must equal its objects.toml definition; its actor packages must exist.
    Writes: objects.toml (the taken towers as objects, the groups gone) and objects.saved.json (the groups' keys dropped).
    Deletes: the groups' record folders and their actor packages. Nothing else is touched."""
    items = tomllib.loads(objects_text).get('objects', [])
    groups = [i for i in items if GROUP.match(i['id'])]
    if not groups:
        raise PylonError('no pylon group is listed in objects.toml; nothing to retire')
    body = json.loads(saved_text)
    saved = body.get('objects', {})
    deletes, scopes = [], {f'region/{REGION}'}
    for item in groups:
        gid = item['id']
        folder = game / 'assets' / gid
        record = folder / 'asset.toml'
        if not record.is_file():
            raise PylonError(f'{gid}: its record {record.relative_to(game)} is missing')
        asset = records.load_asset(record)
        if asset.id != gid or sorted(asset.references) != sorted(saved_definition(item)['models']):
            raise PylonError(f'{gid}: its record does not name this group or its models')
        if gid not in saved or saved[gid] != saved_definition(item):
            raise PylonError(f'{gid}: objects.saved.json does not record its objects.toml definition')
        scopes.add(authority.asset_scope(asset))
        for path in sorted(folder.rglob('*')):
            if path.is_file():
                deletes.append(path.relative_to(game).as_posix())
        for output in asset.outputs:
            found = [rel for rel in apply.package_rels(game, output.package) if (game / rel).is_file()]
            if not any(rel.endswith('.uasset') or rel.endswith('.umap') for rel in found):
                raise PylonError(f'{gid}: its actor package {output.package} is missing')
            deletes.extend(found)
    for p in taken:
        if p['object'] in saved:
            raise PylonError(f'{p["object"]} is already saved')
    deletes = sorted(set(deletes))
    listed = {k: v for k, v in saved.items() if k not in {g['id'] for g in groups}}
    saved_out = json.dumps({**body, 'objects': listed}, indent=2, sort_keys=True) + '\n'
    return {'deletes': deletes, 'saved_text': saved_out, 'scopes': scopes,
            'groups': [g['id'] for g in groups]}


def step_paths(game: Path, taken: list[dict]) -> dict:
    """{'step': the paths the retire-and-write step touches, 'save': the paths objects.py's later save needs}. A claim must
    cover both: the step's own writes, and the save that must follow it in the same claim (its manifest actor included,
    as objects.py's claim_paths lists it for --environment region/w00-island)."""
    region = f'games/yorimichi_v2/world/regions/{REGION}'
    step = {f'{region}/objects.toml', f'{region}/objects.saved.json'}
    folder = game / 'world/regions' / REGION
    retire = retire_plan(game, taken, (folder / 'objects.toml').read_text(), (folder / 'objects.saved.json').read_text())
    step |= {f'games/yorimichi_v2/{rel}' for rel in retire['deletes']}
    save = {f'games/yorimichi_v2/assets/{p["object"]}/{name}' for p in taken for name in ('asset.toml', 'verified.json')}
    save.add(f'games/yorimichi_v2/{objects.MANIFEST["region/w00-island"]}')
    return {'step': sorted(step), 'save': sorted(save)}


def apply_step(game: Path, taken: list[dict], claim: str, *, echo=print) -> dict:
    """The one journaled, authorized step: recover any interrupted run first, then write objects.toml and the saved list
    and delete the groups' records and packages. Any failure before the write raises with nothing changed."""
    apply.Journal(game).recover(claim)
    folder = game / 'world/regions' / REGION
    current = (folder / 'objects.toml').read_text()
    planned = render(current, runtime(), root=game)
    plan = retire_plan(game, taken, current, (folder / 'objects.saved.json').read_text())
    region = f'games/yorimichi_v2/world/regions/{REGION}'
    rels = [f'{region}/objects.toml', f'{region}/objects.saved.json'] + [f'games/yorimichi_v2/{r}' for r in plan['deletes']]
    try:
        authority.authorize(sorted(rels), claim, 'gondola pylon split', scopes=plan['scopes'])
    except authority.Unauthorized as error:
        raise PylonError(str(error)) from None
    writes = {f'world/regions/{REGION}/objects.toml': planned.encode(),
              f'world/regions/{REGION}/objects.saved.json': plan['saved_text'].encode()}
    ops = {'writes': writes, 'deletes': plan['deletes']}
    apply.execute(game, ops, scopes=plan['scopes'], lockable=lambda g, rels_: apply.lockable_present(g, rels_))
    echo(f'retired {", ".join(plan["groups"])}; wrote {len(taken)} pylon object(s) into objects.toml; '
         f'deleted {len(plan["deletes"])} file(s)')
    return plan


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Plan the per-pylon gondola objects (see the module docstring).')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='exit 1 when objects.toml differs from the plan; write nothing')
    mode.add_argument('--paths', action='store_true', help='print the paths the claim must cover (step and save), and exit')
    mode.add_argument('--claim', metavar='TASK', help='retire the three pylon groups and write the pylon objects under this claim')
    parser.add_argument('--print', action='store_true', help='with --check, print the planned objects.toml diff')
    args = parser.parse_args(argv)
    try:
        data = runtime()
        taken = select(data)
        if args.paths:
            print(json.dumps(step_paths(GAME, taken), indent=1))
            return 0
        current = OBJECTS.read_text()
        if args.claim:
            apply_step(GAME, taken, args.claim)
            return 0
        planned = render(current, data)
        same = planned == current
        print('objects.toml', 'matches the plan' if same else f'differs: {len(taken)} pylon objects planned')
        if args.print and not same:
            sys.stdout.writelines(difflib.unified_diff(current.splitlines(True), planned.splitlines(True), 'committed',
                                                       'planned'))
        return 0 if same else 1
    except (PylonError, authority.Unauthorized, records.RecordError, apply.SplitError) as error:
        print(f'gondola pylons: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
