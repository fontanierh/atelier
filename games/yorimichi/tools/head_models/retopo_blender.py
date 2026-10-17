"""Blender worker: QuadriFlow on a separately reconstructed manifold head copy."""
import argparse
import json
from pathlib import Path
import sys
import time

import bpy
import bmesh
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from retopo import checked_mesh, digest, fresh, progress


def topology(bm):
    return dict(vertices=len(bm.verts), faces=len(bm.faces),
                nonmanifold_edges=sum(len(e.link_faces) > 2 for e in bm.edges),
                boundary_edges=sum(e.is_boundary for e in bm.edges),
                wire_edges=sum(not e.link_faces for e in bm.edges),
                short_edges=sum(max(abs(c) for c in e.verts[0].co-e.verts[1].co) < 1e-4 for e in bm.edges),
                inconsistent_edges=sum(e.is_manifold and not e.is_contiguous for e in bm.edges))


def main():
    """@cc [owner:fontanierh,label:correctness] quad-head-is-a-derived-copy
    Remeshing MUST write a separate derived mesh and retain the source checkpoint.
    Solver rejection or missing output MUST fail, even if Blender itself exits zero.
    The reported quad/triangle counts MUST describe the actual exported mesh.
    """
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--quads', type=int, required=True)
    args = p.parse_args(sys.argv[sys.argv.index('--')+1:])
    fresh(args.output)
    before = digest(args.source)
    started = time.monotonic()
    with np.load(args.source, allow_pickle=False) as source:
        v, f = checked_mesh(source['vertices'], source['faces'])
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    mesh = bpy.data.meshes.new('TRELLIS_reconstructed_working_copy')
    with progress(f'Loading {len(f):,} reconstructed triangles into Blender'):
        mesh.from_pydata(v.tolist(), [], f.tolist())
        mesh.update()
    obj = bpy.data.objects.new('TRELLIS_derived_quad_head', mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    with progress('Checking solver topology and normal orientation'):
        bm = bmesh.new()
        bm.from_mesh(mesh)
        loose = [e for e in bm.edges if not e.link_faces]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context='EDGES')
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        # QuadriFlow's Blender preflight uses an absolute 1e-4 edge tolerance.
        # Scale only solver coordinates and divide back before exporting.
        for vertex in bm.verts:
            vertex.co *= 1000
        preflight = topology(bm)
        print('Solver preflight:', json.dumps(preflight), flush=True)
        if any(preflight[k] for k in ('nonmanifold_edges', 'wire_edges', 'short_edges', 'inconsistent_edges')):
            raise ValueError('Working surface does not meet QuadriFlow preconditions')
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()
    with progress(f'QuadriFlow target {args.quads:,} quads, deterministic seed 42'):
        result = bpy.ops.object.quadriflow_remesh(use_mesh_symmetry=False,
            use_preserve_sharp=False, use_preserve_boundary=True, smooth_normals=True,
            mode='FACES', target_faces=args.quads, seed=42)
    if result != {'FINISHED'}:
        raise ValueError(f'QuadriFlow rejected the working mesh: {result}')
    mesh = obj.data
    for vertex in mesh.vertices:
        vertex.co /= 1000
    mesh.update()
    bpy.ops.object.shade_smooth()
    mesh.calc_loop_triangles()
    positions = np.empty(len(mesh.vertices)*3, dtype='<f4')
    mesh.vertices.foreach_get('co', positions)
    positions = positions.reshape(-1, 3)
    triangles = np.array([tuple(t.vertices) for t in mesh.loop_triangles], dtype='<u4')
    quads = [tuple(face.vertices) for face in mesh.polygons if len(face.vertices) == 4]
    positions, triangles = checked_mesh(positions, triangles)
    bm = bmesh.new()
    bm.from_mesh(mesh)
    output_topology = topology(bm)
    bm.free()
    np.savez_compressed(args.output/'mesh.npz', vertices=positions, faces=triangles,
                        quads=np.asarray(quads, dtype='<u4'))
    bpy.ops.wm.save_as_mainfile(filepath=str((args.output/'retopology.blend').resolve()))
    if digest(args.source) != before:
        raise ValueError('Remeshing changed the retained source')
    report = dict(source_sha256=before, output_sha256=digest(args.output/'mesh.npz'),
                  method='QuadriFlow on reconstructed surface; no manual edits',
                  blender=bpy.app.version_string, seed=42, target_quads=args.quads,
                  quads=len(quads), polygons=len(mesh.polygons), triangles=len(triangles),
                  vertices=len(positions), preflight=preflight, topology=output_topology,
                  seconds=time.monotonic()-started,
                  limitation='Automatic quad flow does not guarantee facial deformation loops')
    (args.output/'remesh.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
