"""Construct final coastal ground from explicit rim/paving data and plan bounded exports."""
import argparse
import json
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori  # noqa: E402,F401
from atelier.export_manifest import real_directory  # noqa: E402


def main(argv=None):
    """@cc [owner:fontanierh,label:correctness] coastal-final-query-triangulation
    The final query MUST use the actual post-paving, float32 finished ground and
    Blender's exported triangle diagonals, in the region's world frame exactly once.
    It MUST NOT read GLB exports, reconstruct analytic terrain, or replace nonplanar
    quads with a different fan. Every complete paving owner and final rim is required.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rim', required=True, type=Path)
    parser.add_argument('--paving', action='append', required=True, type=Path)
    parser.add_argument('--query-output', required=True, type=Path)
    parser.add_argument('--surface-output', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    from brinecove.paving_data import read_all
    from brinecove.rim_schema import read
    paving = read_all(args.paving)
    real_directory(args.rim.parent)
    if args.rim.is_symlink() or not args.rim.is_file():
        raise ValueError('Missing final coastal boundary data')
    rim, world = read(json.loads(args.rim.read_text()))
    real_directory(args.output); real_directory(args.query_output.parent)
    import bpy
    bpy.ops.wm.read_factory_settings(use_empty=True)
    from brinecove import geometry_finish as finish, ground
    from brinecove.piece_inputs import finish_parts
    from terrain_product import Mesh, save
    import region_query
    import numpy as np
    done = threading.Event(); started = time.monotonic()
    def heartbeat():
        while not done.wait(25):
            print(f'Final coast ground constructing/planning after {time.monotonic()-started:.0f}s; no complete product yet', flush=True)
    thread = threading.Thread(target=heartbeat, daemon=True); thread.start()
    try:
        source, seam = ground.build(rim, world)
        if source.normals is None:
            source.normals = finish.collar_normals(source, rim, finish.smooth_normals(source))
        value, counts, _ = finish_parts(source, 'Ground', rim, args.output, paving=paving, seam=seam,
                                       query_output=args.surface_output)
        # The final query surface comes from the actual post-paving finished pieces,
        # without reading back GLBs or substituting analytic/natural terrain.
        surface, = region_query.load(args.surface_output, owner='SM_BC_Ground', stage='final')
        if not np.array_equal(surface['matrix'], np.eye(4)):
            raise ValueError('Final coast query requires the exact local finished mesh frame')
        from brinecove import region
        query = Mesh.from_polygons(surface['positions'].astype('<f8') + np.asarray(region.ORIGIN), surface['triangles'])
        save(args.query_output, query, owner='Brinecove', stage='final', city=True)
    finally:
        done.set(); thread.join(timeout=1)
    print('FINAL COAST GROUND PLAN COMPLETE', len(value['pieces']), counts, seam, flush=True)


if __name__ == '__main__':
    main()
