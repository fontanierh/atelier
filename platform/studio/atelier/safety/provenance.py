"""What was actually running when a capture was taken.

A row in the ledger is only worth as much as its provenance, so every harness records the same
identity block: the exact command, the source commit plus a hash of the uncommitted diff, the native
binary, the saved preferences, the profile the game reports *after* applying them, the hashes of the
generated assets the shot depends on, and the guard's own verdict.
"""
import hashlib, json, os, re, subprocess, time
from pathlib import Path


def git(root, *args):
    try:
        return subprocess.run(['git', *args], cwd=root, capture_output=True, text=True, check=True).stdout
    except Exception:
        return ''


def sha(path):
    path = Path(path)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def identity(root, project, command, inputs=(), extra=None, module=None):
    """`project` is the Unreal project folder; `module` its game module (defaults to the .uproject name)."""
    project = Path(project)
    if module is None:
        module = next((p.stem for p in project.glob('*.uproject')), project.name)
    diff = git(root, 'diff', 'HEAD')
    record = dict(
        command=[str(part) for part in command],
        commit=git(root, 'rev-parse', 'HEAD').strip(),
        dirty=git(root, 'status', '--porcelain'),
        dirty_sha256=hashlib.sha256(diff.encode()).hexdigest() if diff.strip() else None,
        settings=(project/'Saved/settings.txt').read_text() if (project/'Saved/settings.txt').exists() else '',
        engine_config_sha256=sha(project/'Config/DefaultEngine.ini'),
        binary_sha256=sha(project/'Binaries/Mac'/f'libUnrealEditor-{module}.dylib'),
        started=time.time(),
        asset_sha256={str(Path(p).resolve()): sha(p) for p in inputs},
    )
    record.update(extra or {})
    return record


def profile_from_log(path):
    """The `PROFILE` line the game's preferences print after applying, as a dict of effective values."""
    try:
        text = Path(path).read_text(errors='ignore')
    except OSError:
        return None
    found = None
    for match in re.finditer(r'PROFILE\s+(\{.*?\})\s*$', text, re.MULTILINE):
        try:
            found = json.loads(match.group(1))
        except ValueError:
            continue
    return found


def guard_result(folder):
    path = Path(folder)/'memory-health.json'
    if not path.exists():
        return None
    try:
        record = json.loads(path.read_text())
    except ValueError:
        return None
    return dict(state=record.get('state'), peak_gib=round((record.get('peak_bytes') or 0)/2**30, 3),
                footprint_gib=round((record.get('footprint_bytes') or 0)/2**30, 3),
                elapsed_seconds=record.get('elapsed_seconds'))


def png_size(path):
    data = Path(path).read_bytes()[:24]
    if len(data) < 24 or data[:8] != b'\x89PNG\r\n\x1a\n':
        return None
    import struct
    return struct.unpack('>II', data[16:24])
