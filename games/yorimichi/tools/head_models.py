"""Guarded Apple Silicon model setup, pinned download and native head experiments.

Examples and measured recipes are in docs/MESHAXIOM_HEAD_QUALITY.md.
Worker-specific arguments follow --. Model payloads remain beneath build/yorimichi.
"""
import argparse
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[3]
WORKERS = Path(__file__).with_suffix('')


def main(argv=None):
    """@cc [owner:fontanierh,label:safety] local-head-aggregate-envelope
    Every setup, download or inference child MUST run under one aggregate guard and
    normal admission. Ceilings above10GiB MUST reserve the whole selected envelope
    through the existing MeshAxiom admission adapter. Shared policies MUST NOT change.
    """
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('backend', choices=['native', 'trellis'])
    p.add_argument('stage', choices=['setup', 'download', 'generate', 'compare'])
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--memory-gib', type=int, choices=range(4, 17), default=10)
    p.add_argument('--timeout', type=int, default=3600)
    # Parse outer options explicitly; worker options are separated by --.
    supplied = list(sys.argv[1:] if argv is None else argv)
    separator = supplied.index('--') if '--' in supplied else len(supplied)
    args = p.parse_args(supplied[:separator])
    forwarded = supplied[separator+1:]
    if any(item == '--root' or item.startswith('--root=') for item in forwarded):
        p.error('Set the runtime root on the guarded outer command only')
    if args.stage not in ('generate', 'compare') and forwarded:
        p.error('Only generate and compare accept worker arguments after --')
    if not 1 <= args.timeout <= 7200:
        p.error('Deadline must be1–7200 seconds')
    if not args.root.resolve().is_relative_to((REPO/'build/yorimichi').resolve()):
        p.error('Model runtime must stay beneath build/yorimichi')
    if args.report.exists():
        p.error('Use a new report directory for every attempt')
    runtime = args.root.resolve()
    py = runtime/('pixal-venv' if args.backend == 'native' else 'mlx-venv')/'bin/python'
    if args.stage == 'setup':
        command = [sys.executable, '-u', str(WORKERS/'setup_runtime.py'),
                   '--root', str(runtime), '--backend', args.backend]
    elif args.stage == 'download':
        command = [str(py), '-u', str(WORKERS/'download.py'),
                   '--root', str(runtime), '--backend', args.backend]
    elif args.stage == 'compare':
        command = [str(py), '-u', str(WORKERS/'compare.py'), '--root', str(runtime), *forwarded]
    else:
        command = [str(py), '-u', str(WORKERS/(args.backend+'_worker.py')),
                   '--root', str(runtime), *forwarded]
    from atelier.harness.safety.guarded import run
    from atelier.ai.meshaxiom.guarded import admission_for
    purpose = f'Local head {args.backend} {args.stage}, {args.memory_gib}GiB aggregate cap'
    session = admission_for(command, args.report, args.timeout, purpose, args.memory_gib) if args.memory_gib > 10 else None
    return run(command, args.report, timeout=args.timeout, purpose=purpose,
               limit_gib=args.memory_gib, admission=session, aggregate_tree=True, progress=20)


if __name__ == '__main__':
    sys.exit(main())
