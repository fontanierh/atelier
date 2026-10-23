"""Finite exact legacy FBX query frame, without a mesh export/import dependency."""
import hashlib
import json
from pathlib import Path

CODEC = Path(__file__).resolve().parents[2] / 'assets/vehicles/gondola/fbx-query-frame.json'
_checked = None


def checked_codec():
    global _checked
    if _checked is not None:return _checked
    import bpy
    from io_scene_fbx import parse_fbx
    import bpy_extras.io_utils
    value=json.loads(CODEC.read_text())
    if (value.get('schema')!=1 or value.get('codec')!='blender-static-identity-fbx-world-frame-v1'
            or value.get('source_matrix')!='identity' or value.get('position_dtype')!='<f4'
            or value.get('computation_dtype')!='<f8' or list(bpy.app.version)!=value.get('blender_version')
            or bpy.app.build_hash.decode()!=value.get('blender_build_hash')):
        raise ValueError('Unsupported FBX query codec/version/tool; exact roundtrip proof required')
    root=Path(parse_fbx.__file__).parent
    files={'io_scene_fbx/'+path.name:path for path in root.glob('*.py')}
    files['bpy_extras/io_utils.py']=Path(bpy_extras.io_utils.__file__)
    if set(files)!=set(value['tool_files']) or any(hashlib.sha256(path.read_bytes()).hexdigest()!=value['tool_files'][key] for key,path in files.items()):
        raise ValueError('FBX query codec source changed; exact roundtrip proof required')
    _checked=value
    return value


def imported_identity_triangles(surfaces,*,roles=('render','collision')):
    """@cc [owner:fontanierh,label:correctness] exact-legacy-fbx-query-frame
    Queries MUST preserve the actual legacy FBX float32 positions, ordered
    tessellation and float32 imported object frame promoted to float64. The
    supported identity-source conversion MUST be byte-proven and tool-bound;
    unsupported source matrices, dtypes or codecs MUST refuse, never approximate
    or silently return the clean pre-export frame. This function exports no mesh.
    """
    import numpy as np
    value=checked_codec()
    matrix=np.asarray(value['world_matrix'],dtype='<f8')
    if (matrix.shape!=(4,4) or not np.isfinite(matrix).all() or not np.array_equal(matrix[3],[0,0,0,1])
            or not np.array_equal(matrix,matrix.astype('<f4').astype('<f8')) or np.linalg.det(matrix[:3,:3])==0
            or not roles or any(role not in ('render','collision') for role in roles)):
        raise ValueError('Invalid exact FBX query frame or role selection')
    rows=[]
    for surface in surfaces:
        if surface['role'] not in roles:continue
        positions=surface['positions'];triangles=surface['triangles'];frame=surface['matrix']
        if (positions.dtype!=np.dtype('<f4') or positions.ndim!=2 or positions.shape[1]!=3 or not np.isfinite(positions).all()
                or not np.array_equal(frame,np.eye(4)) or triangles.ndim!=2 or triangles.shape[1]!=3
                or triangles.dtype.kind not in 'iu' or not len(triangles) or triangles.min()<0 or triangles.max()>=len(positions)):
            raise ValueError('Unsupported source query frame/geometry; exact FBX conversion proof required')
        # Preserve the original probe's operation order: transform the complete
        # local vertex array in float64, then index actual source loop triangles.
        vertices=positions.astype('<f8')@matrix[:3,:3].T+matrix[:3,3]
        rows.append(vertices[triangles])
    return np.concatenate(rows) if rows else np.empty((0,3,3),dtype='<f8')
