"""Bake TRELLIS's learned colors to native vertices without constructing UVs.

This alternative retains the exact raw native positions/indices and owns one
aggregate CPU guard. Metallic/roughness variation is not represented in this preview.
"""
from pathlib import Path
from functools import partial
import argparse
import gzip
import json
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image,ImageDraw
from meshaxiom_pixel_match import digest,load_module,fitted_view,matte,silhouette,stage
from meshaxiom_quality import VENDOR,write


def vertex_colors(shape_coords, texture_coords, attributes, resolution):
    """@cc [owner:fontanierh,label:correctness] native-vertex-color-support
    Every raw dual-grid vertex MUST use the learned color of its own decoder voxel.
    Missing, duplicate or nonfinite support MUST reject; input arrays MUST remain unchanged.
    """
    a=np.asarray(shape_coords,dtype='int64');b=np.asarray(texture_coords,dtype='int64')
    if a.ndim!=2 or b.shape!=a.shape or a.shape[1]!=3 or len(attributes)!=len(a):
        raise ValueError('Decoder/color support shape mismatch')
    if not np.isfinite(attributes).all() or (a<0).any() or (b<0).any() or (a>=resolution).any() or (b>=resolution).any():
        raise ValueError('Invalid decoder/color support')
    ka=(a[:,0]*resolution+a[:,1])*resolution+a[:,2]
    kb=(b[:,0]*resolution+b[:,1])*resolution+b[:,2]
    order=np.argsort(kb);ordered=kb[order]
    if (np.diff(ordered)==0).any() or len(np.unique(ka))!=len(ka):
        raise ValueError('Duplicate decoder/color support')
    index=np.searchsorted(ordered,ka)
    if (index>=len(ordered)).any() or not np.array_equal(ordered[index],ka):
        raise ValueError('Missing native vertex color support')
    return np.clip(np.asarray(attributes)[order[index],:3],0,1).astype('float32')


def linear(values):
    return np.where(values<=.04045,values/12.92,((values+.055)/1.055)**2.4).astype('float32')


def srgb(values):
    return np.where(values<=.0031308,values*12.92,1.055*np.maximum(values,0)**(1/2.4)-.055)


def worker(args):
    started=time.monotonic();args.output.mkdir(parents=True,exist_ok=True)
    print('Loading native shape/PBR checkpoints for vertex bake',flush=True)
    if (args.output/'head.glb').exists():raise ValueError('Completed vertex-bake trial exists')
    with np.load(args.checkpoint/'mesh_raw.npz',allow_pickle=False) as raw:
        vertices=raw['vertices'].astype('<f4');faces=raw['faces'].astype('<u4')
    with np.load(args.checkpoint/'decoder_output.npz',allow_pickle=False) as decoder:
        coords=decoder['coords'][:,1:4].copy()
    with np.load(args.checkpoint/'texture.npz',allow_pickle=False) as texture:
        attrs=texture['tex_np'];tex_coords=texture['tex_coords_spatial']
        grid=json.loads((args.checkpoint/'mesh_raw.json').read_text())['mesh_grid_size']
        colors=vertex_colors(coords,tex_coords,attrs,grid)
    if len(vertices)!=len(colors) or not np.isfinite(vertices).all() or faces.max()>=len(vertices):
        raise ValueError('Raw mesh and decoder support differ')
    positions=vertices.copy();positions[:,1]=vertices[:,2];positions[:,2]=-vertices[:,1]
    print(f'Color support verified for{len(vertices):,} native vertices; deriving display normals',flush=True)
    normals=np.zeros_like(positions)
    for start in range(0,len(faces),65536):
        f=faces[start:start+65536];p=positions[f]
        n=np.cross(p[:,1]-p[:,0],p[:,2]-p[:,0])
        for corner in range(3):np.add.at(normals,f[:,corner],n)
    normals/=np.maximum(np.linalg.norm(normals,axis=1,keepdims=True),1e-20)
    values=linear(colors)
    arrays=[positions.astype('<f4'),normals.astype('<f4'),values.astype('<f4'),faces.astype('<u4')]
    views=[];binary=bytearray()
    for array in arrays:
        binary+=b'\0'*(-len(binary)%4)
        views.append(dict(buffer=0,byteOffset=len(binary),byteLength=array.nbytes))
        binary+=array.tobytes()
    accessors=[dict(bufferView=i,componentType=5126,count=len(vertices),type='VEC3') for i in range(3)]
    accessors[0].update(min=positions.min(0).tolist(),max=positions.max(0).tolist())
    accessors.append(dict(bufferView=3,componentType=5125,count=faces.size,type='SCALAR'))
    doc=dict(asset=dict(version='2.0',generator='Atelier native TRELLIS vertex color bake'),
        scene=0,scenes=[dict(nodes=[0])],nodes=[dict(mesh=0)],
        meshes=[dict(primitives=[dict(attributes=dict(POSITION=0,NORMAL=1,COLOR_0=2),indices=3,material=0,mode=4)])],
        materials=[dict(doubleSided=True,pbrMetallicRoughness=dict(baseColorFactor=[1,1,1,1],metallicFactor=0,roughnessFactor=.85))],
        buffers=[dict(byteLength=len(binary))],bufferViews=views,accessors=accessors)
    pm=load_module(VENDOR);model=args.output/'head.glb';model.write_bytes(pm._join_glb(doc,bytes(binary)))
    checked,payload=pm._split_glb(model.read_bytes())
    for index,expected in [(0,positions),(3,faces)]:
        view=checked['bufferViews'][index];offset=view['byteOffset']
        actual=np.frombuffer(payload,dtype='<f4' if index==0 else '<u4',count=expected.size,offset=offset).reshape(expected.shape)
        if not np.array_equal(actual,expected):raise ValueError('Vertex bake changed raw positions/indices')
    del binary,payload,arrays
    print('Raw positions/indices verified in GLB; streaming complete source archive',flush=True)
    spoken=time.monotonic()
    # Stream the complete native source for independent downloads without a huge Python list.
    with gzip.open(args.output/'mesh.json.gz','wt',encoding='utf-8') as out:
        out.write('{"vertices":[')
        for first in range(0,len(positions),65536):
            if first:out.write(',')
            out.write(json.dumps(positions[first:first+65536].tolist(),separators=(',',':'))[1:-1])
            if time.monotonic()-spoken>=20:
                print(f'Source archive: {min(first+65536,len(positions)):,}/{len(positions):,} vertices',flush=True);spoken=time.monotonic()
        out.write('],"faces":[')
        for first in range(0,len(faces),65536):
            if first:out.write(',')
            out.write(json.dumps(faces[first:first+65536].tolist(),separators=(',',':'))[1:-1])
            if time.monotonic()-spoken>=20:
                print(f'Source archive: {min(first+65536,len(faces)):,}/{len(faces):,} triangles',flush=True);spoken=time.monotonic()
        out.write(']}')
    report=dict(method='Learned native voxel color to raw dual-grid vertex bake, no UVs',
        worker_sha256=digest(Path(__file__)),native_checkpoint_sha256=digest(args.checkpoint/'mesh_raw.npz'),
        texture_checkpoint_sha256=digest(args.checkpoint/'texture.npz'),output_sha256=digest(model),
        vertices=len(vertices),triangles=len(faces),all_native_positions_and_indices_exact=True,
        material='sRGB field converted to linear vertex RGB; uniform roughness.85/metallic0; PBR variation omitted',
        transform='Only fixed Z-up to Y-up axis rotation',seconds=round(time.monotonic()-started,3))
    write(args.output/'vertex-bake.json',report)
    print(json.dumps(report),flush=True)
    if not args.render:return
    render_vertices(args,pm,positions,faces,values,model)


def render_vertices(args,pm,positions,faces,values,model):
    pm.rasterize=partial(pm.rasterize,chunk=256)
    reference=matte(Image.open(args.image));contact=Image.new('RGB',(1536,816));draw=ImageDraw.Draw(contact)
    cameras=[]
    for index,(yaw,pitch) in enumerate([(0,-5),(60,-5),(120,-5),(180,-5),(240,-5),(300,-5),(60,55),(240,-40)]):
        view=fitted_view(pm,positions,reference,yaw+args.yaw_offset,pitch)
        name=f'yaw{yaw}-pitch{pitch}'
        with stage(f'Native vertex-color view {index+1}/8'):
            face,bary=silhouette(pm,positions,faces,view);seen=face>=0
            rgb=(values[faces[face[seen]]]*bary[seen,:,None]).sum(1)
            pixels=np.zeros((*seen.shape,3),dtype='uint8');pixels[seen]=np.clip(srgb(rgb)*255,0,255).astype('uint8')
        Image.fromarray(pixels).save(args.output/(name+'.png'))
        contact.paste(Image.fromarray(pixels).resize((384,384)),(index%4*384,index//4*408))
        draw.text((index%4*384+8,index//4*408+386),name,fill='white')
        cameras.append(dict(name=name,yaw=yaw+args.yaw_offset,pitch=pitch,transform_matrix=view.cam_to_world.tolist(),camera_angle_x=view.fov_x))
    contact.save(args.output/'contact.png')
    write(args.output/'comparison.json',dict(model_sha256=digest(model),reference_sha256=digest(args.image),
        camera_yaw_offset=args.yaw_offset,source_unchanged=True,mode='Base color, no relighting',views=cameras))


def render_existing(args):
    """Render an existing native vertex-color GLB without rewriting its model bytes."""
    args.output.mkdir(parents=True,exist_ok=True)
    pm=load_module(VENDOR);before=digest(args.model)
    doc,payload=pm._split_glb(args.model.read_bytes())
    if doc.get('nodes')!=[dict(mesh=0)]:raise ValueError('Vertex-color comparison requires identity node transforms')
    if len(doc['meshes'])!=1 or len(doc['meshes'][0]['primitives'])!=1:
        raise ValueError('Vertex-color comparison requires one complete native primitive')
    primitive=doc['meshes'][0]['primitives'][0]
    if primitive.get('mode',4)!=4:raise ValueError('Expected native triangles')
    def read(index,kind,component,dtype,width):
        a=doc['accessors'][index];v=doc['bufferViews'][a['bufferView']]
        if a['type']!=kind or a['componentType']!=component or a.get('sparse') or v.get('byteStride') or v.get('buffer',0)!=0:
            raise ValueError('Unsupported native vertex attribute layout')
        return np.frombuffer(payload,dtype=dtype,count=a['count']*width,
            offset=v.get('byteOffset',0)+a.get('byteOffset',0)).reshape(a['count'],width)
    positions=read(primitive['attributes']['POSITION'],'VEC3',5126,'<f4',3)
    values=read(primitive['attributes']['COLOR_0'],'VEC3',5126,'<f4',3)
    faces=read(primitive['indices'],'SCALAR',5125,'<u4',1).reshape(-1,3)
    render_vertices(args,pm,positions,faces,values,args.model)
    if digest(args.model)!=before:raise ValueError('Comparison changed the native GLB')


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--image',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--render',action='store_true')
    p.add_argument('--yaw-offset',type=float,default=0)
    p.add_argument('--memory-gib',type=int,choices=range(4,11),default=8)
    p.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    args=p.parse_args(argv)
    if not -360<=args.yaw_offset<=360:p.error('Camera offset must be within one turn')
    if args.worker:return worker(args)
    if args.report.exists():p.error('Use a fresh guard report')
    from atelier.harness.safety.guarded import run
    forwarded=sys.argv[1:] if argv is None else list(argv)
    return run([sys.executable,'-u',str(Path(__file__).resolve()),*forwarded,'--worker'],args.report,
        timeout=1800,purpose='Native TRELLIS vertex-color export and matched views',
        limit_gib=args.memory_gib,aggregate_tree=True,progress=20)


if __name__=='__main__':sys.exit(main())
