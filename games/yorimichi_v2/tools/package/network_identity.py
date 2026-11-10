"""The multiplayer content manifest a V2 package carries: Content/Data/Network/session.json.

JapanNetwork::Identity refuses to host or join without it. The manifest binds the compiled code digest (the
YORIMICHI_NETWORK_BUILD_ID that Yorimichi.Build.cs generates), a digest of every imported package under Content, and the
SHA1 of each runtime data file, so two players with mixed builds are told so instead of desyncing. It detects
accidentally mixed builds; it is not authentication or an anti-cheat signature. Ported from the donor's
games/yorimichi/network_identity.py (step data.network) with the V2 roots.

The unreal.package step writes it before the cook (build.py). It is a build output, never committed: it changes with
every source edit, so Data/Network is ignored by Git and left out of the runtime data lock (tools/content/records.py).

    uv run python games/yorimichi_v2/tools/package/network_identity.py           # write the manifest, print its signature
    uv run python games/yorimichi_v2/tools/package/network_identity.py --code    # print only the code digest
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

GAME = Path(__file__).resolve().parents[2]
REPO = GAME.parents[1]
CONTENT = GAME / 'unreal/Content'
MANIFEST = 'Data/Network/session.json'   # Content-relative; JapanNetwork.cpp reads AtelierDataPath("Network/session.json")
PROTOCOL = 1                              # JapanNetwork::Protocol
# Yorimichi.Build.cs: the roots, suffixes and ignored folder names its code digest enumerates.
CODE_ROOTS = ('games/yorimichi_v2/unreal/Source', 'games/yorimichi_v2/unreal/Config', 'games/yorimichi_v2/unreal/Plugins',
              'platform/engine/Plugins')
CODE_SUFFIXES = {'.h', '.hpp', '.cpp', '.c', '.cs', '.uplugin', '.inl', '.inc', '.mm', '.m', '.ush', '.usf', '.ini',
                 '.uproject'}
IGNORED = {'Binaries', 'Intermediate', 'Saved', 'DerivedDataCache', '__pycache__'}
DESKTOP_METADATA = {'.ds_store', 'thumbs.db'}
PACKAGE_SUFFIXES = {'.uasset', '.umap', '.uexp', '.ubulk'}


def sha1_file(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha1').hexdigest()


def records_digest(records) -> str:
    """Canonical UTF-8 path + NUL + lowercase SHA1 + newline, ordered by path (Build.cs and JapanNetwork.cpp)."""
    digest = hashlib.sha1()
    for entry in sorted(records, key=lambda entry: entry['path']):
        digest.update(f"{entry['path']}\0{entry['sha1']}\n".encode('utf-8'))
    return digest.hexdigest()


def code_files(repo: Path = REPO) -> list[Path]:
    """Build.cs's enumeration: the roots plus the project descriptor, ignored names anywhere in the repo-relative path."""
    files = [p for root in CODE_ROOTS for p in (repo / root).rglob('*') if p.is_file()]
    files.extend((repo / 'games/yorimichi_v2/unreal').glob('*.uproject'))
    files = [p for p in files if p.suffix in CODE_SUFFIXES and not IGNORED & set(p.relative_to(repo).parts)]
    return sorted(set(files), key=lambda p: p.relative_to(repo).as_posix())


def code_identity(repo: Path = REPO) -> str:
    """@cc [owner:fontanierh,label:correctness] network-code-identity
    MUST equal Yorimichi.Build.cs's YORIMICHI_NETWORK_BUILD_ID for the same tree: the same files, ordering and record
    format, with CRLF folded to LF for source only. A mismatch makes every package refuse to host or join."""
    return records_digest([{'path': p.relative_to(repo).as_posix(),
                            'sha1': hashlib.sha1(p.read_bytes().replace(b'\r\n', b'\n')).hexdigest()}
                           for p in code_files(repo)])


def content_files(content: Path = CONTENT) -> list[Path]:
    """Every file under Content except build folders, desktop metadata and the manifest's own folder, by relative path."""
    files = []
    for path in content.rglob('*'):
        if not path.is_file():
            continue
        relative = path.relative_to(content)
        if (IGNORED & set(relative.parts) or path.name.casefold() in DESKTOP_METADATA
                or relative.is_relative_to(Path(MANIFEST).parent)):
            continue
        files.append((relative.as_posix(), path))
    return [path for _, path in sorted(files)]


def signature(code: str, assets: str, files) -> str:
    """JapanNetwork::Identity's check: SHA1 of protocol, code, asset digest and data-file digest, one per line."""
    return hashlib.sha1(f'{PROTOCOL}\n{code}\n{assets}\n{records_digest(files)}\n'.encode('ascii')).hexdigest()


def manifest(repo: Path = REPO, content: Path = CONTENT) -> dict:
    files, assets = [], []
    paths = content_files(content)
    if not (content / 'Data/world.json').is_file() or not any(p.suffix == '.umap' for p in paths):
        raise ValueError('cannot certify multiplayer content before the world data and a map exist')
    for path in paths:
        if path.is_relative_to(content / 'Data'):
            files.append({'path': path.relative_to(content / 'Data').as_posix(), 'sha1': sha1_file(path)})
        elif path.suffix in PACKAGE_SUFFIXES:
            assets.append({'path': path.relative_to(content).as_posix(), 'sha1': sha1_file(path)})
    code = code_identity(repo)
    asset_hash = records_digest(assets)
    return {'protocol': PROTOCOL, 'code': code, 'assets': asset_hash, 'signature': signature(code, asset_hash, files),
            'files': files, 'packages': len(assets)}


def write(repo: Path = REPO, content: Path = CONTENT) -> dict:
    """Write the manifest atomically; rewriting identical bytes is skipped so an unchanged tree stays unchanged."""
    result = manifest(repo, content)
    destination = content / MANIFEST
    text = json.dumps(result, indent=2, sort_keys=True) + '\n'
    if not destination.is_file() or destination.read_text() != text:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix('.tmp')
        temporary.write_text(text)
        temporary.replace(destination)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--code', action='store_true', help='print only the code digest')
    args = parser.parse_args(argv)
    if args.code:
        print(code_identity())
        return 0
    result = write()
    print(f'NETWORK IDENTITY {result["signature"]}: code {result["code"]}, {len(result["files"])} data files, '
          f'{result["packages"]} packages')
    return 0


if __name__ == '__main__':
    sys.exit(main())
