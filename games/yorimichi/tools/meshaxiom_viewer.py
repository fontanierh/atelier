"""Stage a generated mesh in the local multi-asset viewer; serve only this build directory.

No model weights, repository root or credentials are copied. Tailscale may proxy a loopback
static HTTP server at this directory; hosting configuration stays outside the public repo.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil

REPO = Path(__file__).resolve().parents[3]
WEB = Path(__file__).with_suffix('')
VENDOR = WEB.with_name('character_review_web') / 'vendor'


def atomic_write(path, data):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_bytes(data)
    temporary.replace(path)


def stage(args):
    """@cc [owner:fontanierh,label:correctness] meshaxiom-viewer-source-geometry
    The viewer MUST display the supplied generated positions/connectivity without remeshing,
    and its downloadable GLB MUST be a byte-identical copy of the supplied export. Only explicit
    public inputs and the pinned local web/vendor files MAY enter the staged site.
    """
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,39}', args.asset):
        raise ValueError('Use a simple lowercase asset slug')
    output = args.output.resolve()
    if not output.is_relative_to((REPO / 'build/yorimichi').resolve()):
        raise ValueError('Stage the viewer beneath build/yorimichi')
    raw = args.mesh.read_bytes()
    if args.mesh.suffix == '.gz':
        raw = gzip.decompress(raw)
    mesh = json.loads(raw)
    if not mesh.get('vertices') or not mesh.get('faces'):
        raise ValueError('Provide completed generated mesh geometry')
    public = {'mesh.json': raw, 'reference.png': args.reference.read_bytes()}
    if args.model:
        public['model.glb'] = args.model.read_bytes()
    if args.render_glb and not args.model:
        raise ValueError('GLB rendering requires the supplied export')
    record = dict(id=args.asset, title=args.title, palette=args.palette, note=args.note,
                  triangles=len(mesh['faces']), vertices=len(mesh['vertices']),
                  seconds=None, peak_gib=None, render_glb=args.render_glb,
                  defer_topology=bool(args.render_glb and len(mesh['faces']) > 200000))
    if args.benchmark:
        benchmark = json.loads(args.benchmark.read_text())
        if (benchmark['vertex_count'] != len(mesh['vertices']) or benchmark['face_count'] != len(mesh['faces'])
                or benchmark['input_sha256'] != hashlib.sha256(public['reference.png']).hexdigest()):
            raise ValueError('Benchmark counts/reference do not match these viewer inputs')
        record['seconds'] = benchmark['total_worker_seconds']
        record['peak_gib'] = max(g['peak_bytes'] for g in benchmark['guards'].values()) / 1024**3
    record['sha256'] = {name: hashlib.sha256(data).hexdigest() for name, data in public.items()}
    prefix = f'assets/{args.asset}/'
    record.update(mesh=prefix+'mesh.json', reference=prefix+'reference.png',
                  model=prefix+'model.glb' if args.model else None)
    catalog_path = output / 'catalog.json'
    catalog = json.loads(catalog_path.read_text()) if catalog_path.exists() else {'assets': []}
    catalog['assets'] = [record, *(r for r in catalog['assets'] if r['id'] != args.asset)]
    target = output / 'assets' / args.asset
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(VENDOR, output/'vendor', dirs_exist_ok=True)
    for name in ('index.html', 'app.js', 'style.css'):
        atomic_write(output/name, (WEB/name).read_bytes())
    for name, data in public.items():
        atomic_write(target/name, data)
    atomic_write(catalog_path, (json.dumps(catalog, indent=2)+'\n').encode())
    print(f"Viewer staged {args.asset}: {record['triangles']:,} triangles; {len(catalog['assets'])} models", flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--asset', required=True)
    p.add_argument('--title', required=True)
    p.add_argument('--mesh', type=Path, required=True)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--model', type=Path)
    p.add_argument('--render-glb', action='store_true', help='Display the actual exported materials and texture')
    p.add_argument('--benchmark', type=Path)
    p.add_argument('--palette', choices=['bin', 'cart', 'clay'], default='clay')
    p.add_argument('--note', default='MeshAxiom geometry. Inspect the wireframe for open surfaces and broken faces.')
    p.add_argument('--output', type=Path, default=REPO/'build/yorimichi/meshaxiom/viewer')
    stage(p.parse_args())


if __name__ == '__main__':
    main()
