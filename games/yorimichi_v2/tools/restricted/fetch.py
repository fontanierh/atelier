"""Restricted content (DECISIONS D05 group 2): packages that never go to public Git LFS, pinned by hash and fetched.

`restricted.toml` declares the /Game roots (ignored by Git) and the lock; `restricted.lock.json` pins every file under
them by Content-relative path, sha256 and size. The bytes live in authorized restricted storage, made available as a
plain directory laid out like `unreal/Content` and named by `$V2_RESTRICTED_SOURCE` (or `--source`); the repository
holds only the lock, never the bytes, a host or a path to them.

    V2_RESTRICTED_SOURCE=DIR uv run python games/yorimichi_v2/tools/restricted/fetch.py fetch
    uv run python games/yorimichi_v2/tools/restricted/fetch.py pin [--prune]

`fetch` copies each pinned file that is absent here, verifying the copied bytes against the pin; it refuses a source
file that disagrees and never overwrites a local file that differs from its pin. `pin` records the local files
(after adoption, or a claimed and validated edit), keeping the pins of files absent here unless `--prune`; the
storage must then receive the same bytes.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

GAME = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(GAME / 'tools/content'))
import records  # noqa: E402
from records import RecordError  # noqa: E402

SUFFIXES = records.PACKAGE_EXTENSIONS + records.COMPANION_EXTENSIONS


def local_files(game: Path, restricted: records.Restricted) -> dict[str, Path]:
    """Content-relative path -> file for every package file present under the restricted roots."""
    content = game / 'unreal' / 'Content'
    return {p.relative_to(content).as_posix(): p for folder in restricted.folders
            for p in sorted((content / folder).rglob('*')) if p.is_file() and p.name.endswith(SUFFIXES)}


def pin(game: Path, *, prune: bool = False, echo=print) -> dict[str, dict]:
    restricted = records.load_restricted(game)
    if not restricted.roots:
        raise RecordError(f'{game}: no restricted roots declared (restricted.toml)')
    files = {} if prune else dict(records.load_lock(restricted))
    for rel, path in local_files(game, restricted).items():
        files[rel] = {'sha256': records.sha256_file(path), 'size': path.stat().st_size}
    changed = records.write_json(restricted.lock, {'schema': records.SCHEMA, 'files': dict(sorted(files.items()))})
    echo(f'{len(files)} restricted file(s) pinned{"" if changed else " (unchanged)"}')
    return files


def fetch(game: Path, source: Path | None = None, *, echo=print) -> tuple[int, list[str]]:
    """(files copied, refusals). Every copied file is exactly its pin; nothing local is ever replaced."""
    restricted = records.load_restricted(game)
    pinned = records.load_lock(restricted)
    if source is None:
        value = os.environ.get(restricted.source_env)
        if not value:
            raise RecordError(f'set {restricted.source_env} to the authorized restricted storage directory')
        source = Path(value)
    if not source.is_dir():
        raise RecordError(f'restricted source {restricted.source_env} is not a directory')
    content = game / 'unreal' / 'Content'
    copied, refused = 0, []
    for rel, entry in sorted(pinned.items()):
        dest, origin = content / rel, source / rel
        if dest.is_file():
            if records.sha256_file(dest) != entry['sha256']:
                refused.append(f'{rel}: local file differs from its pin; never overwritten (delete it to restore, '
                               'or pin a claimed edit)')
            continue
        if not origin.is_file():
            refused.append(f'{rel}: not in the restricted source')
            continue
        if origin.stat().st_size != entry['size']:
            refused.append(f'{rel}: source size differs from its pin; refused')
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + '.tmp')
        try:
            with origin.open('rb') as src, tmp.open('wb') as out:
                for block in iter(lambda: src.read(1 << 20), b''):
                    out.write(block)
            if records.sha256_file(tmp) != entry['sha256']:
                refused.append(f'{rel}: source hash differs from its pin; refused')
                continue
            tmp.replace(dest)
            copied += 1
        finally:
            tmp.unlink(missing_ok=True)
    echo(f'{copied} restricted file(s) fetched, {len(pinned) - copied - len(refused)} already present, '
         f'{len(refused)} refused')
    return copied, refused


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    get = sub.add_parser('fetch', help='copy pinned restricted files in, verified against the lock')
    get.add_argument('--source', type=Path, help='restricted storage directory (default: the env var restricted.toml names)')
    put = sub.add_parser('pin', help='record the local restricted files in the lock')
    put.add_argument('--prune', action='store_true', help='drop pins of files absent here')
    parser.add_argument('--game', type=Path, default=GAME, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if args.command == 'pin':
            pin(args.game.resolve(), prune=args.prune)
            return 0
        _, refused = fetch(args.game.resolve(), args.source)
    except RecordError as error:
        print(f'restricted {args.command} failed: {error}', file=sys.stderr)
        return 1
    for problem in refused:
        print(f'  {problem}', file=sys.stderr)
    return 1 if refused else 0


if __name__ == '__main__':
    sys.exit(main())
