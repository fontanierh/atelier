"""Read only the complete current independent prop library before native receiving."""
import hashlib
import json
from pathlib import Path

from asset_catalog import WORLD_PROPS
from atelier.export_manifest import real_directory


def read(root):
    root=Path(root)/'props';real_directory(root)
    path=root/'manifest.json'
    if path.is_symlink() or not path.is_file():raise ValueError('Missing regular current prop manifest')
    value=json.loads(path.read_text())
    if value.get('schema')!=1 or value.get('complete') is not True or not isinstance(value.get('exports'),list):
        raise ValueError('Incomplete current world prop library')
    result={};assets=real_directory(root/'assets')
    for row in value['exports']:
        key=row.get('asset')
        if (key not in WORLD_PROPS or key in result or row.get('primary')!=key+'.fbx'
                or type(row.get('triangles')) is not int or not 0<row['triangles']<=32768
                or row.get('metadata',{}).get('collision_hulls')!=0):
            raise ValueError('Foreign, duplicate or unbounded world prop')
        primary=assets/row['primary']
        if primary.is_symlink() or not primary.is_file() or hashlib.sha256(primary.read_bytes()).hexdigest()!=row.get('sha256'):
            raise ValueError('Current world prop export changed')
        result[key]=primary
    if set(result)!=set(WORLD_PROPS):raise ValueError('Missing original world prop owner')
    if {p.name for p in assets.iterdir()}!={'manifest.json',*(key+'.fbx' for key in WORLD_PROPS)}:
        raise ValueError('Foreign world prop export member')
    if any(path.is_symlink() or not path.is_file() for path in assets.iterdir()):
        raise ValueError('World prop members must be regular files')
    return result
