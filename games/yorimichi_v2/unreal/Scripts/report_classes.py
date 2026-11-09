"""Report the asset-registry class of every package under some roots as JSON (read-only `editor.run`,
V2_EDITOR_READ_ONLY=1): tools/restricted/originals.py names an editor-made package by it.

V2_REPORT_ROOTS names the /Game roots ("/Game/Paul /Game/Audio"); V2_REPORT_OUT the JSON file (package -> class).
Nothing is loaded or saved.
"""
import json
import os

import unreal as U

MARKER = 'V2 CLASSES REPORTED'
registry = U.AssetRegistryHelpers.get_asset_registry()
out = {}
for root in os.environ['V2_REPORT_ROOTS'].split():
    for data in registry.get_assets_by_path(root, recursive=True):
        out[str(data.package_name)] = str(data.asset_class_path.asset_name)
with open(os.environ['V2_REPORT_OUT'], 'w') as f:
    json.dump(out, f, indent=0, sort_keys=True)
U.log(f'{MARKER} {len(out)}')
