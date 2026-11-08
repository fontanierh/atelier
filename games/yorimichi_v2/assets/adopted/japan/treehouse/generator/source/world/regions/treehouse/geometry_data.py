"""Canonical coupled Treehouse construction and fade/query data, before rendered exports."""
import argparse
from pathlib import Path
import sys
sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from atelier.mesh_cells import cell_face_groups  # noqa: E402
from atelier.model_files import regular_files  # noqa: E402
from region_mesh_parts import plan, capture_colliders
from mesh_pieces import capture  # noqa: E402
from treehouse import build  # noqa: E402

PARENTS = ('TH_Structure', 'TH_Frame', 'TH_Trunks', 'TH_Dressing')
OPTIONS = dict(apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y', axis_up='Z',
               mesh_smooth_type='FACE', use_custom_props=False, colors_type='SRGB')


def main(argv=None):
    """@cc [owner:fontanierh,label:correctness;performance] canonical-treehouse-fade-source-data
    The original seeded structural construction MUST finish before the shared
    Frame/Dressing capsule table is baked. Every original five-channel fade value,
    ordered corner/material/colour and authored world frame MUST survive capture.
    This explicit coupled source/query barrier MUST NOT export rendered meshes;
    independently consumed owner/piece packets MUST preserve unchanged bytes.
    Dressing MUST retain its original 64-metre grouping and signed child names.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--')+1:])
    root = real_directory(args.out)
    # Refuse all foreign/link destinations before reconstructing or writing geometry.
    if root.exists():
        found = {p.name for p in root.iterdir()}
        if found - {*PARENTS, 'runtime.json', 'manifest.json'}:
            raise ValueError('Foreign Treehouse source-data owner')
        for parent in PARENTS:
            real_directory(root/parent)
            if (root/parent).exists(): regular_files(root/parent)
        for name in ('runtime.json','manifest.json'):
            path=root/name
            if path.is_symlink() or (path.exists() and not path.is_file()):
                raise ValueError('Invalid Treehouse query-data member')
    meshes, materials, runtime, windows = build.construct()
    report = dict(windows=windows, props={key:len(rows) for key, rows in runtime['instances'].items()},
                  lights=len(runtime['lights']), rooms=len(runtime['rooms']))
    # All meshes are finished before the first object() bakes the shared capsule table.
    for mesh in meshes:
        obj = mesh.object(materials)
        groups = None
        if mesh.name == 'TH_Dressing':
            if mesh.colliders: raise ValueError('Dressing cannot acquire collision ownership')
            original=capture(obj.data)
            faces=[original['vertex_indices'][s:s+n].tolist() for s,n in zip(original['starts'],original['counts'])]
            groups = [(f'TH_Dressing_cell_{x}_{y}' + ('_Piece'+suffix if suffix else ''), [int(i) for i in members])
                for x,y,suffix,members in cell_face_groups(original['positions'],faces,64.,triangle_limit=32768)]
        value = plan(obj, root/mesh.name, collisions=capture_colliders(mesh.colliders),
                     options=OPTIONS, face_groups=groups,
                     partition=None if groups is not None else ('spatial' if mesh.name == 'TH_Structure' else 'whole'))
        info = dict(triangles=value['source_triangles'], vertices=len(mesh.vertices), slots=sorted(set(mesh.kinds)),
                    collision_boxes=len(mesh.colliders), min=[round(float(v),3) for v in value['pieces'][0]['min']],
                    max=[round(float(v),3) for v in value['pieces'][0]['max']],
                    render_pieces=[row['name'] for row in value['pieces']])
        import numpy as np
        points = np.asarray(mesh.vertices)
        info.update(min=points.min(0).round(3).tolist(), max=points.max(0).round(3).tolist())
        if mesh.baked: info['piece_bake'] = mesh.baked
        report[mesh.name] = info
        print('TREEHOUSE CANONICAL SOURCE', mesh.name, value['source_triangles'], len(value['pieces']), flush=True)
    atomic_json(root/'runtime.json', runtime)
    atomic_json(root/'manifest.json', report)
    print('TREEHOUSE SOURCE DATA COMPLETE', flush=True)


if __name__ == '__main__': main()
