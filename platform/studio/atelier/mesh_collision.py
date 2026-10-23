"""Complete authored collision corner data inside bounded static-mesh inputs."""
import base64
import io
import zipfile

import numpy as np

CORE={'vertices','faces','matrix'}
RICH=CORE|{'corner_payload','material_slots'}
TRANSFORMED=RICH|{'transform'}
DUMMY='CollisionValidation'


def encode(piece,*,slots,matrix,transform=None):
    """Retain actual hull channels; an empty material table stays empty on export."""
    from . import mesh_ir
    slots=list(slots)
    packet=mesh_ir.encode(piece,key='Collision',slots=slots or [DUMMY],matrix=matrix,options={})
    value=dict(vertices=np.asarray(piece['positions'],dtype='<f4').tolist(),faces=piece['faces'],matrix=matrix,
               material_slots=slots,corner_payload=base64.b64encode(packet).decode('ascii'))
    if transform is not None:value['transform']=transform
    decode(value)
    return value


def unpack(value):
    from .mesh_ir import MAX_BYTES
    if (type(value) is not dict or set(value) not in (RICH,TRANSFORMED) or not isinstance(value['corner_payload'],str)
            or len(value['corner_payload'])>MAX_BYTES*2 or not isinstance(value['material_slots'],list)
            or any(not isinstance(slot,str) or not slot for slot in value['material_slots'])):
        raise ValueError('Invalid complete collision channels')
    if 'transform' in value:
        pose=value['transform'];fields={'location':3,'scale':3,'rotation_euler':3,'rotation_quaternion':4,'rotation_axis_angle':4}
        if (type(pose) is not dict or set(pose)!=set(fields)|{'rotation_mode'}
                or pose['rotation_mode'] not in ('XYZ','XZY','YXZ','YZX','ZXY','ZYX','QUATERNION','AXIS_ANGLE')
                or any(not isinstance(pose[key],list) or len(pose[key])!=width
                       or any(type(v) not in (int,float) or not np.isfinite(v) for v in pose[key]) for key,width in fields.items())
                or any(v==0 for v in pose['scale'])):
            raise ValueError('Invalid original collision transform components')
    try:
        packet=base64.b64decode(value['corner_payload'],validate=True)
        if not packet or len(packet)>MAX_BYTES:raise ValueError('Collision payload exceeds its bound')
        with zipfile.ZipFile(io.BytesIO(packet)) as archive:
            expanded=sum(row.file_size for row in archive.infolist())
        if expanded>MAX_BYTES:raise ValueError('Expanded collision payload exceeds its bound')
    except (ValueError,TypeError,zipfile.BadZipFile) as error:
        raise ValueError('Malformed collision corner payload') from error
    return packet,expanded


def decode(value,*,packet=None):
    """@cc [owner:fontanierh,label:correctness] complete-authored-collision-corners
    An authored hull's source normals, every UV/color layer and its type/roles,
    face order/winding/smoothing, material table and original transform MUST
    survive atomic export. Collision topology and its complete corner payload
    MUST agree exactly. Nested collisions, unknown channels, nonfinite or
    unbounded payloads MUST refuse. A validation-only material placeholder MUST
    never become an exported material on a material-free source hull.
    """
    from . import mesh_ir
    if packet is None:packet,_=unpack(value)
    meta,piece=mesh_ir.decode(packet,_collision_payload=True)
    if (meta['asset']!='Collision' or meta['options'] or meta['collisions']
            or meta['slots']!=(value['material_slots'] or [DUMMY])
            or piece['faces']!=value['faces']
            or np.asarray(value['vertices'],dtype='<f8').shape!=piece['positions'].shape
            or not np.array_equal(np.asarray(value['vertices'],dtype='<f8'),piece['positions'].astype('<f8'))
            or np.asarray(value['vertices'],dtype='<f4').tobytes()!=piece['positions'].tobytes()
            or np.asarray(value['matrix'],dtype='<f8').tobytes()!=np.asarray(meta['matrix'],dtype='<f8').tobytes()):
        raise ValueError('Collision corner data differs from its owned geometry')
    piece['slots']=list(value['material_slots'])
    if 'transform' in value:piece['transform']=value['transform']
    return piece
