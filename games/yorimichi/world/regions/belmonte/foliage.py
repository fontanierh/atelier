"""Explicit shared authored policy for Belmonte's small, inseparable planted props."""
import hashlib
import numpy as np
from atelier.gltf import glb_pack, glb_parts
import foliage_roles

AUTHORED = frozenset('SM_BM_BP_'+name for name in (
    'BarrelPlanter', 'FlowerBucket', 'FlowerStand', 'PotGeranium', 'PotHerb',
    'PotLavender', 'PotShrub', 'StonePlanter_A', 'StonePlanter_B'))


def prepare(path):
    """Append the common role channel without changing any source buffer or paint."""
    source = path.read_bytes()
    doc, original = glb_parts(source)
    primitives = [p for mesh in doc['meshes'] for p in mesh['primitives']]
    assert all(p.get('mode', 4)==4 for p in primitives), path
    triangles = sum(doc['accessors'][p['indices']]['count']//3 for p in primitives)
    if triangles>foliage_roles.AUTHORED_BUDGET:
        raise ValueError('Authored foliage prop exceeds triangle budget: '+str(path))
    binary = bytearray(original)

    def coordinates(count, value):
        binary.extend(b'\0'*(-len(binary)%4))
        values = np.tile(np.asarray(value,dtype='<f4'),(count,1)).tobytes()
        view = len(doc['bufferViews'])
        doc['bufferViews'].append(dict(buffer=0,byteOffset=len(binary),byteLength=len(values)))
        binary.extend(values)
        index = len(doc['accessors'])
        doc['accessors'].append(dict(bufferView=view,componentType=5126,count=count,type='VEC2'))
        return index

    for primitive in primitives:
        attributes = primitive['attributes']
        if 'TEXCOORD_5' in attributes:
            raise ValueError('UV channel 5 is reserved for foliage roles: '+str(path))
        count = doc['accessors'][attributes['POSITION']]['count']
        zero = coordinates(count,(0.,0.))
        for channel in range(5):
            attributes.setdefault('TEXCOORD_'+str(channel),zero)
        attributes['TEXCOORD_5'] = coordinates(count,(3.,foliage_roles.MARKER))
    doc.setdefault('extras',{})['atelier_foliage_policy']='authored-v1'
    doc['buffers'][0]['byteLength']=len(binary)
    path.write_bytes(glb_pack(doc,bytes(binary)))
    return dict(foliage='authored', source_sha256=hashlib.sha256(source).hexdigest(),
                sha256=hashlib.sha256(path.read_bytes()).hexdigest())
