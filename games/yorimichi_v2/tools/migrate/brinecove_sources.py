"""Convert the carved Brine Cove tiles on this tree to the derived-source form (docs/inventory/brinecove-split.md).

    CMD="uv run python games/yorimichi_v2/tools/migrate/brinecove_sources.py"
    $CMD --check          which carved tile records reproduce byte-identically (no claim; writes nothing)
    $CMD --claim TASK     write the new form of every record that reproduces; refuses (and names) the others

A carved tile in the old form commits its remainder as its source. The new form (tools/content/carve.py) keeps the fused
original as its first pinned source instead, writes the selection (the triangles the remainder keeps) beside it, and
derives the remainder from the two during the targeted import. For each carved tile this tool:

1. finds the carved tiles from the split expectations on the tree (world/regions/*/split-*.json) whose record still
   commits the remainder: its one pinned source is a remainder that an expectation lists;
2. takes the original from the record's first commit in git history (the bytes recover.py pinned, read from the local
   LFS store) and checks them against that first pin;
3. matches the committed remainder's triangles to the original's, in order, to get the kept ordinals;
4. derives the remainder from original and selection and requires it to be byte-identical (sha256) to the committed one;
5. requires the record's import to be current (verified.json holds the fingerprint of the old form), so that the new
   fingerprint, written with the new source pins, makes the import unchanged: no package is rewritten and no placement
   moves.

Refused records keep the old form and are named; the others are still converted. With --claim the write goes through
authority.authorize and the import journal (brinecove_split_apply.execute), like the split tools.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import subprocess
import sys
import tomllib
from collections import defaultdict, deque
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parents[1]
sys.path.insert(0, str(GAME / 'tools' / 'content'))
sys.path.insert(0, str(HERE))
import brinecove_split_apply as apply  # noqa: E402
import carve  # noqa: E402
import records  # noqa: E402
from glb_subset import parse_glb, triangles  # noqa: E402

GAME_REL = apply.GAME_REL
LFS_HEADER = b'version https://git-lfs.github.com/spec/v1'


class ConvertError(RuntimeError):
    pass


def git(*args: str) -> bytes:
    return subprocess.run(['git', *args], cwd=apply.REPO, check=True, capture_output=True).stdout


def carved_records(game: Path) -> dict[str, dict]:
    """{record ID: {'shas': remainder hashes an expectation lists for it}} for every tile with a remainder, on this tree."""
    found: dict[str, dict] = {}
    for path in sorted((game / 'world' / 'regions').glob('*/split-*.json')):
        for tile in json.loads(path.read_text()).get('tiles', {}).values():
            if tile.get('remainder'):
                found.setdefault(tile['record'], {'shas': set()})['shas'].add(tile['remainder']['sha256'])
    return found


def original_of(asset_dir_rel: str, commit: str) -> tuple[str, str, bytes]:
    """(file name, sha256, bytes) of the record's first pinned source as it was committed in `commit`."""
    record = tomllib.loads(git('show', f'{commit}:{asset_dir_rel}/asset.toml').decode())
    source = record['sources'][0]
    raw = git('show', f'{commit}:{asset_dir_rel}/{source["path"]}')
    if raw.startswith(LFS_HEADER):
        oid = dict(line.split(' ', 1) for line in raw.decode().splitlines() if ' ' in line)['oid'].removeprefix('sha256:')
        common = Path(git('rev-parse', '--git-common-dir').decode().strip())
        store = (common if common.is_absolute() else apply.REPO / common) / 'lfs' / 'objects' / oid[:2] / oid[2:4] / oid
        if not store.is_file():
            raise ConvertError(f'the original {oid[:12]} is not in the local LFS store (git lfs pull --include it)')
        raw = store.read_bytes()
    return Path(source['path']).name, source['sha256'], raw


def kept_ordinals(original: dict, remainder: dict) -> list[int]:
    """The original's ordinals of the remainder's triangles, each triangle matched once, first occurrence first."""
    free: dict[tuple, deque] = defaultdict(deque)
    for n, key in enumerate(carve.triangle_keys(original)):
        free[key].append(n)
    kept, missing = [], 0
    for key in carve.triangle_keys(remainder):
        if free.get(key):
            kept.append(free[key].popleft())
        else:
            missing += 1
    if missing:
        raise ConvertError(f'{missing} remainder triangle(s) are not triangles of the original')
    return sorted(kept)


def prove(original: bytes, name: str, kept: list[int], total: int, remainder_sha: str) -> None:
    """@cc [owner:fontanierh,label:correctness] brinecove-source-conversion-proof
    A record converts only when the derived remainder (original plus selection) is byte-identical to the committed
    remainder, so the new form reproduces every accepted package input exactly. Any mismatch MUST refuse the record.
    """
    derived = carve.remainder_bytes(original, name, kept, total)
    if carve.sha256(derived) != remainder_sha:
        raise ConvertError(f'the derived remainder is {carve.sha256(derived)[:12]}, the committed one '
                           f'{remainder_sha[:12]}: not byte-identical')


def convert(game: Path, rid: str, shas: set[str]) -> dict:
    """{'id', 'status': 'converted' | 'refused' | 'done', 'why', 'writes': {game-relative: bytes}, 'asset'} for one record.
    Reads only. Its writes are the original, the selection, the new asset.toml and the re-pinned verified.json."""
    result = {'id': rid, 'status': 'refused', 'why': '', 'writes': {}, 'asset': None}
    folder = game / 'assets' / rid
    if not (folder / 'asset.toml').is_file():
        result['why'] = 'no record'
        return result
    text = (folder / 'asset.toml').read_text()
    try:
        asset = records.load_asset(folder / 'asset.toml')
    except records.RecordError as error:
        result['why'] = f'record does not load: {error}'
        return result
    result['asset'] = asset
    if asset.derive is not None:
        result.update(status='done', why='already in the derived form')
        return result
    if asset.authority != 'generated' or len(asset.sources) != 1 or asset.input_dependencies:
        result['why'] = 'not a single-source generated tile record'
        return result
    remainder_rel = asset.sources[0].path
    remainder = folder / remainder_rel
    if not remainder.is_file() or records.is_lfs_pointer(remainder):
        result['why'] = 'the committed remainder is not hydrated'
        return result
    remainder_bytes = remainder.read_bytes()
    remainder_sha = carve.sha256(remainder_bytes)
    if remainder_sha != asset.sources[0].sha256:
        result['why'] = 'the committed remainder differs from its pin'
        return result
    if remainder_sha not in shas:
        result['why'] = 'the committed remainder is not one a split expectation lists'
        return result
    try:
        commit = git('log', '--reverse', '--format=%H', '--', f'{GAME_REL}/assets/{rid}/asset.toml').decode().split()
        if not commit:
            raise ConvertError('no commit creates this record')
        name, original_sha, original = original_of(f'{GAME_REL}/assets/{rid}', commit[0])
        if name != Path(remainder_rel).name:
            raise ConvertError(f'the original is named {name}, the record {remainder_rel}')
        model = parse_glb(original, name)
        total = sum(1 for _ in triangles(model))
        kept = kept_ordinals(model, parse_glb(remainder_bytes, remainder_rel))
        prove(original, name, kept, total, remainder_sha)
        selection_rel = carve.selection_name(name)
        selection = carve.selection_text(total, kept).encode()
        verified = folder / 'verified.json'
        verified_data = json.loads(verified.read_text()) if verified.is_file() else None
        if verified_data is not None and verified_data.get('input_fingerprint') != records.input_fingerprint(asset, {}):
            raise ConvertError('its import is not current (verified.json has another fingerprint); import it first')
        new_text = text.replace(f'sha256 = "{remainder_sha}"', f'sha256 = "{original_sha}"', 1)
        new_text = new_text.replace(f'sha256 = "{original_sha}"',
                                    f'sha256 = "{original_sha}"\n\n[[sources]]\npath = "src/{selection_rel}"\n'
                                    f'sha256 = "{carve.sha256(selection)}"', 1)
        new_text = carve.with_derive(new_text, f'src/{name}', f'src/{selection_rel}')
        parsed = tomllib.loads(new_text)
        if [s['path'] for s in parsed['sources']] != [f'src/{name}', f'src/{selection_rel}'] or \
                parsed['sources'][0]['sha256'] != original_sha or parsed['derive']['selection'] != f'src/{selection_rel}':
            raise ConvertError('the converted asset.toml does not hold the pins it should')
        writes = {f'assets/{rid}/src/{name}': original,
                  f'assets/{rid}/src/{selection_rel}': selection,
                  f'assets/{rid}/asset.toml': new_text.encode()}
        if verified_data is not None:
            new = dataclasses.replace(
                asset, sources=[records.Source(f'src/{name}', original_sha),
                                records.Source(f'src/{selection_rel}', carve.sha256(selection))],
                derive=dict(parsed['derive']))
            verified_data['input_fingerprint'] = records.input_fingerprint(new, {})
            writes[f'assets/{rid}/verified.json'] = (json.dumps(verified_data, indent=2, sort_keys=True) + '\n').encode()
    except (ConvertError, carve.CarveError, ValueError, KeyError, IndexError, subprocess.CalledProcessError) as error:
        result['why'] = str(error)
        return result
    result.update(status='converted', writes=writes,
                  why=f'{len(kept)} of {total} triangles kept; the derived remainder is byte-identical')
    return result


def write(game: Path, results: list[dict], claim: str) -> int:
    """Write the converted records under one claim and the import journal; nothing else is touched."""
    todo = [r for r in results if r['status'] == 'converted']
    if not todo:
        return 0
    writes = {rel: data for r in todo for rel, data in r['writes'].items()}
    scopes = {apply.authority.asset_scope(r['asset']) for r in todo}
    apply.authority.authorize([f'{GAME_REL}/{rel}' for rel in sorted(writes)], claim,
                              'Brine Cove source conversion', scopes=scopes)
    done = apply.execute(game, {'writes': writes, 'deletes': []}, scopes=sorted(scopes, key=json.dumps))
    return len(done['written'])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--check', action='store_true', help='prove each record and write nothing (the default)')
    parser.add_argument('--claim', help='write the converted records under this claim (task ID)')
    args = parser.parse_args(argv)
    if args.check and args.claim:
        parser.error('use --check or --claim, not both')
    game = GAME
    results = [convert(game, rid, info['shas']) for rid, info in sorted(carved_records(game).items())]
    for r in results:
        if r['status'] == 'done':
            continue
        print(f'{r["status"].upper():10} {r["id"]}: {r["why"]}')
    counts = {s: sum(1 for r in results if r['status'] == s) for s in ('converted', 'refused', 'done')}
    print(f'carved tile records: {len(results)}; reproduce byte-identically: {counts["converted"]}; '
          f'refused: {counts["refused"]}; already in the derived form: {counts["done"]}')
    if args.claim:
        try:
            print(f'wrote {write(game, results, args.claim)} file(s)')
        except (apply.authority.Unauthorized, apply.SplitError, OSError) as error:
            print(f'write refused: {error}', file=sys.stderr)
            return 1
    return 1 if counts['refused'] else 0


if __name__ == '__main__':
    sys.exit(main())
