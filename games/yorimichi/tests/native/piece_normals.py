"""Guarded Blender regression: real pier fans retain exact normals through native subdivision and FBX.

Run through atelier's guarded Blender launcher with --output pointing at a fresh diagnostic directory.
This uses the real pier source, copier and FBX boundary; it does not prepare a world or render.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

import bpy
import numpy as np

GAME=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(GAME/'world'),str(GAME/'world/regions'),str(GAME/'world/regions/skatepark')]
import geom
import features
import pieces
from mesh_pieces import capture,subset,create_mesh,values
from io_scene_fbx import parse_fbx


def faces(path):
    root,_=parse_fbx.parse(str(path))
    def child(parent,name):
        return next(item for item in parent.elems if item.id==name)
    objects=child(root,b'Objects')
    geometry=[item for item in objects.elems if item.id==b'Geometry']
    assert len(geometry)==1
    geometry=geometry[0]
    coordinates=np.asarray(child(geometry,b'Vertices').props[0]).reshape(-1,3)
    indices=list(child(geometry,b'PolygonVertexIndex').props[0])
    layer=child(geometry,b'LayerElementNormal')
    assert child(layer,b'MappingInformationType').props[0]==b'ByPolygonVertex'
    normals=np.asarray(child(layer,b'Normals').props[0]).reshape(-1,3)
    reference=child(layer,b'ReferenceInformationType').props[0]
    if reference==b'IndexToDirect':
        normals=normals[np.asarray(child(layer,b'NormalsIndex').props[0])]
    else:
        assert reference==b'Direct'
    assert len(normals)==len(indices)
    result=Counter();polygon=[]
    for index,normal in zip(indices,normals):
        vertex=-index-1 if index<0 else index
        polygon.append((tuple(coordinates[vertex]),tuple(normal)))
        if index<0:
            result[tuple(polygon)]+=1;polygon=[]
    assert not polygon
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    assert not args.output.exists()
    args.output.mkdir(parents=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    source=features.pier()
    material=bpy.data.materials.new('NormalFixture')
    original=geom.to_object(source,material)
    whole=capture(original.data)
    source_faces=[whole['vertex_indices'][start:start+count].tolist()
                  for start,count in zip(whole['starts'],whole['counts'])]
    geom.export_fbx(original,args.output/'whole.fbx')
    expected=faces(args.output/'whole.fbx')
    actual=Counter();loops=0;old_error=0.;count=0
    for name,members in pieces.groups(source.name,whole['positions'],source_faces):
        piece=subset(whole,members)
        data=create_mesh(name,piece)
        attribute=data.attributes['custom_normal']
        assert (attribute.data_type,attribute.domain,len(attribute.data))==('FLOAT_VECTOR','CORNER',len(piece['normals']))
        assert values(data.corner_normals,'vector',3).tobytes()==piece['normals'].tobytes()
        # A separate former-setter control proves this source reaches the fan-space precision gap.
        compressed=data.copy()
        compressed.attributes.remove(compressed.attributes['custom_normal'])
        compressed.normals_split_custom_set(piece['normals'].tolist())
        old_error=max(old_error,float(np.max(np.abs(values(compressed.corner_normals,'vector',3)-piece['normals']))))
        bpy.data.meshes.remove(compressed)
        obj=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(obj)
        obj.matrix_world=original.matrix_world.copy()
        path=args.output/(name+'.fbx');geom.export_fbx(obj,path)
        actual.update(faces(path));loops+=len(piece['normals']);count+=1
        bpy.data.objects.remove(obj,do_unlink=True);bpy.data.meshes.remove(data)
    assert count>1 and loops==len(whole['normals'])
    assert old_error>2e-5,('Fixture must exercise the original precision failure',old_error)
    assert actual==expected,'Expanded FBX polygon/corner positions and normals differ'
    (args.output/'result.json').write_text(json.dumps(dict(pieces=count,corners=loops,old_setter_max_error=old_error,
        bitwise_corner_normals=True,exported_face_corners_equal=True),indent=2)+'\n')
    print('PIECE NORMALS EXACT VERIFIED',flush=True)


if __name__=='__main__':
    main()
