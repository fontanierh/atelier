"""Blender-only ship constructor control; frozen authority is prepared by the outer host.

This diagnostic proves source mesh/query equality only. It does not certify exported FBX,
saved native packages, cooked surfaces, runtime components or traversal.
No subprocess, Git helper or native launcher may run inside this process.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME / 'world'))
import yori  # noqa: E402,F401
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from mesh_pieces import capture  # noqa: E402
from regions.ferry.ship_sources import BUILDERS, project  # noqa: E402


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def checked(record):
    path = Path(record['path'])
    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != record['sha256']:
        raise ValueError('Frozen ship authority changed')
    return path


def signature(obj):
    data = capture(obj.data)
    def plain(value):
        if isinstance(value, np.ndarray):
            return dict(dtype=value.dtype.str, shape=list(value.shape), bytes=value.tobytes().hex())
        if isinstance(value, (list, tuple)):
            return [plain(row) for row in value]
        if isinstance(value, dict):
            return {key: plain(row) for key, row in value.items()}
        return value
    data['slots'] = [material.name for material in data['slots']]
    data['matrix'] = [list(row) for row in obj.matrix_world]
    payload = json.dumps(plain(data), sort_keys=True, separators=(',', ':')).encode()
    return dict(sha256=hashlib.sha256(payload).hexdigest(), polygons=len(obj.data.polygons),
                triangles=sum(len(face.vertices) - 2 for face in obj.data.polygons),
                corners=len(obj.data.loops), slots=data['slots'],
                channels={key: hashlib.sha256(json.dumps(plain(value), sort_keys=True).encode()).hexdigest()
                          for key, value in data.items()})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authority', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    authority = json.loads(args.authority.read_text())
    paths = {key: checked(row) for key, row in authority['files'].items()}
    bpy.ops.wm.read_factory_settings(use_empty=True)
    baseline_solid = load('solid_mesh', paths['original_solid'])
    sys.modules['solid_mesh'] = baseline_solid
    original = load('ferry_immutable_original', paths['original_build'])
    materials = original.make_materials()
    before, raw = {}, {}
    for key, builder in BUILDERS.items():
        mesh = original.Mesh(key); getattr(original, builder)(mesh)
        original.check(mesh)  # the original gate also reverses inward authored parts
        obj, _ = original.to_object(mesh, materials)
        before[key] = signature(obj)
        raw[key] = dict(vertices=mesh.verts, faces=mesh.faces,
                        seats=list(original.SEATS), blocks=list(original.BLOCKS), boat_faces=list(original.BOAT_FACES))
        print('IMMUTABLE SHIP SOURCE', key, before[key]['triangles'], flush=True)
    expected_proxies = original.collision_proxies()
    expected_seats, expected_hits = original.seating_check({key: type('MeshQuery', (),
        dict(verts=data['vertices'], faces=data['faces'])) for key, data in raw.items()})
    current_solid = load('solid_mesh', paths['current_solid']); sys.modules['solid_mesh'] = current_solid
    planner = load('ferry_selected_planner_control', GAME / 'world/regions/ferry/plan_ship.py')
    audit = load('ferry_selected_audit_control', GAME / 'world/regions/ferry/ship_audit.py')
    selected = project(paths['current_build'].read_text())
    actual, values = {}, {}
    for key in BUILDERS:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        obj, value = planner.construct(key, selected[key])
        actual[key] = signature(obj)
        if actual[key] != before[key]:
            atomic_json(args.output, dict(complete=False, asset=key, baseline=before[key], selected=actual[key]))
            raise ValueError('Selected ship corner/frame/material equality failed: ' + key + ' ' +
                ','.join(field for field in before[key]['channels'] if before[key]['channels'][field] != actual[key]['channels'][field]))
        value.update(triangles=actual[key]['triangles'],
            min=[round(min(v[i] for v in value['vertices']), 3) for i in range(3)],
            max=[round(max(v[i] for v in value['vertices']), 3) for i in range(3)])
        values[key] = value
        print('SELECTED SHIP SOURCE EXACT', key, actual[key]['triangles'], flush=True)
    result = audit.audit(selected['audit']['program'], values)
    if result['proxies'] != expected_proxies:
        raise ValueError('Original whole authored ship proxies changed')
    for row in authority['files'].values(): checked(row)
    atomic_json(args.output, dict(schema=1, complete=True, coverage='source_mesh_and_queries_only',
        authority=authority, baseline=before, selected=actual, proxies=len(expected_proxies),
        original_seats=len(expected_seats), original_overlaps=expected_hits, original_deck_audit=result['deck_audit']))
    print('FERRY SHIP SOURCE CONTROL COMPLETE', flush=True)


if __name__ == '__main__': main()
