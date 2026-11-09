"""Acceptance for an extracted V2 package: automated checks, a manual evidence ledger, and one verdict.

The package is judged where it runs, outside the repository (P7 step 2). This tool never cooks, builds, launches the
game or touches a claim, board or release. It checks what a file can show (identity, signatures, bundled dependencies,
excluded content names, runtime-data bytes) and keeps a ledger of what a person saw in the running game, bound to the
package's fingerprint, so an evidence line recorded for one package cannot pass another.

    uv run python games/yorimichi_v2/tools/package/acceptance.py automated --app APP
    uv run python games/yorimichi_v2/tools/package/acceptance.py record --app APP --evidence EV first_launch pass --note "..."
    uv run python games/yorimichi_v2/tools/package/acceptance.py verify --app APP --evidence EV [--multiplayer] [--report OUT]

`record` refuses an evidence file bound to another package unless `--reset` starts it again. `verify` exits 1 unless every
automated check and every required manual item passes for this exact package.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cook_config  # noqa: E402

GAME = cook_config.GAME
# What a person must see in the running package (P7 step 2). The ledger accepts only these names.
MANUAL = ('first_launch', 'input', 'map_travel', 'gameplay', 'sound', 'settings_persistence', 'save_persistence',
          'shutdown')
MULTIPLAYER = ('two_machine_multiplayer',)
# Paths outside the app that a bundled binary may not reference: a build folder or a developer's home leaks in.
FOREIGN_LINK_MARKERS = ('/Users/', '/Volumes/', '/private/', 'Intermediate', 'Saved/', 'Binaries/')
SYSTEM_PREFIXES = ('/System/', '/usr/lib/', '/usr/libexec/')
ABSOLUTE = re.compile(r"(^|[\s'\"(\[,=:])(/[^\s'\",\])]+)")


class Check:
    def __init__(self, name, ok, detail=''):
        self.name, self.ok, self.detail = name, bool(ok), detail

    def as_dict(self):
        return {'check': self.name, 'ok': self.ok, 'detail': self.detail}


def files_under(app: Path):
    for root, dirs, files in os.walk(app, followlinks=False):
        dirs[:] = [d for d in dirs if not d.endswith('.app')]
        for name in files:
            path = Path(root) / name
            yield path


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint(app: Path) -> str:
    """One digest over what the package is: its property list, executables, libraries and paks, by relative path."""
    digest = hashlib.sha256()
    chosen = []
    for path in files_under(app):
        rel = path.relative_to(app).as_posix()
        data = '/Data/' in '/' + rel      # the staged runtime data is bound to the package too
        if rel == 'Contents/Info.plist' or rel.startswith('Contents/MacOS/') or path.suffix in {'.pak', '.dylib', '.ini'} or data:
            chosen.append((rel, path))
    for rel, path in sorted(chosen):
        digest.update(f'{rel}\0{sha256(path)}\n'.encode())
    return digest.hexdigest()


def info_plist(app: Path) -> dict:
    with (app / 'Contents/Info.plist').open('rb') as handle:
        return plistlib.load(handle)


def check_identity(app: Path) -> list[Check]:
    try:
        info = info_plist(app)
    except (OSError, ValueError) as error:
        return [Check('identity', False, f'Contents/Info.plist unreadable: {error}')]
    expected = cook_config.bundle_identifier(GAME)
    out = [Check('identity.bundle_id', info.get('CFBundleIdentifier') == expected,
                 f"{info.get('CFBundleIdentifier')} (expected {expected})")]
    executable = info.get('CFBundleExecutable', '')
    out.append(Check('identity.executable', bool(executable) and (app / 'Contents/MacOS' / executable).is_file(),
                     executable or 'no CFBundleExecutable'))
    return out


def check_signatures(app: Path) -> list[Check]:
    try:
        result = subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], capture_output=True,
                                text=True, timeout=600)
        return [Check('signatures', result.returncode == 0, (result.stderr or 'valid').strip()[:300])]
    except (OSError, subprocess.TimeoutExpired) as error:
        return [Check('signatures', False, f'codesign unavailable: {error}')]


AUDIO_LOOKUP = 'com.apple.cmio.registerassistantservice.system-extensions'
MACH_LOOKUP = 'com.apple.security.temporary-exception.mach-lookup.global-name'


def check_entitlements(app: Path) -> list[Check]:
    """A sandboxed app may look up the CoreAudio service: without it audio start-up blocks forever (first launch)."""
    try:
        result = subprocess.run(['codesign', '-d', '--entitlements', '-', '--xml', str(app)], capture_output=True,
                                timeout=120)
        entitlements = plistlib.loads(result.stdout) if result.stdout.strip() else {}
    except (OSError, subprocess.TimeoutExpired, plistlib.InvalidFileException, ValueError) as error:
        return [Check('entitlements.audio', False, f'entitlements unreadable: {error}')]
    if not entitlements.get('com.apple.security.app-sandbox'):
        return [Check('entitlements.audio', True, 'not sandboxed')]
    ok = AUDIO_LOOKUP in (entitlements.get(MACH_LOOKUP) or [])
    return [Check('entitlements.audio', ok, 'sandboxed; CoreAudio lookup ' + ('allowed' if ok else f'missing ({AUDIO_LOOKUP})'))]


def check_bundled_deps(app: Path) -> list[Check]:
    """Every executable and library resolves its non-system dependencies inside the package, not in a build tree."""
    binaries = [p for p in files_under(app) if p.suffix == '.dylib' or (p.parent.name == 'MacOS' and p.is_file())]
    if not binaries:
        return [Check('bundled_deps', False, 'no executable or library found in the package')]
    bad = []
    for binary in binaries:
        try:
            result = subprocess.run(['otool', '-L', str(binary)], capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as error:
            return [Check('bundled_deps', False, f'otool unavailable: {error}')]
        for line in result.stdout.splitlines():
            if not line.startswith(('\t', ' ')):   # a header: the binary itself, once per architecture of a universal one
                continue
            target = line.strip().split(' (')[0]
            if target.startswith(SYSTEM_PREFIXES) or target.startswith('@'):
                continue
            if target.startswith('/') and any(marker in target for marker in FOREIGN_LINK_MARKERS):
                bad.append(f'{binary.name} -> {target}')
    return [Check('bundled_deps', not bad, '; '.join(bad[:5]) or f'{len(binaries)} binaries resolve inside the package')]


def check_excluded(app: Path) -> list[Check]:
    hits = sorted(p.relative_to(app).as_posix() for p in files_under(app)
                  if any(word in p.relative_to(app).as_posix().lower() for word in cook_config.EXCLUDED))
    return [Check('excluded_absent', not hits, '; '.join(hits[:5]) or 'no X01/X02 content names')]


def check_runtime_data(app: Path, game: Path | None = None) -> list[Check]:
    """Each committed runtime-data file is in the package with the committed bytes (unreal/Content/Data)."""
    lock = json.loads(((game or GAME) / 'runtime-data.lock.json').read_text())['files']
    by_name: dict[str, list[Path]] = {}
    for path in files_under(app):
        by_name.setdefault(path.name, []).append(path)
    missing, changed = [], []
    for rel, want in sorted(lock.items()):
        # rel is 'Data/<...>' relative to unreal/Content; the staged copy keeps that suffix somewhere in the package.
        found = [p for p in by_name.get(Path(rel).name, []) if p.relative_to(app).as_posix().endswith(rel)]
        if not found:
            missing.append(rel)
        elif not any(sha256(p) == want for p in found):
            changed.append(rel)
    detail = f'{len(lock)} files; missing {missing[:4]}, changed {changed[:4]}'
    return [Check('runtime_data', not missing and not changed, detail)]


def portable(text: str, app: Path) -> str:
    """Check details as shareable evidence records them (CONTRACTS yorimichi-v2-portable-records): the bundle by its name,
    never the folder it was extracted to, and any other absolute path (a foreign dependency's build folder, a home
    path) by its file name only."""
    text = text.replace(str(app.resolve()), app.name).replace(str(app), app.name)
    return ABSOLUTE.sub(lambda m: m.group(1) + Path(m.group(2)).name, text)


def automated(app: Path) -> list[Check]:
    if not (app / 'Contents/Info.plist').is_file():
        return [Check('app', False, f'{app.name} is not an app bundle')]
    out = [Check('app', True, app.name)]
    out += check_identity(app)
    out += check_signatures(app)
    out += check_entitlements(app)
    out += check_bundled_deps(app)
    out += check_excluded(app)
    out += check_runtime_data(app)
    for check in out:
        check.detail = portable(str(check.detail), app)
    return out


def git_identity() -> dict:
    def git(*args):
        return subprocess.run(['git', *args], cwd=GAME, capture_output=True, text=True).stdout.strip()
    return {'commit': git('rev-parse', 'HEAD'), 'dirty': bool(git('status', '--porcelain', '--', '.'))}


def load_ledger(path: Path) -> dict:
    return json.loads(path.read_text()) if path.is_file() else {'package': None, 'items': {}}


def write_ledger(path: Path, ledger: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + '\n')


def record(app: Path, evidence: Path, item: str, status: str, note: str, reset: bool) -> str:
    if item not in MANUAL + MULTIPLAYER:
        raise SystemExit(f'unknown item {item!r}; the items are {", ".join(MANUAL + MULTIPLAYER)}')
    if status not in ('pass', 'fail'):
        raise SystemExit('status is pass or fail')
    current = fingerprint(app)
    ledger = load_ledger(evidence)
    if ledger.get('package') not in (None, current) and not reset:
        raise SystemExit(f'{evidence} is bound to another package ({ledger["package"][:12]}); use --reset to start over')
    if ledger.get('package') != current:
        ledger = {'package': current, 'items': {}}
    ledger['items'][item] = {'status': status, 'note': portable(note, app)}
    write_ledger(evidence, ledger)
    return f'{item}: {status} recorded for package {current[:12]}'


def verify(app: Path, evidence: Path, multiplayer: bool) -> dict:
    checks = automated(app)
    current = fingerprint(app) if app.is_dir() else None
    ledger = load_ledger(evidence)
    required = MANUAL + (MULTIPLAYER if multiplayer else ())
    for item in required:
        entry = ledger['items'].get(item)
        if ledger.get('package') != current:
            ok, detail = False, 'no evidence for this package'
        elif entry is None:
            ok, detail = False, 'not recorded'
        else:
            ok, detail = entry['status'] == 'pass', portable(f"{entry['status']}: {entry['note']}", app)
        checks.append(Check(f'manual.{item}', ok, detail))
    failed = [c.name for c in checks if not c.ok]
    return {'verdict': 'pass' if not failed else 'fail', 'failed': failed, 'package': current,
            'bundle_id': cook_config.bundle_identifier(GAME), 'identity': git_identity(),
            'checks': [c.as_dict() for c in checks]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = parser.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('automated')
    a.add_argument('--app', type=Path, required=True)
    r = sub.add_parser('record')
    r.add_argument('--app', type=Path, required=True)
    r.add_argument('--evidence', type=Path, required=True)
    r.add_argument('item')
    r.add_argument('status')
    r.add_argument('--note', default='')
    r.add_argument('--reset', action='store_true')
    v = sub.add_parser('verify')
    v.add_argument('--app', type=Path, required=True)
    v.add_argument('--evidence', type=Path, required=True)
    v.add_argument('--multiplayer', action='store_true')
    v.add_argument('--report', type=Path)
    args = parser.parse_args(argv)
    if args.cmd == 'automated':
        checks = automated(args.app)
        for c in checks:
            print(f"{'ok  ' if c.ok else 'FAIL'} {c.name}: {c.detail}")
        return 0 if all(c.ok for c in checks) else 1
    if args.cmd == 'record':
        print(record(args.app, args.evidence, args.item, args.status, args.note, args.reset))
        return 0
    report = verify(args.app, args.evidence, args.multiplayer)
    text = json.dumps(report, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + '\n')
    print(text)
    return 0 if report['verdict'] == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
