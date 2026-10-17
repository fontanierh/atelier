"""Export native TRELLIS colors with a standard unlit material; retain every binary byte."""
from pathlib import Path
import argparse
import copy
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from meshaxiom_pixel_match import digest, load_module
from meshaxiom_quality import VENDOR, write


def unlit_document(document):
    """@cc [owner:fontanierh,label:correctness] unlit-retains-native-data
    Unlit export MUST change only the material extension and extensionsUsed.
    All scene/geometry bindings and existing material values MUST remain identical.
    The caller MUST additionally verify that the complete GLB binary is unchanged.
    """
    if document.get('extensionsUsed') or len(document.get('materials', [])) != 1:
        raise ValueError('Expected an unextended native vertex-color material')
    if document['materials'][0].get('extensions'):
        raise ValueError('Unexpected existing material extension')
    result = copy.deepcopy(document)
    result['extensionsUsed'] = ['KHR_materials_unlit']
    result['materials'][0]['extensions'] = {'KHR_materials_unlit': {}}
    restored = copy.deepcopy(result)
    del restored['extensionsUsed']; del restored['materials'][0]['extensions']
    if restored != document:
        raise ValueError('Material conversion changed protected metadata')
    return result


def worker(args):
    from vertex_photo import native_arrays
    from vertex_bake import render_existing
    started = time.monotonic(); args.output.mkdir(parents=True, exist_ok=True)
    target = args.output/'head.glb'
    if target.exists(): raise ValueError('Completed material trial exists')
    pm = load_module(VENDOR); before = digest(args.model)
    original, payload = pm._split_glb(args.model.read_bytes())
    positions, _, _, faces, _ = native_arrays(original, payload)
    document = unlit_document(original)
    target.write_bytes(pm._join_glb(document, payload))
    checked, binary = pm._split_glb(target.read_bytes())
    if checked != document or binary != payload or digest(args.model) != before:
        raise ValueError('Unlit export changed native data or source')
    write(args.output/'material-report.json', dict(method='Standard KHR_materials_unlit over native learned vertex RGB',
        worker_sha256=digest(Path(__file__)), input_sha256=before, output_sha256=digest(target),
        reference_sha256=digest(args.image), vertices=len(positions), triangles=len(faces),
        complete_binary_identical=True, scene_geometry_bindings_identical=True,
        positions_normals_indices_colors_unchanged=True,
        limitations='Unlit appearance preview. Raw lit normal grain remains in the retained lit model; no geometry or normal repair.',
        seconds=round(time.monotonic()-started, 3)))
    del positions, faces, payload, binary
    args.model = target; args.yaw_offset = -90
    render_existing(args)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('model', 'image', 'output', 'report'): p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--memory-gib', type=int, choices=range(4, 11), default=8)
    p.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = p.parse_args(argv)
    if args.worker: return worker(args)
    if args.report.exists(): p.error('Use a fresh guard report')
    from atelier.harness.safety.guarded import run
    forwarded = sys.argv[1:] if argv is None else list(argv)
    return run([sys.executable, '-u', str(Path(__file__).resolve()), *forwarded, '--worker'], args.report,
        timeout=600, purpose='Native unlit material export and eight matched views',
        limit_gib=args.memory_gib, aggregate_tree=True, progress=20)


if __name__ == '__main__': sys.exit(main())
