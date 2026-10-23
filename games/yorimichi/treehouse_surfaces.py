"""Complete bounded logical Treehouse surfaces and exact source/native ownership."""
import json
import math
from pathlib import Path
import re
from atelier.export_manifest import real_directory,sha
from atelier.mesh_geometry import SIDECARS

PARENTS=('TH_Structure','TH_Frame','TH_Trunks','TH_Dressing')
STRUCTURE='/Game/Japan/Treehouse/StructurePieces'
DRESSING='/Game/Japan/Treehouse/Pieces'
CELL=r'(?:0|-?[1-9][0-9]*)_(?:0|-?[1-9][0-9]*)(?:_Piece[0-3]{1,16})?'


def destination(parent):
    return STRUCTURE if parent=='TH_Structure' else DRESSING if parent=='TH_Dressing' else '/Game/Japan/Assets'


def valid_name(parent,name):
    if parent not in PARENTS or not isinstance(name,str):return False
    if parent in ('TH_Frame','TH_Trunks'):return name==parent
    return bool(re.fullmatch(re.escape(parent)+'_cell_'+CELL,name))


def rows(out,*,verify_files=True):
    root=Path(out)/'treehouse';real_directory(root)
    file=root/'surfaces.json'
    if file.is_symlink():raise ValueError('Linked Treehouse membership')
    value=json.loads(file.read_text())
    parents=value.get('parents');assets=value.get('assets')
    if (value.get('schema')!=1 or value.get('complete') is not True or not isinstance(parents,dict)
            or set(parents)!=set(PARENTS) or not isinstance(assets,dict)):
        raise ValueError('Incomplete Treehouse surface owner')
    expected=[]
    for parent in PARENTS:
        members=parents[parent]
        if not isinstance(members,list) or not members or any(not valid_name(parent,name) for name in members):
            raise ValueError('Invalid Treehouse logical surface membership')
        expected.extend(members)
    if len(set(expected))!=len(expected) or set(expected)!=set(assets):raise ValueError('Duplicate or partial Treehouse surfaces')
    result=[]
    for name in expected:
        row=assets[name];parent=row.get('parent')
        if parent not in parents or name not in parents[parent]:raise ValueError('Foreign Treehouse surface parent')
        folder='structure' if parent=='TH_Structure' else 'dressing' if parent=='TH_Dressing' else parent.removeprefix('TH_').lower()
        low,high=row.get('min'),row.get('max')
        if (type(row.get('triangles')) is not int or not 0<row['triangles']<=32768 or row.get('collision_hulls')!=0
                or row.get('fbx')!='assets/'+folder+'/'+name+'.fbx'
                or not isinstance(low,list) or not isinstance(high,list) or len(low)!=3 or len(high)!=3
                or any(type(v) not in (int,float) or not math.isfinite(v) for v in (*low,*high))
                or any(a>b for a,b in zip(low,high))
                or row.get('uv_channels')!=(['UVMap','Piece1','Piece2','Piece3','Piece4'] if parent in ('TH_Frame','TH_Dressing') else ['UVMap'])
                or not isinstance(row.get('slots'),list) or not row['slots'] or len(set(row['slots']))!=len(row['slots'])
                or any(not isinstance(slot,str) or not re.fullmatch('TH_[A-Za-z0-9_]+',slot) for slot in row['slots'])
                or not isinstance(row.get('used_slots'),list) or not row['used_slots']
                or not set(row['used_slots'])<=set(row['slots'])
                or not isinstance(row.get('sha256'),str) or not re.fullmatch('[0-9a-f]{64}',row['sha256'])):
            raise ValueError('Invalid current bounded Treehouse surface')
        path=root/row['fbx'];real_directory(path.parent)
        if verify_files and (path.is_symlink() or not path.is_file() or sha(path)!=row['sha256']):
            raise ValueError('Missing or changed current Treehouse source')
        result.append(dict(row,name=name,package=destination(parent)+'/'+name))
    return result


def absent(content,package):
    path=Path(content)/package.removeprefix('/Game/')
    real_directory(path.parent)
    return not any(path.with_suffix(suffix).exists() or path.with_suffix(suffix).is_symlink() for suffix in SIDECARS)


def retired_parents_absent(content):
    return all(absent(content,'/Game/Japan/Assets/'+parent) for parent in ('TH_Structure','TH_Dressing'))
