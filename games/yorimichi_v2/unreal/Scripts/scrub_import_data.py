"""Remove donor import provenance from adopted packages before they are committed (plan P3 step 1; CONTRACTS
yorimichi-v2-portable-records). Run through `editor.run` (V2_EDITOR_SCRIPT=unreal/Scripts/scrub_import_data.py).

An adopted package's import data names the donor checkout's absolute source files (a home folder), and an
Interchange import also keeps its node graph, which repeats them. V2 does not reimport adopted packages from
those files: a generated asset's sources are its record's repository-relative paths. So each asset under
V2_SCRUB_FOLDERS (comma-separated /Game folders) whose import data names any source file has each recorded file
blanked, any Interchange node graph replaced by an empty one and its factory node ID renamed after the asset, and
only those packages are saved. Geometry,
materials and settings are untouched; a package without import data, or with none recorded, is not resaved.
"""
import os

import unreal as U

MARKER = 'V2 SCRUB DONE'
EAL = U.EditorAssetLibrary


def sources(data):
    # A blanked file reads back resolved against the editor's working folder (Engine/Binaries/<platform>).
    blank = os.path.normpath(os.getcwd())
    try:
        return [f for f in data.extract_filenames() if f and os.path.normpath(f) != blank]
    except Exception:   # an import data class without the scripted accessors still names its sources
        return ['<unreadable>']


def private_node(data):
    """An Interchange factory node ID still naming a file (a scrub before the ID was renamed)."""
    try:
        uid = str(data.get_editor_property('node_unique_id'))
    except Exception:
        return False
    return '/' in uid or '\\' in uid


def main():
    folders = [f.strip() for f in os.environ.get('V2_SCRUB_FOLDERS', '').split(',') if f.strip()]
    if not folders or any(not f.startswith('/Game/') for f in folders):
        raise RuntimeError('V2_SCRUB_FOLDERS must name /Game folders')
    scrubbed = kept = 0
    for folder in folders:
        for index, path in enumerate(EAL.list_assets(folder, recursive=True, include_folder=False)):
            if index % 256 == 255:
                U.SystemLibrary.collect_garbage()   # thousands of adopted assets: bound what stays loaded
            asset = EAL.load_asset(path.split('.')[0])
            if asset is None:
                raise RuntimeError(f'cannot load {path}')
            try:
                data = asset.get_editor_property('asset_import_data')
            except Exception:
                kept += 1
                continue
            if data is None or not (sources(data) or private_node(data)):
                kept += 1
                continue
            # The property is read-only on textures in 5.8: blank each recorded file in place instead, and drop
            # an Interchange import's node graph, which repeats them.
            for slot in range(len(data.extract_filenames())):
                data.scripted_add_filename('', slot, '')
            if hasattr(data, 'set_node_container') and hasattr(U, 'InterchangeBaseNodeContainer'):
                data.set_node_container(U.new_object(U.InterchangeBaseNodeContainer, outer=data))
                # Its factory node's ID is the source file too ("Factory_<path>"), read-only to scripts: name it after the asset.
                if not U.ImportProvenance.rename_interchange_node(data, f'Factory_{asset.get_name()}'):
                    raise RuntimeError(f'{path}: Interchange data without a renamable node ID')
            if sources(data):
                raise RuntimeError(f'{path} still names {sources(data)}')
            if not EAL.save_loaded_asset(asset, only_if_is_dirty=False):
                raise RuntimeError(f'could not save {path}')
            scrubbed += 1
    U.log(f'{MARKER} scrubbed={scrubbed} kept={kept}')


main()
