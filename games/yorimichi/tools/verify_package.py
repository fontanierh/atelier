"""Verify release files and independently extract the macOS app; no game is launched.

Run from the repo root with uv run python games/yorimichi/tools/verify_package.py --help.
Extraction uses the normal render admission and memory guard. Other checks are read-only.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import time

from atelier.safety import guarded
from package_archive import AUDIO_SERVICE, MACH_LOOKUP, STAGED_DATA

MACHO = {b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca',
         b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca'}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def leaf(value):
    require(isinstance(value, str) and value not in ('', '.', '..') and Path(value).name == value and '\\' not in value,
            'manifest names must be single path components')
    return value


def checksum(path):
    digest = hashlib.sha256()
    started = spoken = time.monotonic()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1 << 20), b''):
            digest.update(block)
            now = time.monotonic()
            require(now - started < 2700, 'checksum exceeded 45 minutes')
            if now - spoken >= 25:
                print(f'checksum: {path.name}, {now - started:.0f} s elapsed', flush=True)
                spoken = now
    return digest.hexdigest()


def release_inputs(root, expected_revision=None):
    manifest = json.loads((root / 'manifest.json').read_text())
    leaf(manifest['app']); leaf(manifest['launcher']); leaf(manifest['zip'])
    revision = manifest.get('cook', {}).get('revision', manifest['revision'])
    if expected_revision:
        require(revision == expected_revision, 'archive source revision differs from the requested revision')
    entries = manifest['files']
    require(bool(entries), 'release manifest contains no files')
    names = [leaf(entry['file']) for entry in entries]
    require(len(names) == len(set(names)), 'duplicate release files')
    if manifest['split']:
        expected = [manifest['zip'] + '.part-' + chr(97 + i // 26) + chr(97 + i % 26) for i in range(len(names))]
        require(len(names) <= 26 * 26 and names == expected, 'release parts are missing or out of order')
    else:
        require(names == [manifest['zip']], 'unsplit release must contain its one ZIP')
    sums = ''.join(f"{entry['sha256']}  {entry['file']}\n" for entry in entries)
    require((root / 'SHA256SUMS').read_text() == sums, 'SHA256SUMS differs from the manifest')
    for entry in entries:
        path = root / entry['file']
        require(path.is_file() and not path.is_symlink() and path.stat().st_size == entry['bytes'],
                f"missing or wrong-size release file: {entry['file']}")
        require(checksum(path) == entry['sha256'], f"checksum mismatch: {entry['file']}")
        print(f"verified release file: {entry['file']}", flush=True)
    return manifest, revision, [root / name for name in names]


def expand_dyld(path, loader, executable):
    if path == '@loader_path' or path.startswith('@loader_path/'):
        return loader / path[len('@loader_path'):].lstrip('/')
    if path == '@executable_path' or path.startswith('@executable_path/'):
        return executable.parent / path[len('@executable_path'):].lstrip('/')
    return Path(path)


def native_dependencies(app, executable):
    """Resolve every required bundled Mach-O dependency inside the app; optional weak links stay explicit."""
    def commands(path):
        return subprocess.check_output(['otool', '-l', str(path)], text=True, timeout=120)
    main = commands(executable)
    rpaths = lambda text: re.findall(r'cmd LC_RPATH\n.*?path (.*?) \(offset', text, re.S)
    result, weak, binaries = [], [], []
    for item in sorted(app.rglob('*')):
        if not item.is_file() or item.is_symlink():
            continue
        with item.open('rb') as source:
            if source.read(4) not in MACHO:
                continue
        text = commands(item)
        search = [expand_dyld(path, item.parent, executable) for path in rpaths(text)] + [
            expand_dyld(path, executable.parent, executable) for path in rpaths(main)]
        for block in re.split(r'Load command \d+\n', text):
            kind = re.search(r'^\s*cmd (LC_LOAD_DYLIB|LC_LOAD_WEAK_DYLIB|LC_REEXPORT_DYLIB|LC_LOAD_UPWARD_DYLIB)\s*$', block, re.M)
            name = re.search(r'^\s*name (.*?) \(offset', block, re.M)
            if not kind or not name or name[1].startswith(('/System/Library/', '/usr/lib/')):
                continue
            library = name[1]
            require(library.startswith(('@rpath/', '@loader_path/', '@executable_path/')),
                    f'{item.name} depends on a local installation: {library}')
            candidates = [base / library[len('@rpath/'):] for base in search] if library.startswith('@rpath/') else [
                expand_dyld(library, item.parent, executable)]
            found = [path.resolve() for path in candidates if path.is_file() and app.resolve() in path.resolve().parents]
            entry = dict(loader=str(item.relative_to(app)), library=library)
            if not found and kind[1] == 'LC_LOAD_WEAK_DYLIB':
                weak.append(entry)
            else:
                require(bool(found), f'{item.name} has an unresolved required library: {library}')
                result.append(dict(**entry, resolved=str(found[0].relative_to(app.resolve()))))
        binaries.append(str(item.relative_to(app)))
    return dict(binaries=binaries, resolved=result, optional_weak_links=weak)


def app_checks(folder, manifest, communitypark=False):
    app, launcher = folder / manifest['app'], folder / manifest['launcher']
    require(app.is_dir() and launcher.is_file() and os.access(launcher, os.X_OK), 'app or executable launcher missing')
    metadata = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
    executable = app / 'Contents/MacOS' / leaf(metadata['CFBundleExecutable'])
    require(executable.is_file() and os.access(executable, os.X_OK), 'game executable missing or not executable')
    architectures = subprocess.check_output(['lipo', '-archs', str(executable)], text=True, timeout=120).strip()
    require('arm64' in architectures.split(), 'app has no Apple silicon executable')
    dependencies = native_dependencies(app, executable)
    require(str(executable.relative_to(app)) in dependencies['binaries'], 'game is not a Mach-O executable')
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True, timeout=120)
    raw = subprocess.check_output(['codesign', '-d', '--entitlements', '-', '--xml', str(app)], timeout=120)
    entitlements = plistlib.loads(raw) if raw.strip() else {}
    if entitlements.get('com.apple.security.app-sandbox'):
        require(AUDIO_SERVICE in entitlements.get(MACH_LOOKUP, []), 'sandbox lacks its CoreAudio lookup allowance')
    roots = list(app.glob('Contents/UE/*/Content/Data'))
    require(len(roots) == 1, 'expected one staged Content/Data root')
    required = [*STAGED_DATA, 'hidamari/city.json'] + (['communitypark/park.json'] if communitypark else [])
    for relative in required:
        require((roots[0] / relative).is_file(), f'missing staged data: {relative}')
    for path in app.rglob('*'):
        if path.is_symlink():
            require(path.exists() and app.resolve() in path.resolve().parents, f'broken or external symlink: {path.name}')
    return dict(architectures=architectures, dependencies=dependencies, required_data=required,
                bundle=metadata, entitlements=entitlements, launcher_sha256=checksum(launcher))


def verify(root, destination, report, *, expected_revision=None, communitypark=False):
    root, destination, report = root.resolve(), destination.resolve(), report.resolve()
    require(not destination.exists(), 'choose a new extraction directory; old extracted apps are never reused')
    require(not report.exists(), 'choose a new report path; previous proofs are never reused')
    require(destination != root and root not in destination.parents, 'extract outside the package directory')
    manifest, revision, files = release_inputs(root, expected_revision)
    destination.mkdir(parents=True)
    archive = files[0]
    if manifest['split']:
        archive = destination / 'joined-release.zip'
        with archive.open('wb') as output:
            for path in files:
                with path.open('rb') as source:
                    for block in iter(lambda: source.read(1 << 20), b''):
                        output.write(block)
                print(f'joined verified part: {path.name}', flush=True)
    code = guarded.run(['ditto', '-x', '-k', str(archive), str(destination)], report.parent / (report.stem + '.guard'),
                       timeout=900, kind='job', small_gib=3, watch=('ditto',), purpose='independent release extraction')
    require(code == 0, 'guarded archive extraction failed')
    proof = dict(revision=revision, files=manifest['files'], **app_checks(destination / 'Yorimichi', manifest, communitypark))
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(proof, indent=2) + '\n')
    print(f'PASS independent release verification: {report}', flush=True)
    return proof


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--extract', type=Path, required=True, help='new independent extraction directory')
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--expected-revision', help='exact full cook revision, or short revision for an older manifest')
    parser.add_argument('--require-communitypark', action='store_true')
    args = parser.parse_args(argv)
    verify(args.package, args.extract, args.report, expected_revision=args.expected_revision, communitypark=args.require_communitypark)


if __name__ == '__main__':
    main()
