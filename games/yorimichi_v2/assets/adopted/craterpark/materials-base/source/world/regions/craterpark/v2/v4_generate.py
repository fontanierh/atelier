"""Compile an explicit v4 design into the existing NPZ/FBX pipeline; no legacy layout fallback."""
import argparse
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parents[2]))

import numpy as np  # noqa: E402
from craterpark.v2 import dsl, generate, v4_config  # noqa: E402


def validator_ground(resolved, bounds=None):
    """Convert the resolved [z,x] height field to the validator's [x,z] uniform grid."""
    from craterpark.v2 import validate
    terrain = resolved.terrain
    x, z = np.asarray(terrain.x, 'f8'), np.asarray(terrain.z, 'f8')
    height = np.asarray(terrain.heights, 'f8')
    if len(x) < 2 or len(z) < 2 or height.shape != (len(z), len(x)):
        raise ValueError('v4 validation requires a finite terrain grid')
    step = float(x[1] - x[0])
    if step <= 0 or not np.allclose(np.diff(x), step) or not np.allclose(np.diff(z), step):
        raise ValueError('v4 terrain grid must have equal positive x/z spacing')
    if bounds is not None:
        lo, hi = np.asarray(bounds, 'f8')[:, [0, 2]]
        if np.any(lo < [x[0], z[0]]) or np.any(hi > [x[-1], z[-1]]):
            raise ValueError('v4 geometry leaves the terrain grid; extrapolation is forbidden')
        ix0 = max(0, int(np.searchsorted(x, lo[0], side='right')) - 1)
        iz0 = max(0, int(np.searchsorted(z, lo[1], side='right')) - 1)
        ix1 = min(len(x), int(np.searchsorted(x, hi[0])) + 2)
        iz1 = min(len(z), int(np.searchsorted(z, hi[1])) + 2)
        height = height[iz0:iz1, ix0:ix1]
        x, z = x[ix0:ix1], z[iz0:iz1]
    if not np.isfinite(height).all():
        raise ValueError('v4 terrain is invalid inside the geometry bounds')
    return validate.Ground(float(x[0]), float(z[0]), step, height.T)


def run_validators(park, out, ground):
    """@cc [owner:fontanierh] v4-structural-validation
    Preview MUST only admit named cosmetic failures.
    Missing or failing structural validation MUST fail generation, including preview mode.
    """
    from craterpark.v2 import validate
    if ground is None:
        raise ValueError('v4 validation requires terrain')
    path = Path(out) / 'validation.json'
    report, ok = validate.validate_park(park, path, ground=ground)
    from craterpark.v2 import v4_supports
    specs = [c for c in getattr(park, 'checks', ()) if c.get('kind') == 'v4_support']
    support_result = {'ok': True, 'support_count': 0, 'envelope_count': 0}
    if specs:
        try:
            envelopes, coverage = v4_supports.derive_envelopes(park.mesh, park.checks)
            support_result = v4_supports.check(park.mesh, park.checks, envelopes=envelopes,
                                               envelope_coverage=coverage)
        except v4_supports.SupportError as error:
            support_result = {'ok': False, 'failures': [{'kind': 'unresolved_support', 'detail': str(error)}]}
    elif any(name.endswith('.support') for name in getattr(getattr(park, 'mesh', None), 'features', ())):
        support_result = {'ok': False, 'failures': [{'kind': 'undeclared_support_geometry'}]}
    # The current rail primitive merges posts and the bar into one feature.
    # Until it emits actual post bodies and bearing interfaces, tower clearance
    # alone cannot certify those additional supports.
    rainbows=[c['feature'] for c in getattr(park,'checks',()) if c.get('kind')=='v4_rainbow']
    if rainbows:
        support_result['ok']=False
        support_result.setdefault('failures',[]).append(
            {'kind':'unresolved_rainbow_post_supports','features':rainbows})
    report['checks']['supports'] = support_result
    report['ok'] = ok = bool(ok and support_result['ok'])
    report['failed'] = [name for name, result in report['checks'].items() if not result.get('ok', True)]
    path.write_text(json.dumps(report, indent=1) + '\n')
    acceptance = {'ran': True, 'ok': bool(support_result['ok']), 'support_count': len(specs)}
    if ok:
        return {'ran': True, 'ok': True, 'supports': acceptance}
    failed = sorted(name for name, result in report.get('checks', {}).items()
                    if isinstance(result, dict) and not result.get('ok', True))
    if failed and all(name in generate.COSMETIC for name in failed) and (Path(out) / generate.PREVIEW).exists():
        report.update(ok=False, preview=True, cosmetic_failures=failed)
        path.write_text(json.dumps(report, indent=1) + '\n')
        print(f'PREVIEW BUILD: cosmetic failures in {", ".join(failed)}; validation remains false', flush=True)
        return {'ran': True, 'ok': False, 'preview': True, 'failed': failed, 'supports': acceptance}
    raise ValueError(f'Crater Park v4 validation failed ({", ".join(failed) or "unknown failure"}); see {path}')


def main(argv=None):
    import yori
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--design', default=None)
    parser.add_argument('--out', default=str(yori.OUT / 'craterpark' / 'v2'))
    args = parser.parse_args(argv)
    if args.design:
        os.environ[v4_config.SWITCH] = str(Path(args.design).expanduser().resolve())
    if not v4_config.selected():
        parser.error('--design or ATELIER_CRATERPARK_V4_DESIGN is required')
    from craterpark import placement
    from craterpark.v2 import ao, dressing, export, spawns, v4_design, v4_layout
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    # A failed new compile must never leave a successful old artifact available for export.
    for name in ('geometry.npz', 'geometry-report.json'):
        (out / name).unlink(missing_ok=True)
    start = time.monotonic()
    provenance = v4_config.provenance()
    print('CRATERPARK V4 resolving design and terrain', flush=True)
    resolved = v4_design.load_design(v4_config.design_path())
    print('CRATERPARK V4 compiling design segments', flush=True)
    park = v4_layout.compile_design(resolved)
    if not isinstance(park, dsl.Park) or not park.lines:
        raise ValueError('v4 compiler must return a Park with checked tower starts')
    terrain = validator_ground(resolved, [park.mesh.V.min(0), park.mesh.V.max(0)])
    generate.declare_scenery(park)
    labels = {line['id']: line.get('name', line['id']) for line in resolved.lines}
    lines = spawns.entries(park.mesh, park.lines, placement, deck_y=spawns.TOWER,
                           labels=labels, checks=park.checks)
    dressing.check(park.mesh, placement)
    trees = dressing.plant(park.mesh, airs=park.checks)
    print('CRATERPARK V4 baking occlusion and validating structure', flush=True)
    ao.bake_mesh(park.mesh, drawn=(dsl.RIDING, dsl.SIDE, dsl.GROUND, dsl.COPING, dsl.RAIL))
    # A diagnostic artifact is intentionally rejected by export.write even if renamed.
    diagnostic_arrays, diagnostic_index = generate.bundle(park, lines, trees)
    diagnostic_index.update(v4=provenance, bounds_native=[park.mesh.V.min(0).tolist(), park.mesh.V.max(0).tolist()],
                            accepted=False)
    diagnostic_arrays['index'] = np.asarray(json.dumps(diagnostic_index))
    np.savez(out / 'unaccepted-geometry.npz', **diagnostic_arrays)
    validation = run_validators(park, out, terrain)
    if v4_config.provenance() != provenance:
        raise ValueError('v4 inputs changed during generation; rerun with stable inputs')
    arrays, index = diagnostic_arrays, diagnostic_index
    index['v4'] = provenance
    index['validation'] = validation
    index['accepted'] = True
    index['bounds_native'] = [park.mesh.V.min(0).tolist(), park.mesh.V.max(0).tolist()]
    arrays['index'] = np.asarray(json.dumps(index))
    (out / 'lines').mkdir(exist_ok=True)
    for stale in (out / 'lines').glob('*.npz'):
        stale.unlink()
    for line in park.lines:
        if Path(line.name).name != line.name or line.name in ('.', '..'):
            raise ValueError('line name must be a filename component')
        export.line_npz(park.mesh, line, out / 'lines' / f'{line.name}.npz')
    rep = generate.report(park, index, time.monotonic() - start)
    rep.update(layout='v4', v4=provenance, validation=validation,
               bounds_native=[park.mesh.V.min(0).tolist(), park.mesh.V.max(0).tolist()])
    temporary = out / 'geometry.tmp.npz'
    np.savez(temporary, **arrays)
    import hashlib
    rep['geometry_sha256'] = hashlib.sha256(temporary.read_bytes()).hexdigest()
    if v4_config.provenance() != provenance:
        temporary.unlink(missing_ok=True)
        raise ValueError('v4 inputs changed while writing geometry; refusing to publish mixed artifacts')
    (out / 'geometry-report.json').write_text(json.dumps(rep, indent=1) + '\n')
    temporary.replace(out / 'geometry.npz')
    print('CRATERPARK V4 GEOMETRY COMPLETE', rep['render_triangles'], 'render',
          rep['collision_triangles'], 'collision', flush=True)


if __name__ == '__main__':
    main()
