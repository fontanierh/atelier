"""Offline multiplayer checks for an independently extracted Apple Silicon package.

Pair with verify_package.py and a native packaged host/join run. Matching loose data
and signed entitlements do not establish that the packaged executable can host.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import plistlib
import re
import subprocess
import time


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def check_data(data, entitlements, expected_identity):
    sandboxed = entitlements.get('com.apple.security.app-sandbox') is True
    if sandboxed:
        for direction in ('client', 'server'):
            require(entitlements.get('com.apple.security.network.' + direction) is True,
                    'signed sandbox lacks network ' + direction + ' entitlement')
    network = data / 'Network'
    require(network.is_dir() and not network.is_symlink() and
            {p.name for p in network.iterdir()} == {'session.json'} and
            (network / 'session.json').is_file() and not (network / 'session.json').is_symlink(),
            'Network must contain only a regular session.json')
    require(not data.is_symlink() and not any(p.is_symlink() for p in data.rglob('*')),
            'external or symlinked gameplay data')
    manifest = json.loads((network / 'session.json').read_text())
    require(isinstance(manifest, dict), 'invalid multiplayer manifest')
    require(type(manifest.get('protocol')) is int and manifest['protocol'] == 1,
            'unsupported multiplayer protocol')
    for field in ('code', 'assets', 'signature'):
        require(isinstance(manifest.get(field), str) and re.fullmatch('[0-9a-f]{40}', manifest[field]),
                'invalid multiplayer ' + field)
    entries = manifest.get('files')
    require(isinstance(entries, list) and 0 < len(entries) <= 20000, 'invalid gameplay file inventory')
    seen, records = set(), []
    began = spoken = time.monotonic()
    for entry in entries:
        require(isinstance(entry, dict), 'invalid gameplay file record')
        relative, wanted = entry.get('path'), entry.get('sha1')
        require(isinstance(relative, str) and bool(relative) and len(relative) <= 4096 and
                not any(c in relative for c in ('..', '\\', '\n', '\r', '\0')) and
                not PurePosixPath(relative).is_absolute() and
                PurePosixPath(relative).as_posix() == relative and
                not relative.startswith('Network/') and relative not in seen,
                'invalid or duplicate gameplay path')
        require(isinstance(wanted, str) and re.fullmatch('[0-9a-f]{40}', wanted), 'invalid gameplay digest')
        path = data / relative
        require(path.is_file() and not path.is_symlink() and data.resolve() in path.resolve().parents,
                'missing or external gameplay file: ' + relative)
        digest = hashlib.sha1()
        with path.open('rb') as stream:
            while block := stream.read(1024 * 1024):
                digest.update(block)
                now = time.monotonic()
                require(now - began < 300, 'gameplay inventory exceeded five minutes')
                if now - spoken >= 25:
                    print(f'network package: checked {len(seen)}/{len(entries)} files; hashing {relative}', flush=True)
                    spoken = now
            actual = digest.hexdigest()
        require(actual == wanted, 'changed gameplay file: ' + relative)
        seen.add(relative)
        records.append((relative, wanted))
        now = time.monotonic()
        require(now - began < 300, 'gameplay inventory exceeded five minutes')
        if now - spoken >= 25:
            print(f'network package: checked {len(seen)}/{len(entries)} gameplay files', flush=True)
            spoken = now
    actual_files = {p.relative_to(data).as_posix() for p in data.rglob('*') if p.is_file()
                    and p.name != '.DS_Store' and not p.is_relative_to(data / 'Network')}
    require(actual_files == seen, 'unexpected or missing gameplay files')
    digest = hashlib.sha1()
    for name, value in sorted(records):
        digest.update(f'{name}\0{value}\n'.encode('utf-8'))
    payload = f'1\n{manifest["code"]}\n{manifest["assets"]}\n{digest.hexdigest()}\n'
    require(hashlib.sha1(payload.encode('ascii')).hexdigest() == manifest['signature'],
            'inconsistent multiplayer manifest checksum')
    identity = f'1:{manifest["code"]}:{manifest["signature"]}'
    require(identity == expected_identity, 'manifest differs from the accepted native identity')
    return dict(manifest_claimed_identity=identity, manifest_checksum=manifest['signature'], protocol=1,
                manifest_claimed_code=manifest['code'], manifest_claimed_assets=manifest['assets'],
                data_files=len(seen), sandboxed=sandboxed, signed_entitlements=entitlements)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--expected-identity', required=True, help='identity from the accepted native session receipt')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args(argv)
    require(not args.report.exists(), 'choose a new report path; old evidence is never overwritten')
    app = args.app.resolve()
    roots = list(app.glob('Contents/UE/*/Content/Data'))
    require(len(roots) == 1, 'expected one packaged gameplay-data directory')
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True, timeout=120)
    raw = subprocess.check_output(['codesign', '-d', '--entitlements', '-', '--xml', str(app)], timeout=30)
    entitlements = plistlib.loads(raw) if raw.strip() else {}
    proof = check_data(roots[0], entitlements, args.expected_identity)
    proof.update(passed=True, scope='Offline signed network permissions and loose gameplay consistency only. '
                 'The manifest checksum is recomputable, not an authenticity signature. '
                 'This does not verify the binary or cooked content. Packaged host/join must report the '
                 'compiled identity, repeat the collision probes, and pass physical-machine acceptance.')
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(proof, indent=2) + '\n')
    print(f'PASS multiplayer package prerequisites: {args.report}', flush=True)


if __name__ == '__main__':
    main()
