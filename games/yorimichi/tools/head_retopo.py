"""Guarded, automatic TRELLIS reduction, UV mapping and surface-color cleanup.

The dense checkpoint remains the reference. Reduction creates a separate mesh;
the later UV and paint stages must preserve that reduced mesh exactly.
"""
import argparse
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[3]
WORKERS = Path(__file__).with_name('head_models')


def main(argv=None):
    """@cc [owner:fontanierh,label:safety] head-retopo-aggregate-envelope
    Every setup, reduction, Blender and bake child MUST use normal admission and
    one aggregate guard with a bounded deadline. Outputs MUST stay under the
    supplied build runtime. Shared policies, ceilings and reserves MUST NOT change.
    """
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage', choices=['setup', 'surface', 'reconstruct', 'reduce', 'remesh', 'bake', 'dense'])
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--checkpoint', type=Path)
    p.add_argument('--color-cloud', type=Path)
    p.add_argument('--source', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--blender', type=Path,
                   default=Path('/Applications/Blender.app/Contents/MacOS/Blender'))
    p.add_argument('--quads', type=int, default=15000)
    p.add_argument('--depth', type=int, choices=[8, 9], default=9)
    p.add_argument('--triangles', type=int, nargs='+', default=[40000, 100000])
    p.add_argument('--texture-size', type=int, choices=[1024, 2048, 4096], default=2048)
    p.add_argument('--neighbors', type=int, choices=[1, 8, 16, 32], default=16)
    p.add_argument('--memory-gib', type=int, choices=range(4, 11), default=8)
    p.add_argument('--timeout', type=int, default=900)
    args = p.parse_args(argv)
    root = args.root.resolve()
    if not root.is_relative_to((REPO/'build/yorimichi').resolve()):
        p.error('Runtime must stay beneath build/yorimichi')
    if args.output and not args.output.resolve().is_relative_to(root):
        p.error('Outputs must stay beneath the runtime')
    if args.report.exists():
        p.error('Use a new guard report directory')
    if not 1 <= args.timeout <= 1800 or not 1000 <= args.quads <= 100000:
        p.error('Use a 1–1800 second deadline and 1,000–100,000 target quads')
    if len(args.triangles) > 4 or any(not 1000 <= count <= 500000 for count in args.triangles):
        p.error('Use at most four triangle budgets between 1,000 and 500,000')
    if args.stage != 'setup' and args.output is None:
        p.error('This stage requires --output')
    if args.stage in ('surface', 'reconstruct', 'reduce', 'bake', 'dense') and args.checkpoint is None:
        p.error('This stage requires the native --checkpoint directory')
    if args.stage in ('reconstruct', 'remesh', 'bake', 'dense') and args.source is None:
        p.error('This stage requires --source from the preceding stage')
    script = WORKERS/'retopo.py'
    py = root/'venv/bin/python'
    forwarded = ['--root', str(root)]
    for name in ('source', 'checkpoint', 'output', 'color_cloud'):
        value = getattr(args, name)
        if value is not None:
            forwarded += ['--'+name.replace('_', '-'), str(value.resolve())]
    if args.stage in ('surface', 'reconstruct'):
        command = [str(py), '-u', str(WORKERS/'surface.py'), args.stage, *forwarded,
                   '--depth', str(args.depth), '--triangles', *map(str, args.triangles)]
    elif args.stage == 'remesh':
        command = [str(args.blender), '--background', '--threads', '3',
                   '--python-exit-code', '1', '--python', str(WORKERS/'retopo_blender.py'),
                   '--', *forwarded, '--quads', str(args.quads)]
    else:
        command = [sys.executable if args.stage == 'setup' else str(py), '-u',
                   str(script), args.stage, *forwarded,
                   '--texture-size', str(args.texture_size), '--neighbors', str(args.neighbors)]
    from atelier.harness.safety.guarded import run
    return run(command, args.report, timeout=args.timeout,
               purpose=f'Automatic head {args.stage}', limit_gib=args.memory_gib,
               aggregate_tree=True, progress=20)


if __name__ == '__main__':
    sys.exit(main())
