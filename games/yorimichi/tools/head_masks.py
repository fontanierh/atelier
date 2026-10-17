"""Guarded automatic SAM2 skin/hair masks and texture-only repainting."""
import argparse
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[3]
WORKER = Path(__file__).with_name('head_models')/'masks.py'


def main(argv=None):
    """@cc [owner:fontanierh,label:safety] head-mask-whole-tree-envelope
    Setup, view preparation, model inference and UV projection MUST use normal
    admission and one aggregate guard per stage, including child downloads.
    Runtime and output paths MUST remain under the supplied build runtime.
    """
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage', choices=['setup', 'views', 'infer', 'project'])
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--source', type=Path, help='Baked mesh-uv.npz')
    p.add_argument('--model', type=Path, help='Matching baked head.glb')
    p.add_argument('--views', type=Path, help='Prepared or inferred view directory')
    p.add_argument('--color-cloud', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--device', choices=['auto', 'cpu', 'mps'], default='auto')
    p.add_argument('--paint-mode', choices=['repair', 'full'], default='repair')
    p.add_argument('--hair-palette', choices=['navy', 'grey'], default='navy')
    p.add_argument('--memory-gib', type=int, choices=range(4, 11), default=8)
    p.add_argument('--timeout', type=int, default=900)
    args = p.parse_args(argv)
    root = args.root.resolve()
    if not root.is_relative_to((REPO/'build/yorimichi').resolve()):
        p.error('Runtime must stay beneath build/yorimichi')
    if args.output and not args.output.resolve().is_relative_to(root):
        p.error('Output must stay beneath runtime')
    if args.report.exists() or not 1 <= args.timeout <= 1800:
        p.error('Use a fresh guard report and a 1–1800 second deadline')
    if args.stage != 'setup' and args.output is None:
        p.error('This stage requires --output')
    if args.stage in ('views', 'project') and (args.source is None or args.model is None):
        p.error('This stage requires matching --source and --model')
    if args.stage in ('infer', 'project') and args.views is None:
        p.error('This stage requires --views')
    if args.stage == 'project' and args.color_cloud is None:
        p.error('Repainting requires the source --color-cloud')
    py = sys.executable if args.stage == 'setup' else str(root/('sam-venv' if args.stage == 'infer' else 'venv')/'bin/python')
    command = [py, '-u', str(WORKER), args.stage, '--root', str(root), '--device', args.device,
               '--paint-mode', args.paint_mode, '--hair-palette', args.hair_palette]
    for name in ('source', 'model', 'views', 'color_cloud', 'output'):
        value = getattr(args, name)
        if value is not None:
            command += ['--'+name.replace('_', '-'), str(value.resolve())]
    from atelier.harness.safety.guarded import run
    return run(command, args.report, timeout=args.timeout, limit_gib=args.memory_gib,
               purpose=f'Automated head masks {args.stage}', aggregate_tree=True, progress=20)


if __name__ == '__main__':
    sys.exit(main())
