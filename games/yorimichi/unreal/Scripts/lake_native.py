"""Exact known logical lake ownership with one combined current-before-retirement preflight."""
from pathlib import Path
import re
from atelier import native_membership
from atelier.export_manifest import real_directory
from atelier.mesh_geometry import SIDECARS
OWNERS=('Lake_Cabin','Lake_Water','Lake_Trail','Lake_Shore','Lake_Plants')
DEST='/Game/Japan/Assets'


def owned(name):
    return isinstance(name,str) and bool(re.fullmatch(r'Lake_[A-Za-z0-9_-]+',name)) and any(
        name==parent or name.startswith(parent+'_cell_') or name.startswith(parent+'_Piece') for parent in OWNERS)


def inventory(editor):
    result=set()
    for asset in editor.list_assets(DEST,recursive=False,include_folder=False):
        if not isinstance(asset,str) or not asset.startswith(DEST+'/'):raise ValueError('Lake inventory escaped owner root')
        name=asset[len(DEST)+1:].split('.')[0]
        if not owned(name):continue
        package=DEST+'/'+name
        if asset not in (package,package+'.'+name) or package in result:raise ValueError('Invalid lake native identity')
        result.add(package)
    return result


def retire(editor,previous,names,content):
    if not names or len(names)!=len(set(names)) or any(not owned(name) for name in names):
        raise ValueError('Incomplete current lake membership')
    current=[DEST+'/'+name for name in names]
    real_directory(content)
    for package in previous|set(current):
        path=Path(content)/(package[6:]+'.uasset');real_directory(path.parent)
        if path.is_symlink() or (package in current and not path.is_file()):raise ValueError('Missing/linked current lake primary')
    if any(not editor.does_asset_exist(p) for p in current):raise ValueError('Current lake assets are missing')
    obsolete=previous-set(current)
    retired=native_membership.retire_replaced(editor,{p:current for p in obsolete}) if obsolete else []
    for package in retired:
        path=Path(content)/package[6:]
        if any(path.with_suffix(s).exists() or path.with_suffix(s).is_symlink() for s in SIDECARS):
            raise ValueError('Retired logical lake package remains on disk')
    if inventory(editor)!=set(current):raise ValueError('Current lake membership differs')
    return retired
