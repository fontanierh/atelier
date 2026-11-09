"""Retire the 14 standalone Belmonte train LOD meshes that nothing uses. This is a retirement, not an import.

    uv run python games/yorimichi_v2/tools/migrate/belmontetrain_lods.py --check [--game PATH]   # state and proof; writes nothing
    uv run python games/yorimichi_v2/tools/migrate/belmontetrain_lods.py --paths [--json]        # every path and scope a claim needs
    uv run python games/yorimichi_v2/tools/migrate/belmontetrain_lods.py --claim TASK            # the retirement, one journaled write

The seven adopted records (assets/adopted/belmontetrain/<unit>) each list two standalone meshes,
/Game/BelmonteTrain/Source/SM_BT_<V>/SM_BT_<V>_LOD1 and _LOD2. Nothing uses them: the vehicle records
(assets/prop/belmontetrain/<v>) pin the full LOD chain from the GLB sources, and unreal/Scripts/import_asset.py imports
LOD1 and LOD2 as transient meshes, attaches them and deletes them. They are donor leftovers, so they are retired.

The retirement is one write through brinecove_split_apply.execute, under the seven owners' scopes:
- the 14 [[outputs]] blocks leave the seven records (recover._drop_outputs; every other byte stays);
- the 14 verified.json entries leave (every extension of each package stem), and so do the 14 units.json package entries;
- the 14 .uasset files are deleted, with any .uexp, .ubulk or .umap of the same stem.

States: `unretired` (each record lists its two LOD outputs) and `retired` (none of the 14 is listed or on disk). Any other
state is refused, and a rerun after the retirement is a no-op. Nothing is written before the referencer proof passes: no
tracked file other than the 14 may name a package path (UTF-8 or UTF-16, case-insensitively). The seven records,
their verified.json and units.json are judged in the form they will have after the retirement. A Git LFS pointer among
the scanned files cannot be proven clean, so the proof refuses on one. --check runs the same proof and writes nothing;
it may be run against any checkout with --game.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parents[1]
REPO = GAME.parents[1]
sys.path.insert(0, str(GAME / 'tools' / 'content'))
import authority  # noqa: E402
import records  # noqa: E402
sys.path.insert(0, str(HERE))
import brinecove_split_apply as apply  # noqa: E402  (Journal and execute: the journaled write every migrate step uses)
import recover  # noqa: E402  (_drop_outputs: a record's text without the given [[outputs]] blocks)

GAME_REL = 'games/yorimichi_v2'
RECORDS = 'assets/adopted/belmontetrain'
UNITS_REL = f'{RECORDS}/units.json'
MESH = '/Game/BelmonteTrain/Source/SM_BT_{v}/SM_BT_{v}_LOD{n}'
# record unit -> the vehicle's mesh name in its package paths
UNITS = {'baggage-van': 'BaggageVan', 'brake-van': 'BrakeVan', 'first-class': 'FirstClass', 'locomotive': 'Locomotive',
         'restaurant': 'Restaurant', 'second-class': 'SecondClass', 'tender': 'Tender'}
EXPECTED = {unit: sorted(MESH.format(v=v, n=n) for n in (1, 2)) for unit, v in UNITS.items()}
PACKAGES = sorted(p for packages in EXPECTED.values() for p in packages)          # the 14
PACKAGE_SET = set(PACKAGES)
STEMS = {'unreal/Content/' + p[len('/Game/'):] for p in PACKAGES}                  # a verified.json key minus its extension
EXTENSIONS = ('.uasset', '.umap', '.uexp', '.ubulk')
LOD = re.compile(r'^/Game/BelmonteTrain/Source/SM_BT_[A-Za-z0-9]+/SM_BT_[A-Za-z0-9]+_LOD\d$')
SCOPES = sorted(f'shared/belmontetrain/{unit}' for unit in UNITS)


class LodError(RuntimeError):
    pass


@dataclass
class Plan:
    writes: dict            # game-relative path -> new bytes
    deletes: list           # game-relative paths

    def paths(self) -> list:
        return sorted(set(self.writes) | set(self.deletes))


def canonical(data: dict) -> bytes:
    """verified.json's form (records.write_json's text)."""
    return (json.dumps(data, indent=2, sort_keys=True) + '\n').encode()


def stem_of(rel: str) -> str:
    return rel.rsplit('.', 1)[0]


def is_retired_file(rel: str) -> bool:
    """A file of one of the 14 packages (the .uasset or a companion of its stem)."""
    return rel.endswith(EXTENSIONS) and stem_of(rel) in STEMS


def package_rels(game: Path, package: str) -> list:
    """The game-relative files of one package that exist: its .uasset, .umap, .uexp and .ubulk."""
    stem = game / 'unreal' / 'Content' / package[len('/Game/'):]
    return [(stem.parent / (stem.name + ext)).relative_to(game).as_posix() for ext in EXTENSIONS
            if (stem.parent / (stem.name + ext)).is_file()]


def unit_record(game: Path, unit: str):
    """(game-relative record path, loaded record) of one unit; refuses anything that is not that source-less adopted record."""
    rel = f'{RECORDS}/{unit}/asset.toml'
    path = game / rel
    if not path.is_file():
        raise LodError(f'{rel} is missing')
    asset = records.load_asset(path)
    if (asset.id != f'adopted/belmontetrain/{unit}' or asset.kind != 'adopted' or asset.owner != f'shared/belmontetrain/{unit}'
            or asset.sources or asset.recipe is not None):
        raise LodError(f'{rel}: not the source-less adopted record of {unit}')
    return rel, asset


def leftovers(game: Path) -> list:
    """What the retirement removes that is still listed or on disk: verified entries, units.json keys, package files."""
    out = []
    for unit in UNITS:
        verified = game / RECORDS / unit / 'verified.json'
        if verified.is_file():
            out += [f'{RECORDS}/{unit}/verified.json {key}' for key in json.loads(verified.read_text()).get('files', {})
                    if stem_of(key) in STEMS]
    units = game / UNITS_REL
    if units.is_file():
        out += [f'{UNITS_REL} {p}' for p in json.loads(units.read_text()).get('packages', {}) if p in PACKAGE_SET]
    for package in PACKAGES:
        out += package_rels(game, package)
    return out


def state(game: Path) -> str:
    """`unretired` (every record lists its two LOD outputs) or `retired` (none of the 14 is left). Anything else is refused."""
    listed = 0
    for unit in UNITS:
        _, asset = unit_record(game, unit)
        lods = sorted(o.package for o in asset.outputs if LOD.match(o.package))
        if lods not in ([], EXPECTED[unit]):
            raise LodError(f'{unit}: its LOD outputs are {lods}, not {EXPECTED[unit]}; nothing changed')
        listed += len(lods)
    if listed == len(PACKAGES):
        return 'unretired'
    left = leftovers(game)
    if listed == 0 and not left:
        return 'retired'
    raise LodError(f'partial: the records list {listed} of the 14 LOD outputs and {len(left)} leftover(s) remain '
                   f'({", ".join(left[:3])}); resolve by hand, nothing changed')


def build(game: Path) -> Plan:
    """The retirement's writes and deletes, computed in memory from the records as they are (state `unretired`)."""
    writes, deletes = {}, []
    units_text = (game / UNITS_REL).read_text()
    units = json.loads(units_text)
    if json.dumps(units, indent=1, ensure_ascii=False) + '\n' != units_text:
        raise LodError(f'{UNITS_REL} is not in the form adoption writes; edit it by hand')
    package_units = units.get('packages', {})
    for unit in UNITS:
        rel, asset = unit_record(game, unit)
        text = (game / rel).read_text()
        new = recover._drop_outputs(text, set(EXPECTED[unit]))
        if len(tomllib.loads(new).get('outputs', [])) != len(asset.outputs) - len(EXPECTED[unit]):
            raise LodError(f'{rel}: dropping the LOD outputs changed other outputs; refused')
        if new != text:
            writes[rel] = new.encode()
        verified = game / RECORDS / unit / 'verified.json'
        if verified.is_file():
            vrel = verified.relative_to(game).as_posix()
            data = json.loads(verified.read_text())
            if canonical(data).decode() != verified.read_text():
                raise LodError(f'{vrel} is not in the canonical form; edit it by hand')
            kept = {k: v for k, v in data.get('files', {}).items() if stem_of(k) not in STEMS}
            if kept != data.get('files', {}):
                if kept:
                    data['files'] = kept
                    writes[vrel] = canonical(data)
                else:
                    deletes.append(vrel)
        for package in EXPECTED[unit]:
            if package in package_units and package_units[package] != unit:
                raise LodError(f'{UNITS_REL}: {package} belongs to {package_units[package]!r}, not {unit!r}')
            deletes += package_rels(game, package)
    for package in PACKAGES:
        package_units.pop(package, None)
    if json.dumps(units, indent=1, ensure_ascii=False) + '\n' != units_text:
        writes[UNITS_REL] = (json.dumps(units, indent=1, ensure_ascii=False) + '\n').encode()
    return Plan(writes, sorted(set(deletes)))


def scanned(game: Path) -> list:
    """The files the proof reads: the tracked files of a Git checkout, or every file of a folder that is not one."""
    probe = subprocess.run(['git', '-C', str(game), 'rev-parse', '--is-inside-work-tree'], capture_output=True, text=True)
    if probe.returncode == 0 and probe.stdout.strip() == 'true':
        listing = subprocess.run(['git', '-C', str(game), 'ls-files', '-z'], capture_output=True, text=True, check=True).stdout
        return sorted(rel for rel in listing.split('\0') if rel)
    return sorted(p.relative_to(game).as_posix() for p in game.rglob('*') if p.is_file())


def needles() -> dict:
    return {p: (p.lower().encode(), p.lower().encode('utf-16-le')) for p in PACKAGES}


def proof(game: Path, plan: Plan) -> tuple:
    """@cc [owner:jim5,label:safety] belmontetrain-lod-unreferenced
    Retirement MUST NOT write while any tracked file other than the 14 packages themselves names one of them, as UTF-8
    or UTF-16, in the form it will have after the retirement (the planned bytes for the records, verified.json and
    units.json). A Git LFS pointer among the scanned files, the 14 included, cannot be proven unreferenced, so it refuses.
    Returns (problems, files read, pointers)."""
    problems, pointers, read = [], [], 0
    table = needles()
    for rel in scanned(game):
        path = game / rel
        if not path.is_file():
            continue
        if records.is_lfs_pointer(path):
            pointers.append(rel)
            continue
        if is_retired_file(rel):
            continue
        data = plan.writes[rel] if rel in plan.writes else path.read_bytes()
        read += 1
        low = data.lower()
        hits = [p for p, forms in table.items() if any(form in low for form in forms)]
        if hits:
            problems.append(f'{rel} names {hits[0]}')
    if pointers:
        problems.insert(0, f'{len(pointers)} Git LFS pointer file(s), e.g. {pointers[0]}: cannot prove the packages are '
                           'unreferenced; fetch the real files (git lfs pull) and rerun')
    return problems, read, len(pointers)


def journal_pending(game: Path) -> bool:
    return (game / apply.JOURNAL).is_dir()


def retire(game: Path, claim: str, *, lockable=apply.lockable_present, echo=print) -> str:
    """The claimed retirement. Recovers an interrupted journal first, then refuses before any write unless the state is
    `unretired` and the referencer proof is clean. A rerun after the retirement changes nothing."""
    apply.Journal(game).recover(claim)
    current = state(game)
    if current == 'retired':
        echo('retire: already retired; nothing written')
        return current
    plan = build(game)
    problems, read, pointers = proof(game, plan)
    if problems:
        raise LodError('retirement refused, nothing changed: ' + '; '.join(problems[:5]))
    try:
        authority.authorize([f'{GAME_REL}/{rel}' for rel in plan.paths()], claim, 'Belmonte LOD retirement', scopes=SCOPES)
    except authority.Unauthorized as error:
        raise LodError(str(error)) from None
    apply.execute(game, {'writes': plan.writes, 'deletes': plan.deletes}, scopes=SCOPES, lockable=lockable)
    if state(game) != 'retired':
        raise LodError('retirement did not leave the records retired; restore from the journal and report')
    echo(f'retire: {len(PACKAGES)} LOD packages removed from {len(UNITS)} records; {len(plan.deletes)} file(s) deleted')
    return 'retired'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Retire the 14 unused Belmonte train LOD meshes (see the docstring).')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='print the state and the referencer proof; writes nothing (default)')
    mode.add_argument('--paths', action='store_true', help='print every path and scope a claim needs, and exit')
    mode.add_argument('--claim', metavar='TASK', help='run the retirement under this claim')
    parser.add_argument('--game', metavar='PATH', help='the game folder to read (--check and --paths only)')
    parser.add_argument('--json', action='store_true', help='with --paths, print JSON')
    args = parser.parse_args(argv)
    if args.claim and args.game:
        print('belmontetrain_lods: --game is for --check and --paths; a claimed write runs in this checkout', file=sys.stderr)
        return 1
    game = Path(args.game).expanduser().resolve() if args.game else GAME
    try:
        if args.claim:
            retire(GAME, args.claim)
            return 0
        if args.paths:
            current = state(game)
            plan = Plan({}, []) if current == 'retired' else build(game)
            body = {'paths': [f'{GAME_REL}/{rel}' for rel in plan.paths()], 'scopes': SCOPES}
            if args.json:
                print(json.dumps(body, indent=1))
            else:
                print('\n'.join(body['paths']) or '(no paths: already retired)')
                print('scopes: ' + ' '.join(SCOPES))
            return 0
        current = state(game)
        plan = Plan({}, []) if current == 'retired' else build(game)
        problems, read, pointers = proof(game, plan)
        print(f'state: {current}; {len(PACKAGES)} packages; {len(plan.paths())} path(s) would change')
        if journal_pending(game):
            print('journal: an interrupted run is pending; the --claim run restores it first')
        if problems:
            print(f'referencer proof: refused ({read} files read, {pointers} pointer(s))')
            for line in problems[:20]:
                print('  ' + line)
            return 1
        print(f'referencer proof: clean ({read} files read, {pointers} pointer(s))')
        return 0
    except (LodError, records.RecordError, apply.SplitError) as error:
        print(f'belmontetrain_lods: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
