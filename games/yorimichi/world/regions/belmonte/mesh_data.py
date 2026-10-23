"""Lossless numeric terrain construction data, independent of mesh export files."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import zipfile

import numpy as np

from atelier.export_manifest import name,real_directory

MAX_BYTES=256*1024*1024


def arrays(mesh):
    if np.asarray(mesh.i).dtype.kind not in 'iu':raise ValueError('Terrain indices must retain integer storage')
    result={key:np.asarray(getattr(mesh,key),dtype='<i8' if key=='i' else '<f8') for key in ('p','n','t','i')}
    if getattr(mesh,'natural',None) is not None:result['natural']=np.asarray(mesh.natural,dtype='<f8')
    count=len(result['p'])
    if (not count or result['p'].shape!=(count,3) or result['n'].shape!=(count,3)
            or result['t'].shape!=(count,2) or result['i'].ndim!=1 or not len(result['i'])
            or len(result['i'])%3 or result['i'].min()<0 or result['i'].max()>=count
            or 'natural' in result and result['natural'].shape!=(count,)
            or any(not np.isfinite(value).all() for value in result.values())
            or sum(value.nbytes for value in result.values())>MAX_BYTES):raise ValueError('Invalid terrain construction arrays')
    return result


def write(path,mesh,*,owner):
    """@cc [owner:fontanierh,label:correctness] terrain-data-before-independent-exports
    Intermediate terrain products MUST retain exact float64 positions, normals,
    UVs, ordered triangle indices and optional natural heights. They MUST NOT
    serialize an exported render mesh or merge logical owners. Owner identity,
    finite values and complete array membership MUST be verified on read.
    """
    path=Path(path);real_directory(path.parent);owner=name(owner)
    if path.stem!=owner or path.suffix!='.npz':raise ValueError('Foreign terrain data path')
    value=arrays(mesh);value['identity']=np.asarray(json.dumps(dict(schema=1,owner=owner),sort_keys=True))
    if path.is_symlink() or path.exists() and not path.is_file():raise ValueError('Terrain data must be regular')
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix='.terrain-',dir=path.parent,delete=False) as stream:
        temporary=Path(stream.name);np.savez(stream,**value)
    try:
        if not path.exists() or path.read_bytes()!=temporary.read_bytes():temporary.replace(path)
    finally:temporary.unlink(missing_ok=True)


def read(path,*,owner):
    path=Path(path);real_directory(path.parent)
    if (path.stem!=name(owner) or path.suffix!='.npz' or path.is_symlink() or not path.is_file()
            or path.stat().st_size>MAX_BYTES+1024*1024):raise ValueError('Invalid terrain data input')
    with zipfile.ZipFile(path) as archive:
        files=archive.infolist()
        if (len({row.filename for row in files})!=len(files) or len(files) not in (5,6)
                or sum(row.file_size for row in files)>MAX_BYTES+1024*1024
                or any(row.compress_type!=zipfile.ZIP_STORED for row in files)):
            raise ValueError('Unbounded terrain data archive')
    with np.load(path,allow_pickle=False) as value:
        if set(value.files) not in ({'p','n','t','i','identity'},{'p','n','t','i','natural','identity'}):
            raise ValueError('Foreign terrain data members')
        identity=json.loads(str(value['identity']))
        if (identity!=dict(schema=1,owner=owner) or type(identity['schema']) is not int):
            raise ValueError('Terrain data belongs to another owner')
        result={key:value[key] for key in value.files if key!='identity'}
    if any(value.dtype!=np.dtype('<i8' if key=='i' else '<f8') for key,value in result.items()):
        raise ValueError('Terrain data changed numeric storage')
    mesh=SimpleNamespace(**result);arrays(mesh)
    return mesh
