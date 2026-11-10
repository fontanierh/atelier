"""The hippodrome materials as material-master records: the pilot of docs/inventory/master-sources.md, section 5.

    uv run python games/yorimichi_v2/tools/migrate/master_records.py                # the state and the claim paths; writes nothing
    uv run python games/yorimichi_v2/tools/migrate/master_records.py --paths        # the claim paths and the scopes
    uv run python games/yorimichi_v2/tools/migrate/master_records.py --claim TASK   # the one journaled write

The adopted record assets/adopted/hippodrome/materials owns five masters. Each becomes its own material-master record,
with the builder module unreal/Scripts/material_masters/hippodrome_masters.py copied into its src/ and pinned by sha256.
The adopted record gives up every package, so it is deleted with its verified.json, and every record that references it
references the masters it uses instead (reference_rewrites). The records are not imported here:
the V2 editor builds and reads back each master (unreal/Scripts/import_asset.py, material-master), and tools/import/run.py
writes its verified.json.

States: `unprepared` (the adopted record lists all five masters, no master record exists) and `done` (the five records
exist, the adopted record is gone). Any other state refuses, so a half-moved set is never extended by a second write.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parents[1]
REPO = GAME.parents[1]
GAME_REL = 'games/yorimichi_v2'
sys.path.insert(0, str(GAME / 'tools' / 'content'))
sys.path.insert(0, str(HERE))
import authority  # noqa: E402
import records  # noqa: E402
import brinecove_split_apply as apply  # noqa: E402  (the journaled write every migrate step uses)

ADOPTED = 'adopted/hippodrome/materials'
OWNER = 'shared/hippodrome/materials'
LICENSE = 'owner-published (docs/DECISIONS.md D05 group 1)'
BUILDER = GAME / 'unreal/Scripts/material_masters/hippodrome_masters.py'
BUILDER_REL = 'src/hippodrome_masters.py'
PROVENANCE = ('donor generator games/yorimichi/unreal/Scripts/import_hippodrome.py at the V2 source baseline '
              '(docs/DECISIONS.md D01, D02)')
DONOR_LINES = {'surface': '36-55', 'structure_material': '59-78'}
TEXTURE_GRASS = '/Game/Hippodrome/Textures/T_Grass'
TEXTURE_DIRT = '/Game/Hippodrome/Textures/T_Dirt'
ENGINE_WHITE = '/Engine/EngineResources/WhiteSquareTexture'

# One record per master. `arguments` are the builder's keyword arguments; `reads` the packages the builder receives.
MASTERS = [
    {'id': 'master/hippodrome/structure', 'package': '/Game/Hippodrome/Materials/M_HD_Structure',
     'builder': 'structure_material', 'reads': [ENGINE_WHITE], 'inputs': [],
     'arguments': {'texture': ENGINE_WHITE}},
    {'id': 'master/hippodrome/grass', 'package': '/Game/Hippodrome/Materials/M_HD_Grass',
     'builder': 'surface', 'reads': [TEXTURE_GRASS], 'inputs': ['texture/hippodrome/grass'],
     'arguments': {'texture': TEXTURE_GRASS, 'roughness': 0.95, 'two_sided': False}},
    {'id': 'master/hippodrome/dirt', 'package': '/Game/Hippodrome/Materials/M_HD_Dirt',
     'builder': 'surface', 'reads': [TEXTURE_DIRT], 'inputs': ['texture/hippodrome/dirt'],
     'arguments': {'texture': TEXTURE_DIRT, 'roughness': 0.95, 'two_sided': False}},
    {'id': 'master/hippodrome/stone', 'package': '/Game/Hippodrome/Materials/M_HD_Stone',
     'builder': 'surface', 'reads': [], 'inputs': [],
     'arguments': {'colour_r': 0.36, 'colour_g': 0.35, 'colour_b': 0.32, 'roughness': 0.9, 'two_sided': True}},
    {'id': 'master/hippodrome/rail', 'package': '/Game/Hippodrome/Materials/M_HD_Rail',
     'builder': 'surface', 'reads': [], 'inputs': [],
     'arguments': {'colour_r': 0.86, 'colour_g': 0.85, 'colour_b': 0.80, 'roughness': 0.6, 'two_sided': False}},
]


class PlanError(RuntimeError):
    pass


STRUCTURE = 'master/hippodrome/structure'
REFERENCES_LINE = re.compile(r'^references = (\[.*\])$', re.M)


def reference_rewrites(game: Path) -> dict:
    """{rel: bytes} for every record that references the adopted record: the reference becomes the masters the record's slot
    materials name. A slot that is not a master is a mesh's own instance (the loose meshes, owned by adopted/hippodrome/meshes),
    whose parent is M_HD_Structure. A references line this cannot rewrite refuses."""
    by_package = {m['package']: m['id'] for m in MASTERS}
    out = {}
    for path in records.record_paths(game):
        rel = path.relative_to(game).as_posix()
        if rel == f'assets/{ADOPTED}/asset.toml':
            continue
        asset = records.load_asset(path)
        if ADOPTED not in asset.references:
            continue
        text = path.read_text()
        match = REFERENCES_LINE.search(text)
        if match is None or json.loads(match.group(1)) != asset.references:
            raise PlanError(f'{rel}: its references are not one rewritable line')
        slots = (asset.recipe.get('settings') or {}).get('slot_materials') or []
        masters = sorted({by_package.get(slot, STRUCTURE) for slot in slots}) or [STRUCTURE]
        new = []
        for ref in asset.references:
            for item in (masters if ref == ADOPTED else [ref]):
                if item not in new:
                    new.append(item)
        out[rel] = (text[:match.start(1)] + json.dumps(new) + text[match.end(1):]).encode()
    return out


def builder_sha() -> str:
    return hashlib.sha256(BUILDER.read_bytes()).hexdigest()


def _value(value) -> str:
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, str):
        return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'
    return repr(float(value)) if isinstance(value, float) else str(value)


def record_text(master: dict, sha: str) -> str:
    """The material-master record of one master (asset.toml). Parsed back by records.load_asset in the tests."""
    lines = [f'# Recovered as a material master (tools/migrate/master_records.py): {master["package"]}.',
             f'# The builder is {BUILDER_REL}, pinned by sha256; the master is rebuilt by the V2 editor and read back',
             '# against its saved original, never edited by hand.',
             'schema = 1', f'id = "{master["id"]}"', 'kind = "material-master"', 'authority = "generated"',
             f'owner = "{OWNER}"', f'license = "{LICENSE}"',
             f'provenance = "{PROVENANCE}, {master["builder"]} lines {DONOR_LINES[master["builder"]]}"']
    if master['inputs']:   # a top-level key: it must come before the first [[sources]] table
        lines.append('input_dependencies = [' + ', '.join(f'"{r}"' for r in master['inputs']) + ']')
    lines += ['', '[[sources]]', f'path = "{BUILDER_REL}"', f'sha256 = "{sha}"',
              '', '[recipe]', 'importer = "material-master"', 'version = 1', '', '[recipe.settings]',
              f'builder = "{master["builder"]}"',
              'reads = [' + ', '.join(f'"{r}"' for r in master['reads']) + ']',
              'arguments = { ' + ', '.join(f'{k} = {_value(v)}' for k, v in master['arguments'].items()) + ' }',
              '', '[[outputs]]', f'package = "{master["package"]}"', '']
    return '\n'.join(lines)


def state(game: Path) -> str:
    """'unprepared', 'done', or a PlanError naming what is half-moved."""
    adopted = game / f'assets/{ADOPTED}/asset.toml'
    present = [m['id'] for m in MASTERS if (game / f'assets/{m["id"]}/asset.toml').is_file()]
    packages = {m['package'] for m in MASTERS}
    listed = {o.package for o in records.load_asset(adopted).outputs} if adopted.is_file() else set()
    if not present and packages <= listed:
        return 'unprepared'
    if len(present) == len(MASTERS) and not (listed & packages):
        return 'done'
    raise PlanError(f'the hippodrome masters are half-moved: records {present}, adopted still lists '
                    f'{sorted(listed & packages)}; resolve by hand')


def claim_ops(game: Path) -> dict:
    """The one write: {'writes': {rel: bytes}, 'deletes': [rel]}. Empty when the state is done."""
    if state(game) == 'done':
        return {'writes': reference_rewrites(game), 'deletes': []}
    sha = builder_sha()
    writes = reference_rewrites(game)
    for master in MASTERS:
        folder = f'assets/{master["id"]}'
        writes[f'{folder}/asset.toml'] = record_text(master, sha).encode()
        writes[f'{folder}/{BUILDER_REL}'] = BUILDER.read_bytes()
    deletes = [f'assets/{ADOPTED}/{name}' for name in ('asset.toml', 'verified.json')
               if (game / f'assets/{ADOPTED}/{name}').is_file()]
    return {'writes': writes, 'deletes': deletes}


def claim_paths(game: Path) -> list[str]:
    ops = claim_ops(game)
    return sorted(set(ops['writes']) | set(ops['deletes']))


def materialize(game: Path, claim: str, *, echo=print) -> None:
    apply.Journal(game).recover(claim)
    ops = claim_ops(game)
    if not ops['writes'] and not ops['deletes']:
        echo('materialize: the hippodrome masters are already records and nothing references the adopted record; nothing written')
        return
    paths = claim_paths(game)
    try:
        authority.authorize([f'{GAME_REL}/{rel}' for rel in paths], claim,
                            'Yorimichi V2 hippodrome materials as material-master records', scopes=[OWNER])
    except authority.Unauthorized as error:
        raise PlanError(str(error)) from None
    apply.execute(game, ops, scopes=[OWNER])
    echo(f'materialize: {len(paths)} path(s) under {claim}')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--game', type=Path, default=GAME)
    parser.add_argument('--paths', action='store_true', help='print the claim paths and the scope')
    parser.add_argument('--claim', metavar='TASK', help='the one journaled write')
    args = parser.parse_args(argv)
    try:
        if args.claim:
            materialize(args.game, args.claim)
            return 0
        print(f'state: {state(args.game)}')
        if args.paths or state(args.game) == 'unprepared':
            for rel in claim_paths(args.game):
                print(f'path {GAME_REL}/{rel}')
            print(f'scopes: {OWNER}')
    except (PlanError, records.RecordError, authority.Unauthorized) as error:
        print(f'master_records: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
