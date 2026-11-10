"""The shared lifecycle that replaces a region's grouped objects with one object per member, in steps that each repeat safely.

A regional tool (the retired gondola_pylons.py and railway_fittings.py; see git history) chooses the members, renders
objects.toml and names its files in a `Split`; this module owns the states, the claim, the receipts and the two writing
steps, so a fix to acceptance or retirement reaches every region.

States: unprepared -> prepared (pending save) -> saved (pending retire) -> done. Each state is the tree after a step, and
a rerun of the step that produced it is a no-op.

1. Prepare: after one authorized check of every path and scope `claim_paths` names, one journaled write puts the
   replacements into objects.toml, takes the group entries out, and records the pending retirement in the region's pending
   file: each group's record files and actor packages, and the replacement ids. The groups' records, actors and saved keys
   stay, so their members are still drawn.
2. Save: objects.py saves the replacements (unchanged tool). Its saved-definition check only looks at the objects it is
   given, and objects.saved.json keeps the groups' keys, so it accepts this state.
3. Retire: only when every replacement has an accepted receipt. Then, under the journal, it deletes the recorded records
   and actor packages, drops the group keys from objects.saved.json and deletes the pending file.

Every write goes through brinecove_split_apply.Journal (recovered first) and execute, and authority.authorize with the
region and environment scopes.
"""
from __future__ import annotations

import json
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
GAME = HERE.parents[1]
sys.path.insert(0, str(GAME / 'tools' / 'content'))
import authority  # noqa: E402
import records  # noqa: E402
sys.path.insert(0, str(HERE))
import brinecove_split_apply as apply  # noqa: E402  (Journal and execute: the journaled write every migrate step uses)
import objects  # noqa: E402  (MANIFEST: the map manifest a save writes)

ENVIRONMENT = 'region/w00-island'


@dataclass(frozen=True)
class Split:
    """One region's split: its files, how its group and replacement objects are recognised, and its wording."""
    region: str                                 # 'w18-gondola'
    pending: str                                # the pending-retirement file in the region folder
    group: re.Pattern                           # matches the id of every group object being replaced
    group_ids: tuple[str, ...]                  # every such group, looked for on disk as well
    is_replacement: Callable[[str], bool]       # an object id this split creates
    error: type                                 # the regional tool's error class
    label: str                                  # names the steps for authority ('gondola pylon', 'railway fittings')
    noun: str                                   # one replacement ('pylon', 'fitting')
    unprepared: Callable[[list[dict]], str]     # the detail of `unprepared`, from the listed groups
    done: Callable[[set[str]], str]             # the detail of `done`, from the replacement ids

    @property
    def region_id(self) -> str:
        return f'region/{self.region}'

    @property
    def scopes(self) -> set[str]:
        return {self.region_id, ENVIRONMENT}

    @property
    def objects_rel(self) -> str:
        return f'world/regions/{self.region}/objects.toml'

    @property
    def saved_rel(self) -> str:
        return f'world/regions/{self.region}/objects.saved.json'

    @property
    def pending_rel(self) -> str:
        return f'world/regions/{self.region}/{self.pending}'


def saved_definition(item: dict) -> dict:
    """What objects.saved.json records for an object: objects.py's definition (its entry without `about`, with the models and
    groups load_objects derives)."""
    models = [item['model']] if isinstance(item['model'], str) else list(item['model'])
    return {'id': item['id'], 'route': list(item['route']), 'model': item['model'], 'models': models, 'groups': []}


# --- the files a step names ----------------------------------------------------------------------------------------------

def pending_of(split: Split, game: Path) -> dict | None:
    path = game / split.pending_rel
    if not path.is_file():
        return None
    try:
        body = json.loads(path.read_text())
    except ValueError as error:
        raise split.error(f'{split.pending_rel} is not JSON: {error}') from None
    if body.get('schema') != 1 or set(body) != {'schema', 'groups', 'replacements'}:
        raise split.error(f'{split.pending_rel} has an unknown shape')
    return body


def pending_text(pending: dict) -> str:
    return json.dumps(pending, indent=2, sort_keys=True) + '\n'


def group_listing(split: Split, game: Path, gid: str) -> dict:
    """A group's record and its files and actor packages as they are on disk: what retirement deletes."""
    folder = game / 'assets' / gid
    asset = records.load_asset(folder / 'asset.toml')
    files = [p.relative_to(game).as_posix() for p in sorted(folder.rglob('*')) if p.is_file()]
    packages = []
    for output in asset.outputs:
        packages += [rel for rel in apply.package_rels(game, output.package) if (game / rel).is_file()]
    if not any(rel.endswith(records.PACKAGE_EXTENSIONS) for rel in packages):
        raise split.error(f'{gid}: its actor package {[o.package for o in asset.outputs]} is missing')
    return {'files': files, 'packages': sorted(set(packages))}


def group_checks(split: Split, game: Path, items: list[dict], saved: dict) -> None:
    """Each listed group: its record names it and its models, and objects.saved.json records its definition."""
    for item in items:
        gid = item['id']
        record = game / 'assets' / gid / 'asset.toml'
        if not record.is_file():
            raise split.error(f'{gid}: its record {record.relative_to(game)} is missing')
        asset = records.load_asset(record)
        if asset.id != gid or sorted(asset.references) != sorted(saved_definition(item)['models']):
            raise split.error(f'{gid}: its record does not name this group or its models')
        if saved.get(gid) != saved_definition(item):
            raise split.error(f'{gid}: objects.saved.json does not record its objects.toml definition')


def saved_of(split: Split, game: Path) -> dict:
    path = game / split.saved_rel
    return json.loads(path.read_text()).get('objects', {}) if path.is_file() else {}


def objects_of(split: Split, game: Path) -> dict:
    return {i['id']: i for i in tomllib.loads((game / split.objects_rel).read_text()).get('objects', [])}


def groups_listed(split: Split, game: Path) -> list[dict]:
    return [i for i in objects_of(split, game).values() if split.group.match(i['id'])]


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

def state(split: Split, game: Path, taken: list[dict]) -> tuple[str, str]:
    """(state, detail) of the tree: unprepared, prepared, saved, or done. Refuses a tree no step explains."""
    objects_now, saved = objects_of(split, game), saved_of(split, game)
    groups = [i for i in objects_now.values() if split.group.match(i['id'])]
    listed = {i for i in objects_now if split.is_replacement(i)}
    wanted = {t['object'] for t in taken}
    pending = pending_of(split, game)
    if pending is None:
        if groups and not listed:
            return 'unprepared', split.unprepared(groups)
        group_left = any((game / 'assets' / g / 'asset.toml').is_file() or g in saved for g in split.group_ids)
        if not groups and wanted <= listed and not group_left:
            return 'done', split.done(wanted)
        raise split.error('objects.toml, objects.saved.json and the group records disagree and no pending file explains it')
    if groups or set(pending['replacements']) != listed:
        raise split.error(f'{split.pending_rel} does not match objects.toml')
    for gid in pending['groups']:
        if gid not in saved or not (game / 'assets' / gid / 'asset.toml').is_file():
            raise split.error(f'{gid} is pending retirement but its saved entry or record is gone')
    missing = [pid for pid in sorted(wanted) if not receipt_ok(game, pid, objects_now[pid], saved)]
    if missing:
        return 'prepared', f'{len(missing)} replacement(s) without an accepted receipt, e.g. {missing[0]}'
    return 'saved', f'all {len(wanted)} replacements have accepted receipts; retire with --retire --claim'


def claim_paths(split: Split, game: Path, taken: list[dict]) -> dict:
    """Every path and scope the steps touch, for one claim: the region's objects, the pending file, the groups' records and
    actor packages (as the pending file or the disk names them), the replacement records, and the manifest objects.py lists."""
    pending = pending_of(split, game)
    if pending is not None:
        listing = {g: {'files': v['files'], 'packages': v['packages']} for g, v in pending['groups'].items()}
    else:
        listing = {g: group_listing(split, game, g) for g in split.group_ids if (game / 'assets' / g / 'asset.toml').is_file()}
    rels = {split.objects_rel, split.saved_rel, split.pending_rel}
    for entry in listing.values():
        rels |= set(entry['files']) | set(entry['packages'])
    for t in taken:
        rels |= {f'assets/{t["object"]}/asset.toml', f'assets/{t["object"]}/verified.json'}
    rels.add(objects.MANIFEST[ENVIRONMENT])
    return {'paths': sorted(f'games/yorimichi_v2/{r}' for r in rels), 'scopes': sorted(split.scopes)}


def authorize(split: Split, game: Path, taken: list[dict], claim: str | None, what: str) -> None:
    """The complete claim, checked before any byte of the step is written."""
    plan = claim_paths(split, game, taken)
    try:
        authority.authorize(plan['paths'], claim, what, scopes=split.scopes)
    except authority.Unauthorized as error:
        raise split.error(str(error)) from None


# --- the steps ---------------------------------------------------------------------------------------------------------

def prepare(split: Split, game: Path, taken: list[dict], claim: str, render: Callable[[str], str], *, lockable=None,
            echo=print) -> str:
    """Step 1. `render` turns the committed objects.toml into the prepared one. A rerun when already prepared (or later) is
    a no-op. The claim is checked before any write."""
    apply.Journal(game).recover(claim)
    current, why = state(split, game, taken)
    if current != 'unprepared':
        echo(f'prepare: already {current} ({why}); nothing written')
        return current
    objects_out = render((game / split.objects_rel).read_text())
    groups, saved = groups_listed(split, game), saved_of(split, game)
    listed = {item['id']: group_listing(split, game, item['id']) for item in groups}
    group_checks(split, game, groups, saved)
    pending = {'schema': 1, 'groups': listed, 'replacements': sorted(t['object'] for t in taken)}
    authorize(split, game, taken, claim, f'{split.label} prepare')
    ops = {'writes': {split.objects_rel: objects_out.encode(), split.pending_rel: pending_text(pending).encode()},
           'deletes': []}
    apply.execute(game, ops, scopes=split.scopes, **({'lockable': lockable} if lockable else {}))
    echo(f'prepare: {len(pending["replacements"])} {split.noun} objects listed; {len(listed)} group(s) pending retirement')
    return 'prepared'


def retire(split: Split, game: Path, taken: list[dict], claim: str, *, lockable=None, echo=print) -> str:
    """@cc [owner:fontanierh,label:safety] group-split-retire-after-receipts
    Step 3. A group's records, actor packages and saved key are deleted only once every replacement has an accepted receipt
    (receipt_ok: saved definition, record and verified hash of each actor package); any other state refuses and changes
    nothing, so the members are never left undrawn. A rerun after it is a no-op."""
    apply.Journal(game).recover(claim)
    current, why = state(split, game, taken)
    if current == 'done':
        echo(f'retire: already done ({why}); nothing written')
        return current
    if current != 'saved':
        raise split.error(f'retire refused: the {split.noun} objects are {current} ({why}); nothing changed')
    pending = pending_of(split, game)
    saved = saved_of(split, game)
    deletes = {split.pending_rel}
    for gid, listing in pending['groups'].items():
        deletes |= {rel for rel in listing['files'] + listing['packages'] if (game / rel).is_file()}
        saved.pop(gid, None)
    body = json.loads((game / split.saved_rel).read_text())
    body['objects'] = saved
    authorize(split, game, taken, claim, f'{split.label} retire')
    ops = {'writes': {split.saved_rel: (json.dumps(body, indent=2, sort_keys=True) + '\n').encode()},
           'deletes': sorted(deletes)}
    apply.execute(game, ops, scopes=split.scopes, **({'lockable': lockable} if lockable else {}))
    echo(f'retire: {len(pending["groups"])} group(s) removed; {len(deletes) - 1} file(s) deleted')
    return 'done'
