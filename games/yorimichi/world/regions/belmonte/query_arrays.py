"""Exact complete query triangle/colour arrays with an explicit natural/final stage."""
import json
from pathlib import Path
import tempfile
import zipfile

import numpy as np

from atelier.atomic_files import managed_temporary_parent
from atelier.export_manifest import name,real_directory

MAX_BYTES=256*1024*1024


def checked(faces,values=None):
    faces=np.asarray(faces,dtype='<f8')
    if (faces.ndim!=3 or faces.shape[1:]!=(3,3) or not len(faces) or not np.isfinite(faces).all()
            or faces.nbytes>MAX_BYTES):raise ValueError('Invalid complete query triangles')
    result=dict(faces=faces)
    if values is not None:
        values=np.asarray(values,dtype='<f8')
        if values.shape!=faces.shape or not np.isfinite(values).all():raise ValueError('Invalid complete query colours')
        result['values']=values
    if sum(value.nbytes for value in result.values())>MAX_BYTES:raise ValueError('Complete query arrays exceed envelope')
    return result


def write(path,faces,values=None,*,owner,stage):
    """@cc [owner:fontanierh,label:correctness] explicit-valley-query-data
    Query data MUST retain complete ordered triangle positions and optional
    per-corner colour values in their original float64 query frame. Natural
    and final identities MUST stay separate. No render export, source revision
    or unrelated catalogue field may enter otherwise unchanged query bytes.
    """
    path=Path(path);real_directory(path.parent);owner=name(owner)
    if stage not in ('natural','final') or path.name!=owner+'-'+stage+'.npz':raise ValueError('Foreign query data destination')
    result=checked(faces,values)
    result['metadata']=np.frombuffer(json.dumps(dict(schema=1,owner=owner,stage=stage),sort_keys=True).encode(),dtype=np.uint8)
    if path.is_symlink() or path.exists() and not path.is_file():raise ValueError('Query data must be regular')
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix='.query-arrays-',dir=managed_temporary_parent(path),delete=False) as stream:
        temporary=Path(stream.name);np.savez(stream,**result)
    try:
        if not path.exists() or path.read_bytes()!=temporary.read_bytes():temporary.replace(path)
    finally:temporary.unlink(missing_ok=True)


def read(path,*,owner,stage):
    path=Path(path);real_directory(path.parent)
    if (stage not in ('natural','final') or path.name!=name(owner)+'-'+stage+'.npz'
            or path.is_symlink() or not path.is_file() or path.stat().st_size>MAX_BYTES+1048576):raise ValueError('Invalid query data input')
    with zipfile.ZipFile(path) as archive:
        rows=archive.infolist()
        if (len(rows) not in (2,3) or len({row.filename for row in rows})!=len(rows)
                or sum(row.file_size for row in rows)>MAX_BYTES+1048576
                or any(row.compress_type!=zipfile.ZIP_STORED for row in rows)):raise ValueError('Unbounded query data archive')
    with np.load(path,allow_pickle=False) as value:
        if set(value.files) not in ({'metadata','faces'},{'metadata','faces','values'}):raise ValueError('Foreign query array fields')
        meta=value['metadata']
        if meta.dtype!=np.uint8 or meta.ndim!=1:raise ValueError('Invalid query array identity')
        identity=json.loads(meta.tobytes())
        if identity!=dict(schema=1,owner=owner,stage=stage) or type(identity['schema']) is not int:raise ValueError('Foreign query array identity')
        arrays={key:value[key] for key in value.files if key!='metadata'}
    if any(value.dtype!=np.dtype('<f8') for value in arrays.values()):raise ValueError('Query arrays changed numeric storage')
    return checked(arrays['faces'],arrays.get('values'))
