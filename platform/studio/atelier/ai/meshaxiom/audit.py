"""Inspect completed geometry with the pinned upstream topology metrics, without loading a model."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def main():
    """@cc [owner:fontanierh,label:correctness] meshaxiom-measured-face-minimum
    The minimum MUST count unique triangles excluding repeated-index and area-degenerate faces.
    Inspection MUST NOT add faces or modify geometry to satisfy the floor. A missed floor MUST
    remain visible in the report and return exit code 2.
    """
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--minimum-faces', type=int, default=0)
    args = p.parse_args()
    if args.minimum_faces < 0:
        p.error('Minimum faces must be nonnegative')
    from .install import verify_source
    verify_source(args.root)
    sys.path.insert(0, str(args.root.resolve()/'upstream/src'))
    from meshaxiom.vendor.recipe.mesh_utils90 import mesh_stats
    import numpy as np
    path = args.output/'mesh.json'
    raw = path.read_bytes()
    data = json.loads(raw)
    vertices = np.asarray(data['vertices'], dtype=np.float64)
    faces = np.asarray(data['faces'])
    if (vertices.ndim != 2 or vertices.shape[1] != 3 or not len(vertices)
            or not np.isfinite(vertices).all() or faces.ndim != 2 or faces.shape[1] != 3
            or not len(faces) or not np.issubdtype(faces.dtype, np.integer)
            or faces.min() < 0 or faces.max() >= len(vertices)):
        raise ValueError('Mesh must contain finite vertices and valid triangle indices')
    stats = mesh_stats(vertices, faces)
    # The upstream metrics canonicalize duplicate/repeated-index triangles. Area-degenerate
    # triangles must also be excluded when judging a requested minimum count.
    usable = stats['faces'] - stats.get('degenerate_faces', 0)
    report = dict(source_mesh_sha256=hashlib.sha256(raw).hexdigest(), raw_faces=len(faces),
                  minimum_faces=args.minimum_faces, usable_faces=usable,
                  meets_minimum_faces=usable >= args.minimum_faces, metrics=stats,
                  geometry_changes='none; inspection only',
                  acceptance='Counts and topology metrics are not a visual or rigging approval')
    (args.output/'mesh-audit.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report['meets_minimum_faces'] else 2


if __name__ == '__main__':
    sys.exit(main())
