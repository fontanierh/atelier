"""Actual serialized Track triangles and independent query witnesses; standard library only."""
import math
import struct
from atelier.gltf import glb_parts
from atomic_equivalence_io import require



def sub(a,b):return [x-y for x,y in zip(a,b)]
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def f32(v):return struct.unpack('<f',struct.pack('<f',v))[0]


def triangles(data, *, asset=None):
    """Exact baked export_yup GLB frame -> native stored FVector3f centimetres.

    Track's single flat mesh export has no hierarchy/TRS. Reject other scenes.
    No polygon triangulation occurs here: indices are actual glTF TRIANGLES.
    """
    doc,binary=glb_parts(data)
    require(len(doc['nodes'])==1 and set(doc['nodes'][0])<={'mesh','name'}
        and doc['scenes'][doc.get('scene',0)]['nodes']==[0],'Unsupported Track source node/frame')
    if asset is not None:require(doc['nodes'][0].get('name')==asset,'Selected Track GLB logical identity differs')
    require(len(doc.get('buffers',[]))==1 and 'uri'not in doc['buffers'][0],'External Track source buffer')
    def accessor(index,kind,components):
        a=doc['accessors'][index];v=doc['bufferViews'][a['bufferView']]
        require(a['type']==kind and 'sparse'not in a and not a.get('normalized') and v.get('buffer',0)==0,'Unsupported source accessor')
        require(a['componentType']in components,'Unsupported source component encoding')
        code,size=components[a['componentType']];width=3 if kind=='VEC3'else 1
        start=v.get('byteOffset',0)+a.get('byteOffset',0);stride=v.get('byteStride',width*size)
        require(type(a['count'])is int and stride>=width*size and a['count']>0 and start>=v.get('byteOffset',0)
            and start+(a['count']-1)*stride+width*size<=v.get('byteOffset',0)+v['byteLength']<=len(binary),'Invalid source buffer range')
        return [struct.unpack_from('<'+code*width,binary,start+i*stride)for i in range(a['count'])]
    result=[]
    for primitive,p in enumerate(doc['meshes'][doc['nodes'][0]['mesh']]['primitives']):
        require(p.get('mode',4)==4 and 'indices'in p,'Track controls require actual indexed TRIANGLES')
        positions=accessor(p['attributes']['POSITION'],'VEC3',{5126:('f',4)})
        native=[[f32(x*100.),f32(z*100.),f32(y*100.)]for x,y,z in positions]
        require(all(math.isfinite(v)for p in native for v in p),'Nonfinite native source frame')
        indices=[v[0]for v in accessor(p['indices'],'SCALAR',{5121:('B',1),5123:('H',2),5125:('I',4)})]
        require(len(indices)%3==0 and all(0<=i<len(native)for i in indices),'Invalid source triangle indices')
        for first in range(0,len(indices),3):
            ids=indices[first:first+3]
            result.append(dict(primitive=primitive,triangle=first//3,indices=ids,corners_cm=[native[i]for i in ids]))
    require(result,'Empty Track source tessellation');return result


def segment_intersects(start,end,triangle):
    """Independent two-sided segment/triangle predicate; no tolerance normalization."""
    direction=sub(end,start);edge1=sub(triangle[1],triangle[0]);edge2=sub(triangle[2],triangle[0])
    h=cross(direction,edge2);det=dot(edge1,h)
    if det==0:return False
    delta=sub(start,triangle[0]);u=dot(delta,h)/det;q=cross(delta,edge1);v=dot(direction,q)/det;t=dot(edge2,q)/det
    return 0<=u<=1 and 0<=v and u+v<=1 and 0<=t<=1


def controls(name,source_triangles,*,suffix=''):
    best=None
    for row in source_triangles:
        t=row['corners_cm'];normal=cross(sub(t[1],t[0]),sub(t[2],t[0]));area=math.sqrt(dot(normal,normal))
        if area>0 and(best is None or area>best[0]):best=(area,row,normal)
    require(best is not None,'No nondegenerate serialized source triangle')
    area,witness,normal=best;center=[sum(p[k]for p in witness['corners_cm'])/3 for k in range(3)]
    normal=[v/area for v in normal]
    positive=dict(start=[p+n*200 for p,n in zip(center,normal)],end=[p-n*200 for p,n in zip(center,normal)],channel='Pawn',trace_complex=True)
    far=[max(p[k]for row in source_triangles for p in row['corners_cm'])+10000 for k in range(3)]
    negative=dict(start=far,end=[far[0],far[1],far[2]+100],channel='Pawn',trace_complex=True)
    result=[]
    for kind,query in (('positive',positive),('negative',negative)):
        for shape in ('ray','capsule'):
            item=dict(query)
            if shape=='capsule':item.update(radius_cm=.1,half_height_cm=.1,orientation=[0.,0.,0.,1.])
            result.append(dict(id=name+suffix+'.'+shape+'.'+kind,kind=shape+'_'+kind,input=item))
    return result,witness


def surface_witness(rows,witness,cooked):
    """Require real source triangle membership and independently valid cooked crossings."""
    target=sorted(tuple(p)for p in witness['corners_cm'])
    require(any(sorted(tuple(p)for p in t)==target for t in cooked),'Selected serialized triangle is not an exact cooked surface')
    require(len(rows)==4 and {r['kind']for r in rows}=={'ray_positive','capsule_positive','ray_negative','capsule_negative'},'Incomplete four query controls')
    for row in rows:
        q=row['input'];positive=row['kind'].endswith('positive')
        intersects=any(segment_intersects(q['start'],q['end'],t)for t in cooked)
        require(intersects is positive,'Declared query outcome lacks an independent cooked surface witness')
        if row['kind'].startswith('capsule') and not positive:
            require(all(min(q['start'][k],q['end'][k])-q['half_height_cm']>max(p[k]for t in cooked for p in t)
                for k in range(3)),'Negative capsule is not strictly outside cooked bounds')
    return dict(source_triangle=witness,cooked_triangle_exact=True,positive_segment_crosses=True,negative_segments_external=True)
