"""The rules that accept a skate RuntimeData import: the assembled package must be the bytes its pinned manifest lists
(package_problems, before ImportRuntime and again after Verify), and the Skate plugin's Verify report
(USkateDataLibrary::Verify, SkateMotionData.cpp:473) must agree with the receipt tools/import/skate_runtime.py wrote for
that package (problems). Pure Python, no editor: unreal/Scripts/import_asset.py calls them, and the tests use them.
"""
import hashlib
import json
from pathlib import Path

MANIFEST = 'package-manifest.json'


def package_problems(folder, manifest_sha256, receipt):
    """@cc [owner:fontanierh,label:correctness] skate-runtime-package-pinned
    What refuses an assembled RuntimeData package before it is imported (and again once Verify has read it): its
    manifest must hash to the record's pinned `manifest_sha256`; the folder must hold exactly the files the manifest
    lists, plus the manifest, each with its listed size and sha256; and each of the receipt's runtime files must keep
    its size and SHA-1. Native Verify compares the saved asset with this folder, so a payload changed after assembly
    would otherwise be imported and recorded under the original pins. [] when accepted."""
    folder = Path(folder)
    raw = (folder / MANIFEST).read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest_sha256:
        return [f'the package manifest hashes to {hashlib.sha256(raw).hexdigest()}, not the pinned {manifest_sha256}']
    listed = json.loads(raw)['files']
    found = []
    present = {path.relative_to(folder).as_posix() for path in folder.rglob('*') if path.is_file()} - {MANIFEST}
    for name in sorted(present - set(listed)):
        found.append(f'{name} is in the package but not in its manifest')
    for name, want in sorted(listed.items()):
        if name not in present:
            found.append(f'{name} is in the manifest but not in the package')
            continue
        data = (folder / name).read_bytes()
        if len(data) != want['bytes'] or hashlib.sha256(data).hexdigest() != want['sha256']:
            found.append(f'{name} differs from its manifest entry')
    for name, want in sorted(receipt['runtime'].items()):
        path = folder / name
        data = path.read_bytes() if path.is_file() else b''
        if len(data) != want['bytes'] or hashlib.sha1(data).hexdigest() != want['sha1']:
            found.append(f'runtime file {name} differs from the receipt')
    return found


def problems(report, receipt, package):
    """@cc [owner:fontanierh,label:correctness] skate-runtime-verified-read-back
    What refuses a RuntimeData import after the plugin's Verify passed: its report must say the typed runtime data encodes
    to the package byte for byte with its negative and invalid-record controls run (runtime_exact,
    runtime_negative_control, runtime_invalid_record_controls 3), name this record's package, and count the receipt's
    runtime files and bytes and its clips. [] when accepted."""
    found = []
    for key, want in (('runtime_exact', True), ('runtime_negative_control', True), ('runtime_invalid_record_controls', 3),
                      ('exact', True), ('negative_control', True)):
        if report.get(key) != want:
            found.append(f'verify report {key} is {report.get(key)!r}, not {want!r}')
    asset = f'{package}.{package.rsplit("/", 1)[1]}'
    if report.get('runtime_asset') != asset:
        found.append(f'verify report names {report.get("runtime_asset")!r}, not {asset}')
    files = receipt['runtime']
    if report.get('runtime_files') != len(files):
        found.append(f'verify report has {report.get("runtime_files")} runtime files, the receipt {len(files)}')
    if report.get('runtime_bytes') != sum(f['bytes'] for f in files.values()):
        found.append(f'verify report has {report.get("runtime_bytes")} runtime bytes, the receipt '
                        f'{sum(f["bytes"] for f in files.values())}')
    if report.get('clips') != receipt['clips']:
        found.append(f'verify report has {report.get("clips")} clips, the receipt {receipt["clips"]}')
    return found
