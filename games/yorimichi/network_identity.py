"""Compatibility identity for code, imported assets and the gameplay data actually staged.

This detects accidentally mixed builds; it is not authentication or an anti-cheat signature.
The compiled code digest binds the manifest to its module. Runtime checks rehash loose gameplay
files, while the asset digest is taken after imports and carried into each platform's cook.
"""
import hashlib
import json
from pathlib import Path

PROTOCOL = 1
CODE_SUFFIXES = {'.h', '.hpp', '.cpp', '.c', '.cs', '.uplugin', '.inl', '.inc', '.mm', '.m', '.ush', '.usf', '.ini', '.uproject'}
IGNORED = {'Binaries', 'Intermediate', 'Saved', 'DerivedDataCache', '__pycache__'}


def sha1_file(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha1').hexdigest()


def code_files(repo):
    roots = [repo / 'games/yorimichi/unreal/Source', repo / 'games/yorimichi/unreal/Config',
             repo / 'platform/engine/Plugins']
    files = [p for root in roots for p in root.rglob('*')
                   if p.is_file() and p.suffix in CODE_SUFFIXES
                   and not (set(p.relative_to(root).parts) & IGNORED)]
    files.extend((repo / 'games/yorimichi/unreal').glob('*.uproject'))
    return sorted(files, key=lambda p: p.relative_to(repo).as_posix())


def records_digest(records):
    """Canonical UTF-8 path + NUL + lowercase SHA1 + newline, ordered by relative path."""
    digest = hashlib.sha1()
    for entry in sorted(records, key=lambda entry: entry['path']):
        digest.update(f"{entry['path']}\0{entry['sha1']}\n".encode('utf-8'))
    return digest.hexdigest()


def code_identity(repo):
    return records_digest([{'path': p.relative_to(repo).as_posix(), 'sha1': sha1_file(p)}
                           for p in code_files(repo)])


def content_files(content):
    """Never include the identity's own output or generated editor/cache files."""
    return sorted((p for p in content.rglob('*') if p.is_file()
                   and not (set(p.relative_to(content).parts) & IGNORED)
                   and p.name != '.DS_Store'
                   and not p.is_relative_to(content / 'Data/Network')),
                  key=lambda p: p.relative_to(content).as_posix())


def signature(code, assets, records):
    data = f'{PROTOCOL}\n{code}\n{assets}\n{records_digest(records)}\n'
    return hashlib.sha1(data.encode('ascii')).hexdigest()


def create(repo, content, log):
    files, assets = [], []
    paths = content_files(content)
    if not (content / 'Data/world.json').is_file() or not any(p.suffix == '.umap' for p in paths):
        raise ValueError('Cannot certify multiplayer content before world data and the imported map exist')
    for index, path in enumerate(paths):
        if path.is_relative_to(content / 'Data'):
            files.append({'path': path.relative_to(content / 'Data').as_posix(), 'sha1': sha1_file(path)})
        elif path.suffix in {'.uasset', '.umap', '.uexp', '.ubulk'}:
            assets.append({'path': path.relative_to(content).as_posix(), 'sha1': sha1_file(path)})
        if index % 250 == 0:
            log.write(f'network identity: checked {index + 1}/{len(paths)} content files\n')
            log.flush()
    code = code_identity(repo)
    asset_hash = records_digest(assets)
    result = {'protocol': PROTOCOL, 'code': code, 'assets': asset_hash,
              'signature': signature(code, asset_hash, files), 'files': files}
    destination = content / 'Data/Network/session.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    temporary.replace(destination)
    log.write(f'NETWORK IDENTITY {result["signature"]}: {len(files)} data files, {len(assets)} imported assets\n')
    return result


def stage(ctx, log):
    from atelier import paths
    create(paths.REPO, ctx.uproject.parent / 'Content', log)
