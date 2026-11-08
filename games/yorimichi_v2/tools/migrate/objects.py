"""Save a region's named runtime scenery groups as objects of their own: one actor, one record (audit A1, A2).

    uv run python games/yorimichi_v2/tools/migrate/objects.py region/w09-brinecove --environment region/w00-island \
        --claim TASK

A region's `objects.toml` (world/regions/<name>/objects.toml) names groups of its runtime scenery file (ABelmonteRegion's
runtime.json) that are objects a person edits: the Brine Cove wreck, a galleon. The guarded editor step
`migrate.objects` (unreal/Scripts/migrate_objects.py, UV2Migration::MigrateRegionGroups) saves each as one
AV2ScenePatch built by the runtime's own component code and lists it in the map's manifest (owned by
`--environment`), so the runtime skips only those groups and the region service still runs. Each object then gets
its own record, `assets/<object id>/asset.toml` (kind placement, owner the region, its model record referenced),
validated on its own: two objects of one region are two claims and two verification files, so two people can edit
them at once. A rerun keeps every saved object as it is, edits included, and creates nothing.

The claim holds the region's and the environment's scopes, the manifest's actor package, and each object record's
two files; the created actor packages are bound to it by the build step.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parents[1]
REPO = GAME.parents[1]
sys.path.insert(0, str(GAME / 'tools/content'))
import authority  # noqa: E402
import records  # noqa: E402
import save_validate  # noqa: E402

LOG = REPO / 'build/yorimichi_v2/logs/migrate.objects.guard/stdout.log'   # the guarded editor's output
OBJECT = re.compile(r'V2 OBJECT (\S+) (\S+)')
DONE = re.compile(r'V2 OBJECTS DONE created=(\d+) kept=(\d+)')


class ObjectError(RuntimeError):
    pass


SPLIT_TOLERANCE_CM = 50.0   # a placed thing is found within this of its source point; placements lie metres apart


def load_objects(region) -> dict:
    """The region's objects.toml: {tag, data, objects: [{id, groups, patch, split, model, about}]}. An object names one
    runtime `group` or several `groups` (a statue cut into cells), each group belonging to one object; or the `patch`
    (its V2Id in the region's patches.json) the migration already saved holding it alone, which it takes over; or a
    `split` = {key, at = [x, y]}: the instances of that source key placed at that source point (metres, as in
    world.json and city.json), which leave the area patches holding them for an actor of their own."""
    path = region.folder / 'objects.toml'
    if not path.is_file():
        raise ObjectError(f'{region.id} has no objects.toml')
    data = tomllib.loads(path.read_text())
    if data.get('schema') != records.SCHEMA or not isinstance(data.get('tag'), str) or not isinstance(data.get('data'), str):
        raise ObjectError(f'{path}: needs schema = {records.SCHEMA}, tag and data')
    objects = data.get('objects', [])
    for item in objects:
        keys = set(item) - {'group', 'groups', 'patch', 'split'}
        if keys != {'id', 'model', 'about'} or len({'group', 'groups', 'patch', 'split'} & set(item)) != 1 \
                or not records.ID.match(item['id']) or not item['id'].startswith('object/'):
            raise ObjectError(f'{path}: each [[objects]] needs id = "object/...", one of group, groups, patch or '
                              f'split, model and about, not {item}')
        split = item.get('split')
        if split is not None and (not isinstance(split, dict) or set(split) != {'key', 'at'}
                                  or not isinstance(split['key'], str) or len(split['at']) != 2
                                  or not all(isinstance(v, (int, float)) for v in split['at'])):
            raise ObjectError(f'{path}: {item["id"]}: split needs key = "..." and at = [x, y], not {split}')
        item['groups'] = [item.pop('group')] if 'group' in item else list(item.get('groups', []))
    for values in ([i['patch'] for i in objects if 'patch' in i],
                   [(i['split']['key'], *i['split']['at']) for i in objects if 'split' in i]):
        if len(values) != len(set(values)):
            raise ObjectError(f'{path}: a patch or a split placement is listed twice')
    for values in ([i['id'] for i in objects], [i['id'].rsplit('/', 1)[1] for i in objects],
                   [g for i in objects for g in i['groups']]):
        if len(values) != len(set(values)):
            raise ObjectError(f'{path}: an object or group is listed twice')
    return {'tag': data['tag'], 'data': data['data'], 'objects': objects}


def record_text(item: dict, region: str, package: str) -> str:
    return '\n'.join([
        f'# One saved object of {region} (tools/migrate/objects.py, from its objects.toml): {item["about"]}.',
        f'# Its placement is this actor package; its model is {item["model"]}. Edit it in the editor and save-validate',
        '# this record: the region\'s other objects and actors are not part of it.',
        'schema = 1', f'id = "{item["id"]}"', 'kind = "placement"', 'authority = "editor"', f'owner = "{region}"',
        f'references = ["{item["model"]}"]', '', '[[outputs]]', f'package = "{package}"', ''])


def claim_paths(game: Path, region_ids: list[str], *, only=None) -> dict[str, list[str]]:
    """What a claim for these regions' objects locks and lists: {"lock": the area patch packages their split
    objects leave (every patch of each split key in patches.json), "path": each object record's two files}."""
    _, regions = records.discover(game)
    by_id = {r.id: r for r in regions}
    lock, path = set(), set()
    for rid in region_ids:
        items = [i for i in load_objects(by_id[rid])['objects'] if only is None or i['id'] in set(only)]
        keys = {i['split']['key'] for i in items if 'split' in i}
        roster = by_id[rid].folder / 'patches.json'
        patches = json.loads(roster.read_text()).get('patches', {}) if roster.is_file() else {}
        lock |= {f'games/yorimichi_v2/{e["package"]}' for e in patches.values() if e['key'] in keys}
        path |= {f'games/yorimichi_v2/assets/{i["id"]}/{name}' for i in items for name in ('asset.toml', 'verified.json')}
    return {'lock': sorted(lock), 'path': sorted(path)}


def native_run(plan_file: Path) -> str:
    env = {**os.environ, 'V2_MIGRATE_PLAN': str(plan_file)}
    LOG.unlink(missing_ok=True)
    result = subprocess.run(['nice', '-n', '10', 'uv', 'run', 'atelier', 'build', 'yorimichi_v2', 'migrate.objects'],
                            cwd=REPO, env=env)
    if result.returncode:
        raise ObjectError(f'the editor step failed (exit {result.returncode}); see {LOG}')
    return LOG.read_text(errors='replace') if LOG.is_file() else ''


def migrate(game: Path, region_ids: list[str], environment: str | None, claim: str | None, *, only=None, editor=native_run,
            out: Path = REPO / 'build/yorimichi_v2/migrate', echo=print) -> dict[str, str]:
    """Save the regions' objects (`only` these object IDs, when given) and record each; returns {object id: actor
    package}. `editor` runs the guarded editor part on the plan file and returns its log (tools/editor/session.py
    runs it in a warm editor). `environment`, the region owning the map's manifest, is needed only for runtime-group
    objects (the manifest lists their groups); split objects touch only their own regions."""
    _, regions = records.discover(game)
    by_id = {r.id: r for r in regions}
    missing = [r for r in region_ids + ([environment] if environment else []) if r not in by_id]
    if only is not None and not set(only) <= {i['id'] for r in region_ids if r in by_id
                                              for i in load_objects(by_id[r])['objects'] if 'patch' not in i}:
        raise ObjectError(f'{sorted(only)}: not all are objects of {region_ids}')
    if missing:
        raise ObjectError(f'no region record for {missing}')
    maps = {m for r in region_ids for m in by_id[r].maps}
    if len(maps) != 1:
        raise ObjectError(f'the regions must share exactly one map, not {sorted(maps)}')
    wanted, groups, splits = {}, [], []
    for rid in region_ids:
        listed = load_objects(by_id[rid])
        listed['objects'] = [item for item in listed['objects'] if 'patch' not in item]   # patch objects: promote()
        if only is not None:
            listed['objects'] = [item for item in listed['objects'] if item['id'] in set(only)]
        if not listed['objects']:
            continue
        pairs = [(g, item['id'].rsplit('/', 1)[1]) for item in listed['objects'] for g in item['groups']]
        if pairs:
            groups.append({'region': rid, 'tag': listed['tag'], 'data': listed['data'],
                           'meshes': [g for g, _ in pairs], 'objects': [o for _, o in pairs]})
        cut = [item for item in listed['objects'] if 'split' in item]
        if cut:
            # Source metres to Unreal cm: (100 x, -100 y), as the migration placed them (inventory/world.md §1).
            splits.append({'region': rid, 'tag': listed['tag'], 'keys': [i['split']['key'] for i in cut],
                           'objects': [i['id'].rsplit('/', 1)[1] for i in cut],
                           'points_cm': [[100.0 * i['split']['at'][0], -100.0 * i['split']['at'][1]] for i in cut],
                           'tolerance_cm': SPLIT_TOLERANCE_CM})
        for item in listed['objects']:
            wanted[f'{listed["tag"]}:{item["id"].rsplit("/", 1)[1]}'] = (rid, item)
    if groups and not environment:
        raise ObjectError('--environment is needed to save runtime-group objects (the manifest lists their groups)')
    environment = environment if groups else None
    if claim:
        authority.creation_claim(claim, region_ids + ([environment] if environment else []), 'object migration')
    else:
        authority.authorize([], None, 'object migration')
    plan = {'map': maps.pop(), 'claim': claim, 'regions': [{'id': r} for r in region_ids], 'environment': environment,
            'groups': groups, 'splits': splits}
    out.mkdir(parents=True, exist_ok=True)
    plan_file = out / 'objects-plan.json'
    plan_file.write_text(json.dumps(plan, indent=2, sort_keys=True) + '\n')
    before = authority.content_snapshot(game)
    text = editor(plan_file)
    if not DONE.search(text):
        raise ObjectError(f'the editor step did not report completion in {LOG}')
    saved = dict((key, package) for package, key in OBJECT.findall(text))
    lost = sorted(set(wanted) - set(saved))
    if lost:
        raise ObjectError(f'the map holds no object for {lost}')
    created = sorted(set(authority.content_snapshot(game)) - set(before))
    made = record_objects(game, [(rid, item, saved[key]) for key, (rid, item) in sorted(wanted.items())], claim,
                          echo=echo)
    if groups:
        save_validate.validate(game, environment, claim=claim, echo=echo)   # the manifest lists the saved groups
    for split in splits:   # its area patches gave up the split objects' instances
        save_validate.validate(game, split['region'], claim=claim, echo=echo)
    owned = {records.content_relative(game, p) for package in made.values()
             for p in records.package_files(game, package)}
    stray = [rel for rel in created if rel.rsplit('.', 1)[0] not in {o.rsplit('.', 1)[0] for o in owned}]
    if stray:
        raise ObjectError(f'{len(stray)} created file(s) belong to no object, e.g. {stray[0]}')
    echo(f'{len(made)} object(s) saved: ' + ', '.join(sorted(made)))
    return made


def record_objects(game: Path, entries: list[tuple[str, dict, str]], claim: str | None, *, echo=print) -> dict:
    """Write and validate the records of saved objects (region, objects.toml entry, actor package); returns {object
    id: package}. One claims check covers the changed records and one the changed package files: each check
    verifies the claim's LFS locks, which took seconds per object when checked one by one."""
    due = {}
    for rid, item, package in entries:
        record = game / 'assets' / item['id'] / 'asset.toml'
        text = record_text(item, rid, package)
        if not record.is_file() or record.read_text() != text:
            due[record] = text
    if due:
        authority.authorize(sorted(f'games/yorimichi_v2/{r.relative_to(game).as_posix()}' for r in due), claim,
                            f'{len(due)} object record(s)', scopes={rid for rid, _, _ in entries})
    for record, text in due.items():
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(text)
    discovered = records.discover(game)
    ids = [item['id'] for _, item, _ in entries]
    changed = []
    for oid in ids:
        save_validate.validate(game, oid, claim=claim, echo=echo, discovered=discovered, collect=changed)
    if changed:
        by_id = {a.id: a for a in discovered[0]}
        save_validate.authorize(sorted(set(changed)), claim, f'{len(ids)} object(s)', game,
                                scopes={authority.asset_scope(by_id[oid]) for oid in ids})
    for oid in ids:
        save_validate.validate(game, oid, claim=claim, echo=echo, discovered=discovered, authorized=frozenset(changed))
    return {item['id']: package for _, item, package in entries}


def promote(game: Path, region_ids: list[str], claim: str | None, *, only=None, echo=print) -> dict[str, str]:
    """Give each `patch` object of the regions its own record: the actor package the migration saved holding that
    object alone (patches.json) leaves its region's verification for the object's. Nothing is opened or saved in the
    editor; the package bytes stay as they are. Returns {object id: actor package}."""
    _, regions = records.discover(game)
    by_id = {r.id: r for r in regions}
    missing = [r for r in region_ids if r not in by_id]
    if missing:
        raise ObjectError(f'no region record for {missing}')
    made = {}
    for rid in region_ids:
        region = by_id[rid]
        items = [i for i in load_objects(region)['objects'] if 'patch' in i and (only is None or i['id'] in set(only))]
        if not items:
            continue
        roster = region.folder / 'patches.json'
        patches = json.loads(roster.read_text()).get('patches', {}) if roster.is_file() else {}
        entries = []
        for item in items:
            entry = patches.get(item['patch'])
            if entry is None:
                raise ObjectError(f'{item["id"]}: patch {item["patch"]} is not in {rid}\'s patches.json')
            rel = entry['package']
            if not rel.startswith('unreal/Content/') or not (game / rel).is_file():
                raise ObjectError(f'{item["id"]}: its patch package {rel} is missing')
            entries.append((rid, item, '/Game/' + rel[len('unreal/Content/'):].rsplit('.', 1)[0]))
        made.update(record_objects(game, entries, claim, echo=echo))
        save_validate.validate(game, rid, claim=claim, echo=echo)   # the region's verification drops them
    if only is not None and set(only) - set(made):
        raise ObjectError(f'{sorted(set(only) - set(made))}: no patch object of {region_ids}')
    echo(f'{len(made)} object(s) promoted: ' + ', '.join(sorted(made)))
    return made


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('regions', nargs='+', help='region IDs whose objects.toml to save')
    parser.add_argument('--environment', help="the region owning the map's manifest (runtime-group objects)")
    parser.add_argument('--promote', action='store_true',
                        help='record the `patch` objects (no editor): their saved patches become their own records')
    parser.add_argument('--claim', help='claims task holding the regions and the environment')
    parser.add_argument('--only', action='append', help='only this object ID (repeatable)')
    parser.add_argument('--claim-paths', action='store_true',
                        help='print (JSON) the lock paths and paths a claim for these objects needs, and exit')
    args = parser.parse_args(argv)
    try:
        if args.claim_paths:
            print(json.dumps(claim_paths(GAME, args.regions, only=args.only), indent=1))
        elif args.promote:
            promote(GAME, args.regions, args.claim, only=args.only)
        else:
            migrate(GAME, args.regions, args.environment, args.claim, only=args.only)
    except (ObjectError, authority.Unauthorized, save_validate.ValidationError, records.RecordError) as error:
        print(f'object migration failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
