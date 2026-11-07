"""Remove donor import provenance from adopted packages before they are committed (plan P3 step 1; CONTRACTS
yorimichi-v2-portable-records). Run through `editor.run` (V2_EDITOR_SCRIPT=unreal/Scripts/scrub_import_data.py).

An adopted package's import data names the donor checkout's absolute source files (a home folder), and an
Interchange import also keeps its node graph, which repeats them. V2 does not reimport adopted packages from
those files: a generated asset's sources are its record's repository-relative paths. So each asset under
V2_SCRUB_FOLDERS (comma-separated /Game folders) whose import data names any source file gets a fresh, empty
import data object of the base class, and only those packages are saved. Geometry, materials and settings are
untouched; a package without import data, or with none recorded, is not resaved.
"""
import os

import unreal as U

MARKER = 'V2 SCRUB DONE'
EAL = U.EditorAssetLibrary


def sources(data):
    try:
        return [f for f in data.extract_filenames() if f]
    except Exception:   # an import data class without the scripted accessors still names its sources
        return ['<unreadable>']


def main():
    folders = [f.strip() for f in os.environ.get('V2_SCRUB_FOLDERS', '').split(',') if f.strip()]
    if not folders or any(not f.startswith('/Game/') for f in folders):
        raise RuntimeError('V2_SCRUB_FOLDERS must name /Game folders')
    scrubbed = kept = 0
    for folder in folders:
        for path in EAL.list_assets(folder, recursive=True, include_folder=False):
            asset = EAL.load_asset(path.split('.')[0])
            if asset is None:
                raise RuntimeError(f'cannot load {path}')
            try:
                data = asset.get_editor_property('asset_import_data')
            except Exception:
                kept += 1
                continue
            if data is None or not sources(data):
                kept += 1
                continue
            asset.set_editor_property('asset_import_data', U.new_object(U.AssetImportData, outer=asset))
            # The old object is still inside the package and would be saved with it: move it out.
            data.rename(None, U.get_transient_package())
            if not EAL.save_loaded_asset(asset, only_if_is_dirty=False):
                raise RuntimeError(f'could not save {path}')
            scrubbed += 1
    U.log(f'{MARKER} scrubbed={scrubbed} kept={kept}')


main()
