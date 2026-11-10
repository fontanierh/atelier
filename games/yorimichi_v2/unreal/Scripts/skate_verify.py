"""The rule that accepts a skate RuntimeData import after the Skate plugin's Verify passed (USkateDataLibrary::Verify,
SkateMotionData.cpp:473): its report must agree with the receipt tools/import/skate_runtime.py wrote for the assembled
package. Pure data, no editor: unreal/Scripts/import_asset.py calls it, and the tests use it.
"""


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
