"""Keep every region object's model on records that exist, in its objects.toml entry and its saved definition.

    uv run python games/yorimichi_v2/tools/migrate/object_models.py --check
    uv run python games/yorimichi_v2/tools/migrate/object_models.py --claim TASK [--region region/w09-brinecove ...]
    uv run python games/yorimichi_v2/tools/migrate/object_models.py --sync-saved --claim TASK   # after parks.py

A recovery that splits or deletes a shared record points its consumers' records at the records that now own the
packages they use (recover.py `_retarget`). A region object also names its model in objects.toml and in
objects.saved.json (tools/migrate/objects.py), so the two must follow: each model that names no record becomes the
object record's own references, in their order. The saved definition is updated with the entry, so objects.py's
saved-definition check still holds and no actor is re-saved. An object without a record, or whose record names no
existing record, is an error, never guessed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parents[1]
sys.path.insert(0, str(GAME / 'tools/content'))
sys.path.insert(0, str(HERE))
import authority  # noqa: E402
import objects  # noqa: E402
import records  # noqa: E402


class ModelError(RuntimeError):
    pass


def _value(models: list[str]) -> str:
    return f'"{models[0]}"' if len(models) == 1 else '[' + ', '.join(f'"{m}"' for m in models) + ']'


def dangling(game: Path, only=None) -> dict[str, dict[str, list[str]]]:
    """{region id: {object id: its new models}} for every object whose model names no record."""
    assets, regions = records.discover(game)
    by_id = {a.id: a for a in assets}
    found = {}
    for region in regions:
        if only and region.id not in only or not (region.folder / 'objects.toml').is_file():
            continue
        for item in objects.load_objects(region)['objects']:
            if all(m in by_id for m in objects.models(item)):
                continue
            record = by_id.get(item['id'])
            # Only records that own packages are models; a placement's references can name other placements.
            new = [r for r in (record.references if record else []) if r in by_id and by_id[r].kind != 'placement'
                   and by_id[r].outputs]
            if not new:
                raise ModelError(f'{item["id"]}: model {objects.models(item)} names no record and its own record names '
                                 'none to take its place')
            found.setdefault(region.id, {})[item['id']] = new
    return found


def rewrite(game: Path, found: dict, claim: str | None) -> list[Path]:
    """Write the new models into each region's objects.toml and objects.saved.json; returns the files written."""
    regions = {r.id: r for r in records.discover(game)[1]}
    due = {}
    for rid, items in found.items():
        folder = regions[rid].folder
        toml = folder / 'objects.toml'
        text = toml.read_text()
        for oid, new in items.items():
            block = re.search(rf'(?ms)^id = "{re.escape(oid)}"\n.*?(?=^\[\[objects\]\]|\Z)', text)
            if block is None or not re.search(r'(?m)^model = .*$', block.group(0)):
                raise ModelError(f'{oid}: no model line in {toml}')
            body = re.sub(r'(?m)^model = .*$', f'model = {_value(new)}', block.group(0), count=1)
            text = text[:block.start()] + body + text[block.end():]
        due[toml] = text
        saved_path = folder / objects.SAVED
        if saved_path.is_file():
            saved = json.loads(saved_path.read_text())
            for oid, new in items.items():
                if oid in saved.get('objects', {}):
                    saved['objects'][oid]['model'] = new[0] if len(new) == 1 else new
                    if 'models' in saved['objects'][oid]:
                        saved['objects'][oid]['models'] = list(new)
            due[saved_path] = json.dumps(saved, indent=2, sort_keys=True) + '\n'
    due = {p: t for p, t in due.items() if p.read_text() != t}
    if due:
        authority.authorize(sorted(f'games/yorimichi_v2/{p.relative_to(game).as_posix()}' for p in due), claim,
                            f'{len(due)} object list(s)', scopes=set(found))
    for path, text in due.items():
        path.write_text(text)
    return sorted(due)


def sync_saved(game: Path, claim: str | None, only=None) -> list[str]:
    """Give each saved definition its objects.toml entry's models when that is all that differs (a generator such as
    parks.py names the precise records); any other difference stays for objects.py to refuse. Returns the objects."""
    regions = [r for r in records.discover(game)[1] if (not only or r.id in only) and (r.folder / objects.SAVED).is_file()
               and (r.folder / 'objects.toml').is_file()]
    due, moved = {}, []
    for region in regions:
        path = region.folder / objects.SAVED
        saved = json.loads(path.read_text())
        for item in objects.load_objects(region)['objects']:
            old, now = saved.get('objects', {}).get(item['id']), objects.definition(item)
            if old is None or old == now:
                continue
            rest = {k for k in set(old) | set(now) if old.get(k) != now.get(k)}
            if rest <= {'model', 'models'}:
                for k in rest:
                    if k in now:
                        old[k] = now[k]
                    else:
                        del old[k]   # a list model became one: no stale `models`
                moved.append(item['id'])
        text = json.dumps(saved, indent=2, sort_keys=True) + '\n'
        if text != path.read_text():
            due[path] = text
    if due:
        authority.authorize(sorted(f'games/yorimichi_v2/{p.relative_to(game).as_posix()}' for p in due), claim,
                            f'{len(due)} saved-object list(s)', scopes={r.id for r in regions if r.folder / objects.SAVED in due})
    for path, text in due.items():
        path.write_text(text)
    return moved


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--check', action='store_true', help='list the objects whose model names no record; write nothing')
    parser.add_argument('--claim', help='claims task holding the regions written')
    parser.add_argument('--region', action='append', help='only this region ID (repeatable)')
    parser.add_argument('--sync-saved', action='store_true',
                        help="copy each objects.toml entry's models into its saved definition when only they differ")
    args = parser.parse_args(argv)
    try:
        if args.sync_saved:
            moved = sync_saved(GAME, args.claim, args.region)
            print(f'{len(moved)} saved definition(s) took their entry\'s models')
            return 0
        found = dangling(GAME, args.region)
        count = sum(len(v) for v in found.values())
        for rid, items in sorted(found.items()):
            print(f'{rid}: {len(items)} object(s), e.g. {next(iter(items))} -> {next(iter(items.values()))}')
        if args.check:
            print(f'{count} object(s) name a model with no record')
            return 1 if count else 0
        written = rewrite(GAME, found, args.claim)
        print(f'{count} object(s) moved to existing models; {len(written)} file(s) written')
    except (ModelError, authority.Unauthorized, records.RecordError) as error:
        print(f'object models failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
