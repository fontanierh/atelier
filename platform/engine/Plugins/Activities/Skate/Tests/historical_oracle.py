#!/usr/bin/env python3
"""Test-only original source/assets from immutable Git history.

No checkout vendor or normal-build dependency, network fetch, source substitution
or compiler execution. Source staging changes only checked probe #[path] spans.
Asset restoration is explicit, uses --game, and stays in ignored build storage.
"""
import argparse
from functools import lru_cache
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
import zipfile

PLUGIN = Path(__file__).resolve().parents[1]
ROOT = PLUGIN.parents[4]
REFERENCE_COMMIT = '46513a635cd8f46b1f5af43cf56679358143ae51'
SOURCE_GIT_PATH = 'platform/engine/Plugins/Activities/Skate/ThirdParty/skate-runtime'
SOURCE_TREE = '065ff7a0200f579d3d3cd518a40726412d0a65eb'
ASSET_ZIP_SHA256 = '85adf3a254a5145839f242f8a7fe04991b70a105bd2f4e34a183912f171d9b7a'
ASSET_ZIP_BLOB = 'eb13dea741ad91eceab2757b61c34a2e5e5d2ad9'
ASSET_MANIFEST_BLOB = 'caa93936e8d8c441916ba2f6dee522dd4d76ce91'
TOOLCHAIN_GUIDANCE = (
    'Original probes require Rust 1.97.1. Install it explicitly with rustup '
    'toolchain install 1.97.1. An empty Cargo cache cannot satisfy --offline '
    'probes: populate the pinned dependency cache explicitly with cargo '
    '+1.97.1 fetch --locked --manifest-path <snapshot>/atelier-host/Cargo.toml '
    'before the guarded build. This helper never installs, fetches or compiles.')

class HistoricalOracleError(RuntimeError):
    pass

def _sha(raw):
    return hashlib.sha256(raw).hexdigest()

def _relative(value):
    value = str(value)
    if not value or '\\' in value or '\0' in value or ':' in value:
        raise HistoricalOracleError('Unsafe historical relative path: ' + repr(value))
    parts = value.split('/')
    if any(part in ('', '.', '..') for part in parts) or PurePosixPath(value).is_absolute():
        raise HistoricalOracleError('Unsafe historical relative path: ' + repr(value))
    return value

def _game(value):
    if not re.fullmatch(r'[a-z][a-z0-9_-]*', value):
        raise HistoricalOracleError('Expected a game directory name, without path separators')
    return value

def _git(*args):
    environment = dict(os.environ, GIT_NO_LAZY_FETCH='1', GIT_NO_REPLACE_OBJECTS='1',
                       GIT_OPTIONAL_LOCKS='0')
    try:
        result = subprocess.run(['git', *args], cwd=ROOT, env=environment,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError as error:
        raise HistoricalOracleError('Git is required to read the pinned original objects') from error
    if result.returncode:
        raise HistoricalOracleError(
            'Pinned historical oracle objects are unavailable: ' + REFERENCE_COMMIT + '. '
            'A sparse checkout needs no vendor files. Shallow or partial clones must '
            'obtain this commit and its source/asset objects from their configured '
            'remote explicitly (unshallow first if necessary). No automatic fetch '
            'or HEAD fallback is allowed. Requested Git operation: ' + ' '.join(args) + '. '
            + TOOLCHAIN_GUIDANCE)
    return result.stdout

@lru_cache(maxsize=1)
def reference_identity():
    commit = _git('rev-parse', '--verify', REFERENCE_COMMIT + '^{commit}').decode().strip()
    tree = _git('rev-parse', '--verify', REFERENCE_COMMIT + ':' + SOURCE_GIT_PATH).decode().strip()
    if commit != REFERENCE_COMMIT or tree != SOURCE_TREE:
        raise HistoricalOracleError('Pinned reference commit/source-tree identity differs')
    return dict(reference_commit=commit, source_git_path=SOURCE_GIT_PATH, source_tree=tree)

@lru_cache(maxsize=None)
def source_bytes(relative):
    relative = _relative(relative)
    reference_identity()
    return _git('show', REFERENCE_COMMIT + ':' + SOURCE_GIT_PATH + '/' + relative)

def source_text(relative):
    return source_bytes(relative).decode('utf-8')

def source_archive(relative=''):
    """Archive only a subtree of the validated original source tree, offline."""
    reference_identity()
    path = SOURCE_GIT_PATH + ('/' + _relative(relative) if relative else '')
    return _git('archive', REFERENCE_COMMIT + ':' + path)

def _build_output(output):
    output = Path(output).absolute()
    build = ROOT / 'build'
    if build.is_symlink():
        raise HistoricalOracleError('Historical oracle build root cannot be a symlink')
    if not output.resolve().is_relative_to(build.resolve()):
        raise HistoricalOracleError('Historical oracle output must remain inside repository build/')
    current = output
    while current != build and current != current.parent:
        if current.is_symlink():
            raise HistoricalOracleError('Historical oracle output cannot use symlink directories')
        current = current.parent
    return output

def _validate_cache(folder, expected, manifest):
    if folder.is_symlink() or not folder.is_dir():
        raise HistoricalOracleError('Historical cache is not a regular directory: ' + str(folder))
    actual = {}
    directories = {parent.as_posix() for name in expected
                   for parent in PurePosixPath(name).parents if str(parent) != '.'}
    for path in folder.rglob('*'):
        if path.is_symlink():
            raise HistoricalOracleError('Historical cache contains a symlink: ' + str(path))
        relative = path.relative_to(folder).as_posix()
        if path.is_file():
            if relative != '.historical-oracle.json':
                actual[relative] = _sha(path.read_bytes())
        elif not path.is_dir() or relative not in directories:
            raise HistoricalOracleError('Historical cache contains an unexpected entry: ' + str(path))
    try:
        saved = json.loads((folder / '.historical-oracle.json').read_text())
    except (OSError, ValueError) as error:
        raise HistoricalOracleError('Missing/corrupt historical cache manifest; remove this cache explicitly') from error
    if actual != expected or saved != manifest:
        raise HistoricalOracleError('Stale/corrupt historical cache; remove this cache explicitly: ' + str(folder))

def stage_source_files(output, relatives):
    """Copy selected complete original blobs, retaining their relative layout."""
    output = _build_output(output)
    relatives = tuple(dict.fromkeys(_relative(value) for value in relatives))
    payload = {name: source_bytes(name) for name in relatives}
    hashes = {name: _sha(raw) for name, raw in payload.items()}
    report = dict(**reference_identity(), original_source_sha256=hashes)
    folder = output / 'historical-oracle-source'
    if folder.exists() or folder.is_symlink():
        _validate_cache(folder, hashes, report)
        return folder
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='historical-source-', dir=output) as temporary:
        candidate = Path(temporary) / 'source'
        candidate.mkdir()
        for name, raw in payload.items():
            path = candidate / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        (candidate / '.historical-oracle.json').write_text(json.dumps(report, indent=2) + '\n')
        _validate_cache(candidate, hashes, report)
        candidate.rename(folder)
    return folder

def stage_path_probe(template, output, paths):
    """Rewrite only exact checked #[path] spans in an ignored template copy.

    paths maps the original path-string value to its pinned source-relative path.
    Every other template byte and every original implementation byte is retained.
    """
    output = _build_output(output)
    paths = dict(paths)
    source = stage_source_files(output, paths.values())
    raw = Path(template).read_bytes()
    generated = raw
    spans = []
    for old, relative in paths.items():
        marker = ('#[path = "' + old + '"]').encode()
        if raw.count(marker) != 1:
            raise HistoricalOracleError('Expected one exact original #[path] span: ' + old)
        replacement_path = 'historical-oracle-source/' + _relative(relative)
        replacement = ('#[path = "' + replacement_path + '"]').encode()
        generated = generated.replace(marker, replacement)
        spans.append(dict(begin_byte=raw.index(marker), end_byte=raw.index(marker) + len(marker),
            original_span_sha256=_sha(marker), generated_span_sha256=_sha(replacement),
            original_path=old, staged_path=replacement_path, original_source_sha256=_sha(source_bytes(relative))))
    restored = generated
    for old, relative in paths.items():
        replacement_path = 'historical-oracle-source/' + _relative(relative)
        restored = restored.replace(('#[path = "' + replacement_path + '"]').encode(),
                                    ('#[path = "' + old + '"]').encode())
    if restored != raw:
        raise HistoricalOracleError('Probe adaptation changed bytes outside checked #[path] spans')
    destination = output / Path(template).name
    provenance = output / (Path(template).stem + '-historical-provenance.json')
    if destination.is_symlink() or provenance.is_symlink():
        raise HistoricalOracleError('Historical probe/provenance cannot be a symlink')
    destination.write_bytes(generated)
    report = dict(**reference_identity(), template_sha256=_sha(raw), generated_probe_sha256=_sha(generated),
                  checked_path_spans=spans, non_path_template_bytes_preserved=True,
                  source_manifest_sha256=_sha((source / '.historical-oracle.json').read_bytes()))
    provenance.write_text(json.dumps(report, indent=2) + '\n')
    return destination

def _restore_zip(raw, manifest, output, expected_sha, provenance):
    if _sha(raw) != expected_sha or manifest.get('archive_sha256') != expected_sha:
        raise HistoricalOracleError('Historical asset ZIP SHA256 differs')
    hashes = manifest.get('sha256')
    if not isinstance(hashes, dict) or not hashes:
        raise HistoricalOracleError('Historical asset manifest has no file hashes')
    hashes = {_relative(name): value for name, value in hashes.items()}
    if '.historical-oracle.json' in hashes:
        raise HistoricalOracleError('Historical asset member collides with the cache manifest')
    if any(not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value)
           for value in hashes.values()):
        raise HistoricalOracleError('Historical asset manifest contains invalid SHA256 values')
    payload = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for entry in archive.infolist():
            name = _relative(entry.filename.rstrip('/'))
            mode = (entry.external_attr >> 16) & 0xffff
            if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                raise HistoricalOracleError('Historical ZIP contains a nonregular member: ' + name)
            if entry.is_dir():
                continue
            if name in payload or name not in hashes:
                raise HistoricalOracleError('Duplicate/unexpected historical ZIP member: ' + name)
            value = archive.read(entry)
            if _sha(value) != hashes[name]:
                raise HistoricalOracleError('Historical ZIP member SHA256 differs: ' + name)
            payload[name] = value
    if set(payload) != set(hashes):
        raise HistoricalOracleError('Historical ZIP/manifest member sets differ')
    report = dict(provenance, archive_sha256=expected_sha, original_asset_sha256=hashes,
                  files=len(payload), uncompressed_bytes=sum(map(len, payload.values())))
    if output.exists() or output.is_symlink():
        _validate_cache(output, hashes, report)
        return report
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='historical-assets-', dir=output.parent) as temporary:
        candidate = Path(temporary) / 'assets'
        candidate.mkdir()
        for name, value in payload.items():
            path = candidate / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(value)
        (candidate / '.historical-oracle.json').write_text(json.dumps(report, indent=2) + '\n')
        _validate_cache(candidate, hashes, report)
        candidate.rename(output)
    return report

def asset_identity(game):
    """Validate the pinned asset objects without reading/extracting their payload."""
    game = _game(game)
    identity = reference_identity()
    base = 'games/' + game + '/assets/skate/'
    zip_path, manifest_path = base + 'runtime.zip', base + 'runtime.json'
    zip_blob = _git('rev-parse', '--verify', REFERENCE_COMMIT + ':' + zip_path).decode().strip()
    manifest_blob = _git('rev-parse', '--verify', REFERENCE_COMMIT + ':' + manifest_path).decode().strip()
    if zip_blob != ASSET_ZIP_BLOB or manifest_blob != ASSET_MANIFEST_BLOB:
        raise HistoricalOracleError('Requested game does not match the pinned historical asset objects')
    return dict(**identity, asset_git_path=zip_path, asset_blob=zip_blob,
                asset_manifest_git_path=manifest_path, asset_manifest_blob=manifest_blob)

def restore_original_assets(output, game):
    """Explicit historical assets for original test/export tools, never shipping."""
    output = _build_output(output)
    game = _game(game)
    if not output.resolve().is_relative_to((ROOT / 'build' / game).resolve()):
        raise HistoricalOracleError('Asset output must remain in build/<requested game>/')
    identity = asset_identity(game)
    zip_path, manifest_path = identity['asset_git_path'], identity['asset_manifest_git_path']
    raw = _git('show', REFERENCE_COMMIT + ':' + zip_path)
    manifest_raw = _git('show', REFERENCE_COMMIT + ':' + manifest_path)
    provenance = dict(**identity, asset_manifest_sha256=_sha(manifest_raw))
    return _restore_zip(raw, json.loads(manifest_raw), output, ASSET_ZIP_SHA256, provenance)

def run_cli(main_function):
    """Keep successful probes unchanged; explain unavailable original prerequisites."""
    # Existing pinned-Git staging helpers called by these checkers also stay
    # offline in partial clones; no implicit promisor-remote object retrieval.
    flags = dict(GIT_NO_LAZY_FETCH='1', GIT_NO_REPLACE_OBJECTS='1', GIT_OPTIONAL_LOCKS='0')
    previous = {name: os.environ.get(name) for name in flags}
    os.environ.update(flags)
    try:
        main_function()
    except HistoricalOracleError as error:
        print('Historical oracle: ' + str(error), file=sys.stderr)
        raise SystemExit(2) from error
    except FileNotFoundError as error:
        if Path(error.filename or '').name in ('rustc', 'cargo'):
            print(TOOLCHAIN_GUIDANCE, file=sys.stderr)
        raise
    except subprocess.CalledProcessError as error:
        command = error.cmd
        executable = command[0] if isinstance(command, (tuple, list)) and command else ''
        if Path(str(executable)).name in ('rustc', 'cargo'):
            print(TOOLCHAIN_GUIDANCE, file=sys.stderr)
        elif Path(str(executable)).name == 'git':
            print('Pinned oracle Git objects are required. Obtain missing shallow/partial '
                  'history explicitly; no automatic fetch or HEAD fallback is allowed.', file=sys.stderr)
        raise
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

def _self_test(output):
    import unittest
    from unittest import mock
    class Tests(unittest.TestCase):
        def setUp(self):
            self.temporary = tempfile.TemporaryDirectory(dir=output)
            self.addCleanup(self.temporary.cleanup)
            self.folder = Path(self.temporary.name) / 'assets'
        def archive(self, members):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w') as archive:
                for name, value in members:
                    archive.writestr(name, value)
            return stream.getvalue()
        def restore(self, raw, hashes, expected=None):
            sha = expected or _sha(raw)
            return _restore_zip(raw, dict(archive_sha256=sha, sha256=hashes), self.folder, sha, {'fixture': 1})
        def test_exact_restore_and_cache_reuse(self):
            raw = self.archive([('private/value', b'complete original bytes')])
            hashes = {'private/value': _sha(b'complete original bytes')}
            first = self.restore(raw, hashes)
            self.assertEqual(first, self.restore(raw, hashes))
            self.assertEqual((self.folder / 'private/value').read_bytes(), b'complete original bytes')
        def test_archive_integrity(self):
            raw = self.archive([('private/value', b'a')])
            with self.assertRaisesRegex(HistoricalOracleError, 'ZIP SHA256'):
                self.restore(raw, {'private/value': _sha(b'a')}, '0' * 64)
            self.assertFalse(self.folder.exists())
        def test_member_integrity(self):
            raw = self.archive([('private/value', b'a')])
            with self.assertRaisesRegex(HistoricalOracleError, 'member SHA256'):
                self.restore(raw, {'private/value': _sha(b'b')})
            self.assertFalse(self.folder.exists())
        def test_path_escape(self):
            for name in ('../outside', '/absolute', 'a/../outside', 'a\\outside', 'a//outside', 'C:outside'):
                raw = self.archive([(name, b'a')])
                with self.assertRaisesRegex(HistoricalOracleError, 'Unsafe historical'):
                    self.restore(raw, {name: _sha(b'a')})
                self.assertFalse(self.folder.exists())
        def test_duplicate_member(self):
            raw = self.archive([('private/value', b'a'), ('private/value', b'a')])
            with self.assertRaisesRegex(HistoricalOracleError, 'Duplicate'):
                self.restore(raw, {'private/value': _sha(b'a')})
        def test_symlink_member(self):
            info = zipfile.ZipInfo('private/value')
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            raw = self.archive([(info, b'../outside')])
            with self.assertRaisesRegex(HistoricalOracleError, 'nonregular'):
                self.restore(raw, {'private/value': _sha(b'../outside')})
        def test_corrupt_cache_is_retained_and_rejected(self):
            raw = self.archive([('private/value', b'a')])
            hashes = {'private/value': _sha(b'a')}
            self.restore(raw, hashes)
            (self.folder / 'private/value').write_bytes(b'corrupt')
            with self.assertRaisesRegex(HistoricalOracleError, 'Stale/corrupt'):
                self.restore(raw, hashes)
            self.assertEqual((self.folder / 'private/value').read_bytes(), b'corrupt')
        def test_extra_cache_file_is_rejected(self):
            raw = self.archive([('private/value', b'a')])
            hashes = {'private/value': _sha(b'a')}
            self.restore(raw, hashes)
            (self.folder / 'extra').write_bytes(b'not original')
            with self.assertRaisesRegex(HistoricalOracleError, 'Stale/corrupt'):
                self.restore(raw, hashes)
        def test_extra_cache_directory_is_rejected(self):
            raw = self.archive([('private/value', b'a')])
            hashes = {'private/value': _sha(b'a')}
            self.restore(raw, hashes)
            (self.folder / 'extra').mkdir()
            with self.assertRaisesRegex(HistoricalOracleError, 'unexpected entry'):
                self.restore(raw, hashes)
        def test_cache_symlink_is_rejected(self):
            raw = self.archive([('private/value', b'a')])
            hashes = {'private/value': _sha(b'a')}
            self.restore(raw, hashes)
            (self.folder / 'private/value').unlink()
            (self.folder / 'private/value').symlink_to('/outside')
            with self.assertRaisesRegex(HistoricalOracleError, 'symlink'):
                self.restore(raw, hashes)
        def test_source_path_and_cache_integrity(self):
            for path in ('../outside', '/absolute', 'a/../outside', 'a\\outside', 'a//outside', 'C:outside'):
                with self.assertRaises(HistoricalOracleError):
                    source_bytes(path)
            staging = Path(self.temporary.name) / 'source-stage'
            identity = dict(reference_commit=REFERENCE_COMMIT, source_tree=SOURCE_TREE)
            with mock.patch(__name__ + '.source_bytes', return_value=b'complete original body'), \
                 mock.patch(__name__ + '.reference_identity', return_value=identity):
                folder = stage_source_files(staging, ['crates/core/source.rs'])
                self.assertEqual(folder, stage_source_files(staging, ['crates/core/source.rs']))
                (folder / 'crates/core/source.rs').write_bytes(b'corrupt')
                with self.assertRaisesRegex(HistoricalOracleError, 'Stale/corrupt'):
                    stage_source_files(staging, ['crates/core/source.rs'])
        def test_build_path_escape(self):
            with self.assertRaisesRegex(HistoricalOracleError, 'inside repository build'):
                _build_output(ROOT / 'outside')
            escaped = Path(self.temporary.name) / 'escape'
            escaped.symlink_to(ROOT)
            with self.assertRaises(HistoricalOracleError):
                _build_output(escaped / 'value')
        def test_missing_history_never_fetches(self):
            result = subprocess.CompletedProcess([], 128, stdout=b'', stderr=b'missing object')
            with mock.patch.object(subprocess, 'run', return_value=result) as run:
                with self.assertRaisesRegex(HistoricalOracleError, 'No automatic fetch'):
                    _git('show', REFERENCE_COMMIT + ':missing')
                self.assertEqual(run.call_count, 1)
                self.assertEqual(run.call_args.kwargs['env']['GIT_NO_LAZY_FETCH'], '1')
                self.assertNotIn('fetch', run.call_args.args[0])
        def test_game_path_validation(self):
            for value in ('../other', '/absolute', '', 'a/b', 'a\\b'):
                with self.assertRaises(HistoricalOracleError):
                    _game(value)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    if not result.wasSuccessful():
        raise HistoricalOracleError('Historical oracle self-test failed')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--self-test', action='store_true', help='Only small synthetic archive/cache tests')
    parser.add_argument('--check-history', action='store_true', help='Validate pinned Git objects without extraction')
    args = parser.parse_args()
    _game(args.game)
    output = _build_output(args.output)
    if args.self_test:
        output.mkdir(parents=True, exist_ok=True)
        _self_test(output)
    elif args.check_history:
        print(json.dumps(dict(**asset_identity(args.game), guidance=TOOLCHAIN_GUIDANCE), indent=2))
    else:
        print(json.dumps(restore_original_assets(output, args.game), indent=2))

if __name__ == '__main__':
    run_cli(main)
