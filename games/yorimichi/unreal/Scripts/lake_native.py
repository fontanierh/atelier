"""Exact known logical lake ownership with one combined current-before-retirement preflight."""
from pathlib import Path
import hashlib
import json
import math
import re
from atelier import native_membership
from atelier.export_manifest import real_directory
from atelier.mesh_geometry import SIDECARS
OWNERS=('Lake_Cabin','Lake_Water','Lake_Trail','Lake_Shore','Lake_Plants')
DEST='/Game/Japan/Lake/Pieces'
LEGACY='/Game/Japan/Assets'


def owned(name):
    return isinstance(name,str) and any(name==parent or bool(re.fullmatch(re.escape(parent)+
        r'_cell_(?:0|-?[1-9][0-9]*)_(?:0|-?[1-9][0-9]*)(?:_Piece[0-3]{1,16})?',name)) for parent in OWNERS)


def inventory(editor):
    result=set()
    for root in (DEST,LEGACY):
        for asset in editor.list_assets(root,recursive=False,include_folder=False):
            if not isinstance(asset,str) or not asset.startswith(root+'/'):raise ValueError('Lake inventory escaped owner root')
            name=asset[len(root)+1:].split('.')[0]
            if root==LEGACY and not owned(name):continue
            if not owned(name):raise ValueError('Foreign package in exclusive lake owner root')
            package=root+'/'+name
            if asset not in (package,package+'.'+name) or package in result:raise ValueError('Invalid lake native identity')
            result.add(package)
    return result


def read(root):
    """@cc [owner:fontanierh,label:correctness] complete-lake-source-admission
    Every declared logical child MUST have current bounded geometry, original zero-hull
    ownership, finite bounds and exact primary bytes before any receiving mutation.
    """
    real_directory(root)
    path=root/'manifest.json'
    if path.is_symlink():raise ValueError('Linked lake manifest')
    value=json.loads(path.read_text())
    if (value.get('schema')!=2 or value.get('complete') is not True or
            set(value.get('parents',{}))!=set(OWNERS) or not isinstance(value.get('assets'),dict)):
        raise ValueError('Lake requires complete current logical membership')
    names=[]
    for parent in OWNERS:
        children=value['parents'][parent]
        if not isinstance(children,list) or not children:raise ValueError('Missing lake logical children')
        for name in children:
            if not owned(name) or not (name==parent or name.startswith(parent+'_cell_')):
                raise ValueError('Foreign lake logical child')
            row=value['assets'].get(name,{})
            if (row.get('parent')!=parent or row.get('fbx')!='assets/'+name+'.fbx' or
                    type(row.get('triangles')) is not int or not 0<row['triangles']<=32768 or
                    type(row.get('collision_boxes')) is not int or row['collision_boxes']!=0):
                raise ValueError('Invalid current lake geometry')
            low,high=row.get('min'),row.get('max')
            if not isinstance(low,list) or not isinstance(high,list) or len(low)!=3 or len(high)!=3 or any(
                type(v) not in (int,float) or not math.isfinite(v) for v in low+high) or any(a>b for a,b in zip(low,high)):
                raise ValueError('Invalid lake source bounds')
            source=root/row['fbx'];real_directory(source.parent)
            if source.is_symlink() or not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=row.get('sha256'):
                raise ValueError('Lake export changed')
            names.append(name)
    if len(names)!=len({n.casefold() for n in names}) or set(names)!=set(value['assets']):
        raise ValueError('Incomplete or duplicate lake receiving inventory')
    return value


def retire(editor,previous,names,content):
    """@cc [owner:fontanierh,label:correctness] combined-lake-owner-retirement
    Current complete saved pieces MUST precede one combined preflight for old logical
    parents and obsolete children. Foreign references MUST refuse the entire retirement;
    every retired primary and supported sidecar MUST be physically absent afterward.
    """
    if not names or len(names)!=len(set(names)) or any(not owned(name) for name in names):
        raise ValueError('Incomplete current lake membership')
    current=[DEST+'/'+name for name in names]
    real_directory(content)
    for package in previous|set(current):
        name=package.rsplit('/',1)[-1]
        if not owned(name) or package not in (DEST+'/'+name,LEGACY+'/'+name):
            raise ValueError('Retirement package escaped exact lake ownership')
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
