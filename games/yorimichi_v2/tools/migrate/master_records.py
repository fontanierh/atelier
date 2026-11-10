"""Generator-built material masters as material-master records (docs/inventory/master-sources.md, section 5).

    CMD="uv run python games/yorimichi_v2/tools/migrate/master_records.py"
    $CMD --family NAME                # the state and the claim paths; writes nothing
    $CMD --family NAME --paths        # the claim paths and the scopes
    $CMD --family NAME --claim TASK   # the one journaled write

A family (tools/migrate/master_families/NAME.py, one FAMILY dict) names the adopted record that owns its masters, the
builder module under unreal/Scripts/material_masters/ and one entry per master. Each master becomes its own
material-master record, with the builder module copied into its src/ and pinned by sha256. The adopted record gives up
every package, so it is deleted with its verified.json, and every record that references it references the masters it
uses instead (reference_rewrites). The records are not imported here: the V2 editor builds and reads back each master
(unreal/Scripts/import_asset.py, material-master), and tools/import/run.py writes its verified.json.

States: `unprepared` (the adopted record lists exactly the family's masters, no master record exists) and `done` (every
master record exists, the adopted record is gone). Any other state refuses, so a half-moved set is never extended by a
second write. An adopted record that owns other packages too refuses: it is split by hand first.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parents[1]
REPO = GAME.parents[1]
GAME_REL = 'games/yorimichi_v2'
BUILDERS = GAME / 'unreal/Scripts/material_masters'
FAMILY_DIR = HERE / 'master_families'
sys.path.insert(0, str(GAME / 'tools' / 'content'))
sys.path.insert(0, str(HERE))
import authority  # noqa: E402
import records  # noqa: E402
import brinecove_split_apply as apply  # noqa: E402  (the journaled write every migrate step uses)

PROVENANCE = '{donor} at the V2 source baseline (docs/DECISIONS.md D01, D02)'
DEPENDENCY_KEYS = ('references', 'input_dependencies')
LINE = {key: re.compile(rf'^{key} = (\[.*\])$', re.M) for key in DEPENDENCY_KEYS}
FAMILY_KEYS = {'name', 'adopted', 'owner', 'license', 'builder', 'donor', 'donor_lines', 'fallback', 'masters'}
MASTER_KEYS = {'id', 'package', 'builder', 'reads', 'inputs', 'arguments'}


class PlanError(RuntimeError):
    pass


def load_families(folder: Path = FAMILY_DIR) -> dict:
    """{name: family} from every master_families/*.py. A family is checked here, before any plan reads it."""
    out = {}
    for path in sorted(folder.glob('*.py')):
        spec = importlib.util.spec_from_file_location(f'v2_master_family_{path.stem}', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        family = module.FAMILY
        if set(family) != FAMILY_KEYS or family['name'] != path.stem:
            raise PlanError(f'{path.name}: a family has the keys {sorted(FAMILY_KEYS)} and is named after its file')
        if not (BUILDERS / family['builder']).is_file():
            raise PlanError(f'{path.name}: no builder module {family["builder"]} in unreal/Scripts/material_masters')
        for master in family['masters']:
            if set(master) != MASTER_KEYS or master['builder'] not in family['donor_lines']:
                raise PlanError(f'{path.name}: {master.get("id")}: a master has the keys {sorted(MASTER_KEYS)} and a '
                                'builder with donor lines')
        if not set(fallback_ids(family)) <= {m['id'] for m in family['masters']} or not fallback_ids(family):
            raise PlanError(f'{path.name}: the fallback is one or more of the family masters')
        out[family['name']] = family
    return out


def fallback_ids(family: dict) -> list:
    """The family's fallback as a list: one master id, or several when a referrer may use any of them."""
    fallback = family['fallback']
    return [fallback] if isinstance(fallback, str) else list(fallback)


def builder_path(family: dict) -> Path:
    return BUILDERS / family['builder']


def builder_rel(family: dict) -> str:
    return f'src/{family["builder"]}'


def builder_sha(family: dict) -> str:
    return hashlib.sha256(builder_path(family).read_bytes()).hexdigest()


def _packages_named(value) -> set:
    """Every /Game package a recipe value names, object suffixes dropped."""
    if isinstance(value, str):
        return {value.split('.')[0]} if value.startswith('/Game/') else set()
    if isinstance(value, dict):
        return set().union(*map(_packages_named, value.values())) if value else set()
    if isinstance(value, (list, tuple)):
        return set().union(*map(_packages_named, value)) if value else set()
    return set()


def reference_rewrites(game: Path, family: dict) -> dict:
    """{rel: bytes} for every record that names the adopted record in its references or input_dependencies. Each
    mention becomes the masters whose packages the record's recipe names, or the family's fallback when it names none.
    A record that is itself an input of a family master drops the mention instead, so no record depends on what it
    feeds. A dependency line this cannot rewrite refuses."""
    adopted = family['adopted']
    by_package = {m['package']: m['id'] for m in family['masters']}
    feeds = {dep for m in family['masters'] for dep in m['inputs']}
    out = {}
    for path in records.record_paths(game):
        rel = path.relative_to(game).as_posix()
        if rel == f'assets/{adopted}/asset.toml':
            continue
        asset = records.load_asset(path)
        if not any(adopted in getattr(asset, key) for key in DEPENDENCY_KEYS):
            continue
        named = _packages_named(asset.recipe or {})
        masters = [] if asset.id in feeds else (sorted({by_package[p] for p in named if p in by_package})
                                                or fallback_ids(family))
        text = path.read_text()
        for key in DEPENDENCY_KEYS:
            current = getattr(asset, key)
            if adopted not in current:
                continue
            match = LINE[key].search(text)
            if match is None or json.loads(match.group(1)) != current:
                raise PlanError(f'{rel}: its {key} are not one rewritable line')
            new = []
            for ref in current:
                for item in (masters if ref == adopted else [ref]):
                    if item not in new:
                        new.append(item)
            if new:
                text = text[:match.start(1)] + json.dumps(new) + text[match.end(1):]
            else:   # an emptied list goes away with its line
                text = text[:match.start()] + text[match.end() + 1:]
        out[rel] = text.encode()
    return out


def _value(value) -> str:
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, str):
        return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'
    return repr(float(value)) if isinstance(value, float) else str(value)


def record_text(family: dict, master: dict, sha: str) -> str:
    """The material-master record of one master (asset.toml). Parsed back by records.load_asset in the tests."""
    provenance = PROVENANCE.format(donor=f'donor generator {family["donor"]}')
    lines = [f'# Recovered as a material master (tools/migrate/master_records.py): {master["package"]}.',
             f'# The builder is {builder_rel(family)}, pinned by sha256; the master is rebuilt by the V2 editor and read back',
             '# against its saved original, never edited by hand.',
             'schema = 1', f'id = "{master["id"]}"', 'kind = "material-master"', 'authority = "generated"',
             f'owner = "{family["owner"]}"', f'license = "{family["license"]}"',
             f'provenance = "{provenance}, {master["builder"]} lines {family["donor_lines"][master["builder"]]}"']
    if master['inputs']:   # a top-level key: it must come before the first [[sources]] table
        lines.append('input_dependencies = [' + ', '.join(f'"{r}"' for r in master['inputs']) + ']')
    lines += ['', '[[sources]]', f'path = "{builder_rel(family)}"', f'sha256 = "{sha}"',
              '', '[recipe]', 'importer = "material-master"', 'version = 1', '', '[recipe.settings]',
              f'builder = "{master["builder"]}"',
              'reads = [' + ', '.join(f'"{r}"' for r in master['reads']) + ']',
              'arguments = { ' + ', '.join(f'{k} = {_value(v)}' for k, v in master['arguments'].items()) + ' }',
              '', '[[outputs]]', f'package = "{master["package"]}"', '']
    return '\n'.join(lines)


def state(game: Path, family: dict) -> str:
    """'unprepared', 'done', or a PlanError naming what is half-moved."""
    adopted = game / f'assets/{family["adopted"]}/asset.toml'
    masters = family['masters']
    present = [m['id'] for m in masters if (game / f'assets/{m["id"]}/asset.toml').is_file()]
    packages = {m['package'] for m in masters}
    listed = {o.package for o in records.load_asset(adopted).outputs} if adopted.is_file() else set()
    if listed - packages:
        raise PlanError(f'{family["adopted"]} also owns {sorted(listed - packages)}; split it by hand first')
    if not present and packages == listed:
        return 'unprepared'
    if len(present) == len(masters) and not listed:
        return 'done'
    raise PlanError(f'the {family["name"]} masters are half-moved: records {present}, adopted still lists '
                    f'{sorted(listed & packages)}; resolve by hand')


def claim_ops(game: Path, family: dict) -> dict:
    """The one write: {'writes': {rel: bytes}, 'deletes': [rel]}. Empty when the state is done and nothing references
    the adopted record."""
    if state(game, family) == 'done':
        return {'writes': reference_rewrites(game, family), 'deletes': []}
    sha = builder_sha(family)
    writes = reference_rewrites(game, family)
    for master in family['masters']:
        folder = f'assets/{master["id"]}'
        writes[f'{folder}/asset.toml'] = record_text(family, master, sha).encode()
        writes[f'{folder}/{builder_rel(family)}'] = builder_path(family).read_bytes()
    deletes = [f'assets/{family["adopted"]}/{name}' for name in ('asset.toml', 'verified.json')
               if (game / f'assets/{family["adopted"]}/{name}').is_file()]
    return {'writes': writes, 'deletes': deletes}


def claim_paths(game: Path, family: dict) -> list[str]:
    ops = claim_ops(game, family)
    return sorted(set(ops['writes']) | set(ops['deletes']))


def materialize(game: Path, family: dict, claim: str, *, echo=print) -> None:
    apply.Journal(game).recover(claim)
    ops = claim_ops(game, family)
    if not ops['writes'] and not ops['deletes']:
        echo(f'materialize: the {family["name"]} masters are already records and nothing references the adopted record; '
             'nothing written')
        return
    paths = claim_paths(game, family)
    try:
        authority.authorize([f'{GAME_REL}/{rel}' for rel in paths], claim,
                            f'Yorimichi V2 {family["name"]} materials as material-master records', scopes=[family['owner']])
    except authority.Unauthorized as error:
        raise PlanError(str(error)) from None
    apply.execute(game, ops, scopes=[family['owner']])
    echo(f'materialize: {len(paths)} path(s) under {claim}')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--game', type=Path, default=GAME)
    parser.add_argument('--family', required=True, help='a master_families/ module name')
    parser.add_argument('--paths', action='store_true', help='print the claim paths and the scope')
    parser.add_argument('--claim', metavar='TASK', help='the one journaled write')
    args = parser.parse_args(argv)
    try:
        families = load_families()
        if args.family not in families:
            raise PlanError(f'no family {args.family}; known: {", ".join(sorted(families))}')
        family = families[args.family]
        if args.claim:
            materialize(args.game, family, args.claim)
            return 0
        print(f'state: {state(args.game, family)}')
        if args.paths or state(args.game, family) == 'unprepared':
            for rel in claim_paths(args.game, family):
                print(f'path {GAME_REL}/{rel}')
            print(f'scopes: {family["owner"]}')
    except (PlanError, records.RecordError, authority.Unauthorized) as error:
        print(f'master_records: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
