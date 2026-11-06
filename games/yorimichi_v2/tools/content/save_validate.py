"""Save validation: record an editor-owned asset's or a region's saved packages after a claimed editor edit.

    uv run python games/yorimichi_v2/tools/content/save_validate.py material/painted [--claim TASK]
    uv run python games/yorimichi_v2/tools/content/save_validate.py region/w01-start [--add FILE ...] [--remove FILE ...]

Editor-owned content is never imported (plan §5): after its edit is saved, this records the complete package set
it now has, with hashes, engine identity and the state of the dependencies it references, in `verified.json`
(assets) or `actors.verified.json` (regions). A region's actors are its current record's packages that still
exist, plus packages under its maps' `__ExternalActors__`/`__ExternalObjects__` folders whose actor label starts
with the region ID (`region/<name>:...`, the migration's labels) or, unlabelled by a region, whose saved
location lies inside the region's bounds, plus explicit `--add`. A package another region
already owns, or one that no longer exists, is refused or dropped explicitly. No change writes nothing.

It never fixes content and never touches a generated package.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
import authority  # noqa: E402
import records  # noqa: E402
from records import RecordError  # noqa: E402

GAME = Path(__file__).resolve().parents[2]
REPO = GAME.parents[1]
BOOTSTRAP_WRITER = authority.BOOTSTRAP_WRITER
ACTOR_ROOTS = ('__ExternalActors__', '__ExternalObjects__')


class ValidationError(RuntimeError):
    pass


def engine_identity() -> str:
    root = Path(os.environ.get('UE_ROOT') or '/Users/Shared/Epic Games/UE_5.8')
    data = json.loads((root / 'Engine/Build/Build.version').read_text())
    return f'{data["MajorVersion"]}.{data["MinorVersion"]}.{data["PatchVersion"]}-{data["Changelist"]}'


def authorize(paths: list[str], claim: str | None):
    try:
        authority.authorize([f'games/yorimichi_v2/{p}' for p in paths], claim, 'save validation')
    except authority.Unauthorized as error:
        raise ValidationError(str(error)) from None


def actor_info(path: Path):
    """(label, location in cm) of a saved actor from its package header, or (None, None) when unreadable."""
    try:
        sys.path.insert(0, str(REPO / 'platform' / 'studio'))
        from atelier import unreal_package_summary as summary
    except ImportError:
        return None, None
    try:
        actor = summary.read(path).actor
    except Exception:  # noqa: BLE001 — an unreadable header leaves membership to the record and --add
        return None, None
    return (actor.label, actor.location) if actor else (None, None)


def inside(bounds, location) -> bool:
    """Half-open, so an actor on a shared edge belongs to exactly one region."""
    return location is not None and bounds[0] <= location[0] < bounds[2] and bounds[1] <= location[1] < bounds[3]


def map_actor_dirs(game: Path, map_package: str) -> list[Path]:
    rel = PurePosixPath(map_package).relative_to('/Game')
    return [game / 'unreal' / 'Content' / root / rel for root in ACTOR_ROOTS]


def region_files(game: Path, region, others: dict[str, str], add: list[str], remove: list[str]) -> list[str]:
    current = set()
    if region.actors.is_file():
        current = set(records.load_verified(region.actors)['files'])
    candidates = set()
    for map_package in region.maps:
        for folder in map_actor_dirs(game, map_package):
            if folder.is_dir():
                candidates.update(records.content_relative(game, p) for p in folder.rglob('*.uasset'))
    members = {rel for rel in current if (game / rel).is_file()}
    for rel in sorted(candidates - members):
        if rel in others:
            continue
        label, location = actor_info(game / rel)
        if (label and label.startswith(region.id + ':')) or (not label or ':' not in label) and \
                inside(region.bounds_cm, location):
            members.add(rel)
    for rel in add:
        rel = records.content_relative(game, (game / rel) if not Path(rel).is_absolute() else Path(rel))
        if rel in others:
            raise ValidationError(f'{rel} belongs to {others[rel]}: move it explicitly (claim both regions)')
        if not (game / rel).is_file():
            raise ValidationError(f'{rel} does not exist')
        members.add(rel)
    for rel in remove:
        members.discard(rel)
    return sorted(members)


def validate(game: Path, subject: str, *, claim=None, add=(), remove=(), echo=print) -> bool:
    assets, regions = records.discover(game)
    by_id = {a.id: a for a in assets}
    engine = engine_identity()
    if subject in by_id:
        asset = by_id[subject]
        if asset.authority == 'generated':
            raise ValidationError(f'{subject} is generated: its importer records it (tools/import/run.py)')
        files = {}
        for output in asset.outputs:
            if output.writer != 'editor':
                continue
            present = [p for p in records.package_files(game, output.package) if p.is_file()]
            if not present:
                raise ValidationError(f'{subject}: {output.package} is not saved')
            stem = present[0].with_suffix('')
            for ext in records.PACKAGE_EXTENSIONS + records.COMPANION_EXTENSIONS:
                if stem.with_suffix(ext).is_file():
                    files[records.content_relative(game, stem.with_suffix(ext))] = None
        target = asset.verified
        previous = records.load_verified(target) if target.is_file() else None
        generated = {}
        if previous:
            # A split asset keeps its importer-written packages' record untouched.
            stems = {records.content_relative(game, records.package_files(game, o.package)[0].with_suffix(''))
                     for o in asset.outputs if o.writer == 'generated'}
            generated = {rel: d for rel, d in previous['files'].items() if rel.rsplit('.', 1)[0] in stems}
        deps = {}
        for dep in asset.references:
            if dep in by_id and by_id[dep].verified.is_file():
                deps[dep] = records.state_fingerprint(records.load_verified(by_id[dep].verified))
        body = {'schema': records.SCHEMA, 'kind': 'editor-saved', 'asset': subject, 'engine': engine,
                'dependencies': deps}
        if previous and previous['kind'] == 'imported':      # split: the import record's identity stays
            body.update(kind='imported', **{k: previous[k] for k in ('input_fingerprint', 'tool') if k in previous})
    else:
        region = next((r for r in regions if r.id == subject), None)
        if region is None:
            raise ValidationError(f'unknown asset or region {subject}')
        others = {}
        for other in regions:
            if other.id != subject and other.actors.is_file():
                for rel in records.load_verified(other.actors)['files']:
                    others[rel] = other.id
        files = dict.fromkeys(region_files(game, region, others, list(add), list(remove)))
        if not files and not region.actors.is_file():
            raise ValidationError(f'{subject} owns no saved actor packages; add them with --add')
        target, generated = region.actors, {}
        body = {'schema': records.SCHEMA, 'kind': 'editor-saved', 'asset': subject, 'engine': engine}
    for rel in files:
        path = game / rel
        if records.is_lfs_pointer(path):
            raise ValidationError(f'{rel} is an LFS pointer; pull it before validating')
        files[rel] = records.sha256_file(path)
    previous_files = records.load_verified(target)['files'] if target.is_file() else {}
    changed = sorted(set(files) ^ set(previous_files) | {r for r in files if previous_files.get(r) != files[r]})
    if changed:
        authorize(changed, claim)
    body['files'] = {**generated, **files}
    if records.write_json(target, body):
        echo(f'recorded {subject}: {len(files)} package file(s), {len(changed)} changed')
        return True
    echo(f'unchanged {subject}')
    return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('subject', help='editor-owned asset ID or region ID')
    parser.add_argument('--claim', help='the active claim (task ID) authorizing these packages')
    parser.add_argument('--add', nargs='*', default=[], help='game-relative actor packages to add to a region')
    parser.add_argument('--remove', nargs='*', default=[], help='game-relative actor packages to drop from a region')
    args = parser.parse_args(argv)
    try:
        validate(GAME, args.subject, claim=args.claim, add=args.add, remove=args.remove)
    except (ValidationError, RecordError) as error:
        print(f'save validation failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
