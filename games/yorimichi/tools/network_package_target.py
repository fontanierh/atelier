"""Verified, independently extracted Mac target for the native session runner.

Only chooses launch files and records provenance. Launch ownership, aggregate
memory limits and teardown remain with review_network_session's existing guard.
"""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import time


def package_layout(app):
    app = Path(app).resolve(strict=True)
    if not app.is_dir() or app.suffix != '.app':
        raise RuntimeError('Expected an extracted macOS app directory')
    plist = app / 'Contents/Info.plist'
    if not plist.is_file() or plist.is_symlink():
        raise RuntimeError('Expected a regular internal package Info.plist')
    metadata = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
    name, bundle = metadata.get('CFBundleExecutable'), metadata.get('CFBundleIdentifier')
    if not isinstance(name, str) or not name or Path(name).name != name or name in ('.', '..'):
        raise RuntimeError('Invalid packaged executable name')
    if not isinstance(bundle, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,199}', bundle):
        raise RuntimeError('Invalid package bundle identifier')
    executable = app / 'Contents/MacOS' / name
    if executable.is_symlink() or not executable.is_file() or not os.access(executable, os.X_OK) or app not in executable.resolve().parents:
        raise RuntimeError('Packaged executable is missing, external or not executable')
    roots = list(app.glob('Contents/UE/*/Content/Data'))
    if len(roots) != 1 or not roots[0].is_dir() or roots[0].is_symlink() or app not in roots[0].resolve().parents:
        raise RuntimeError('Expected one internal packaged gameplay-data directory')
    container = Path.home() / 'Library/Containers' / bundle / 'Data'
    return app, executable, roots[0], container


def package_fingerprint(app, expected_identity):
    """Hash the actual app, including cooked containers, not just its claimed code."""
    app, executable, data, container = package_layout(app)
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True, timeout=120)
    raw = subprocess.check_output(['codesign', '-d', '--entitlements', '-', '--xml', str(app)], timeout=30)
    entitlements = plistlib.loads(raw) if raw.strip() else {}
    from verify_network_package import check_data
    prerequisites = check_data(data, entitlements, expected_identity)
    manifest = json.loads((data / 'Network/session.json').read_text())
    identity = f'{manifest.get("protocol")}:{manifest.get("code")}:{manifest.get("signature")}'
    if identity != expected_identity:
        raise RuntimeError('Package identity differs from the accepted native build')
    began = spoken = time.monotonic()
    records, digest, files, total = [], hashlib.sha256(), 0, 0
    executable_sha = None
    for path in sorted(app.rglob('*')):
        relative = path.relative_to(app).as_posix()
        if path.is_symlink():
            if not path.exists() or app not in path.resolve().parents:
                raise RuntimeError('External or broken app symlink: ' + relative)
            record = ('link', relative, os.readlink(path))
        elif path.is_file():
            sha = hashlib.sha256()
            with path.open('rb') as stream:
                while block := stream.read(1024 * 1024):
                    sha.update(block); total += len(block)
                    now = time.monotonic()
                    if now - began > 180:
                        raise RuntimeError('Packaged fingerprint exceeded three minutes')
                    if now - spoken >= 20:
                        print(f'package fingerprint: {files} files, {total / 1024**3:.2f} GiB read', flush=True)
                        spoken = now
            record = ('file', relative, path.stat().st_mode & 0o777, path.stat().st_size, sha.hexdigest())
            files += 1
            if path == executable:
                executable_sha = sha.hexdigest()
        else:
            continue
        digest.update(json.dumps(record, ensure_ascii=True, separators=(',', ':')).encode() + b'\n')
        if record[0] == 'file' and relative.endswith(('.pak', '.utoc', '.ucas')):
            records.append(record)
    if not records or not executable_sha:
        raise RuntimeError('Package lacks a cooked container or executable fingerprint')
    return dict(kind='packaged-mac', app_sha256=digest.hexdigest(), executable_sha256=executable_sha,
                cooked_containers=records, files=files, bytes=total, identity=identity,
                executable=str(executable), writable_container=str(container), prerequisites=prerequisites)


def runtime_directory(app, name):
    """A new evidence folder inside the signed app's own sandbox container."""
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', name):
        raise RuntimeError('Invalid package run name')
    _, _, _, container = package_layout(app)
    # Reject redirection of any existing parent, including an old proof directory.
    if container.resolve() != container.absolute():
        raise RuntimeError('Package container path is redirected')
    parent = container / 'Library/Application Support/Yorimichi/NetworkQA'
    if parent.resolve() != parent.absolute():
        raise RuntimeError('Package QA parent is redirected')
    parent.mkdir(parents=True, exist_ok=True)
    folder = parent / name
    folder.mkdir()  # Fail on collision: no stale receipt can be reused.
    return folder


def packaged_command(app, destination, role, folder, options):
    _, executable, _, container = package_layout(app)
    folder = Path(folder).resolve(strict=True)
    if container.resolve() not in folder.parents:
        raise RuntimeError('Packaged evidence must remain inside its own sandbox')
    if role not in ('server', 'client', 'plain'):
        raise RuntimeError('Invalid packaged role')
    user = folder / (role + '-user')
    user.mkdir(exist_ok=True)
    if user.resolve() != user.absolute():
        raise RuntimeError('Packaged user directory is redirected')
    return [str(executable), destination, *options,
            '-UserDir=' + str(user) + '/', '-abslog=' + str(folder / (role + '-engine.log'))]


def runtime_identity_checks(folder, expected_identity, source_code):
    checks = {}
    parts = expected_identity.split(':')
    code = parts[1] if len(parts) == 3 else ''
    valid = (len(parts) == 3 and parts[0] == '1' and bool(re.fullmatch('[0-9a-f]{40}', code)) and
             bool(re.fullmatch('[0-9a-f]{40}', parts[2])) and code == source_code)
    build_target = 'Mac/Game/Development'
    digest = hashlib.sha256((code + '\n' + build_target + '\n').encode()).hexdigest()
    for role in ('server', 'client'):
        try:
            receipt = json.loads((Path(folder) / (role + '-connected.json')).read_text())
        except (OSError, ValueError):
            receipt = {}
        checks[role + '_packaged_identity'] = bool(valid and receipt.get('identity') == expected_identity and
            receipt.get('compiled_code_digest') == code and
            receipt.get('compiled_target') == build_target and receipt.get('compiled_input_digest') == digest)
    return checks


def verify_cook_source(repo, receipt):
    """Bind compiled content to a clean commit, without embedding Git in C++."""
    import importlib.util
    repo = Path(repo).resolve()
    spec = importlib.util.spec_from_file_location('package_code_identity', repo / 'games/yorimichi/network_identity.py')
    identity = importlib.util.module_from_spec(spec); spec.loader.exec_module(identity)
    code_files, code_identity = identity.code_files, identity.code_identity
    CODE_SUFFIXES, IGNORED = identity.CODE_SUFFIXES, identity.IGNORED
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True, timeout=5).strip()
    status = subprocess.check_output(['git', 'status', '--porcelain'], cwd=repo, text=True, timeout=5)
    if receipt.get('source_dirty') is not False or receipt.get('revision') != head or status.strip():
        raise RuntimeError('Package proof requires the clean exact cook revision')
    actual = {p.relative_to(repo).as_posix() for p in code_files(repo)}
    roots = ['games/yorimichi/unreal/Source', 'games/yorimichi/unreal/Config', 'platform/engine/Plugins']
    tracked = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', '-z', 'HEAD', '--',
        *roots, 'games/yorimichi/unreal'], cwd=repo, timeout=5).decode().split('\0')
    expected = {name for name in tracked if name and Path(name).suffix in CODE_SUFFIXES and
                not (set(Path(name).parts) & IGNORED) and
                (any(name.startswith(root + '/') for root in roots) or
                 (Path(name).parent.as_posix() == 'games/yorimichi/unreal' and name.endswith('.uproject')))}
    if actual != expected:
        raise RuntimeError('Compiled source inventory differs from its commit, including ignored files')
    return dict(head_sha=head, dirty=False, code_digest=code_identity(repo), source_files=len(actual))


def plain_launch_checks(folder, text, code, source_code):
    diagnostics = re.findall(r'NETWORK diagnostics session=(\d+) gameplay=(\d+) combat=(\d+) enemy=(\d+) vehicles=(\d+) reaction=(\d+) code=([a-z0-9]+) target=(\S+) input=([a-z0-9]+)', text)
    expected_input = hashlib.sha256((source_code + '\nMac/Game/Development\n').encode()).hexdigest()
    return dict(plain_exit=code == 0, plain_world_ready='Character ready:' in text,
                plain_normal_deadline='FEngineLoop::Tick.Benchmarking' in text,
                plain_no_network_diagnostics=bool(diagnostics) and all(
                    row[:6] == ('0',)*6 and row[6:] == (source_code, 'Mac/Game/Development', expected_input)
                    for row in diagnostics),
                plain_no_qa_receipts=not any(any(Path(folder).rglob(pattern)) for pattern in
                    ('*-connected.json', '*-world.json', '*-gameplay.json', '*-complete.json', '*-failed.json', 'combat-*.json', 'enemy-*.json', 'vehicle-*.json', 'reaction-*.json')))


def cook_binding_checks(cook, binary, source, expected_identity):
    """Cook provenance covers the actual containers, not a copied revision field."""
    files = cook.get('files', {})
    wanted = {name: (entry.get('bytes'), entry.get('sha256')) for name, entry in files.items()
              if name.endswith(('.pak', '.utoc', '.ucas')) and isinstance(entry, dict)}
    rows = binary.get('cooked_containers', [])
    actual = {row[1]: (row[3], row[4]) for row in rows if len(row) == 5 and row[0] == 'file'}
    parts = expected_identity.split(':')
    return dict(cook_containers_match=bool(wanted) and len(actual) == len(rows) and actual == wanted,
                package_source_matches_manifest=len(parts) == 3 and parts[0] == '1' and
                    bool(re.fullmatch('[0-9a-f]{40}', parts[1])) and bool(re.fullmatch('[0-9a-f]{40}', parts[2])) and
                    parts[1] == source.get('code_digest') and binary.get('identity') == expected_identity)
