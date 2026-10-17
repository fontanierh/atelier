"""Guard one MeshAxiom stage with an explicitly selected session memory ceiling.

The default is 10 GiB. A larger ceiling, up to 16 GiB, is for experiments explicitly
authorized by the machine owner. Shared capacity profiles and host reserves never change.
"""
import argparse
import copy
from pathlib import Path
import sys


def admission_for(command, report, timeout, purpose, memory_gib):
    """@cc [owner:fontanierh,label:safety] meshaxiom-explicit-session-envelope
    A selected larger ceiling MUST reserve that entire ceiling for both unified memory and
    GPU use through the existing broker. The session MUST retain the configured checkout,
    locks, endpoint, compatibility binding and exclusive CPU reservation. Shared profiles,
    host reserves, admission and actual-child/tree guards MUST NOT be weakened or edited.
    """
    if not 10 <= memory_gib <= 16:
        raise ValueError('MeshAxiom session memory must be 10–16 GiB')
    if memory_gib == 10:
        return None  # The normal guard constructs its unchanged automatic session.
    from atelier.harness.capacity_runtime import configured_session
    from atelier.harness.capacity_client import AdmissionSession
    baseline = configured_session(kind='job', limit_gib=10, timeout=timeout, folder=report,
                                  purpose=purpose, command=command, performance=True)
    if baseline is None:
        raise ValueError('Larger MeshAxiom sessions require a full-capacity broker; use the normal 10 GiB ceiling')
    if baseline.mode != 'capacity':
        raise ValueError('Larger MeshAxiom sessions require normal full-capacity mode')
    request = copy.deepcopy(baseline.request)
    mib = memory_gib * 1024
    request['resources']['memory_mib'] = max(request['resources']['memory_mib'], mib)
    request['resources']['gpu_mib'] = max(request['resources']['gpu_mib'], mib)
    return AdmissionSession(baseline.socket_path, request, timeout=baseline.timeout,
                            cutover=baseline.cutover, mode=baseline.mode)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--image', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--stage', choices=['vertex', 'topology'], required=True)
    p.add_argument('--face-budget', type=int, default=2000)
    p.add_argument('--steps', type=int, default=20)
    p.add_argument('--max-nodes', type=int, default=8192)
    p.add_argument('--memory-gib', type=int, choices=range(10, 17), default=10)
    p.add_argument('--timeout', type=int, default=3600)
    args = p.parse_args()
    if not (1 <= args.face_budget <= 30000 and 1 <= args.steps <= 40
            and 1 <= args.max_nodes <= 26000 and 1 <= args.timeout <= 7200):
        p.error('Invalid face/step/node bounds or stage deadline (1–7200 seconds)')
    if args.report.exists():
        p.error('Use a new guard report directory for each attempt')
    command = [str(args.root.resolve()/'venv/bin/python'), '-u', '-m',
               'atelier.ai.meshaxiom.worker', '--root', str(args.root.resolve()),
               '--image', str(args.image.resolve()), '--output', str(args.output.resolve()),
               '--stage', args.stage, '--face-budget', str(args.face_budget),
               '--steps', str(args.steps), '--max-nodes', str(args.max_nodes)]
    purpose = f'MeshAxiom {args.stage}, {args.face_budget} faces, owner-selected {args.memory_gib} GiB cap'
    session = admission_for(command, args.report, args.timeout, purpose, args.memory_gib)
    from atelier.harness.safety.guarded import run
    print(purpose, flush=True)
    return run(command, args.report, timeout=args.timeout, purpose=purpose,
               limit_gib=args.memory_gib, admission=session, aggregate_tree=True, progress=25)


if __name__ == '__main__':
    sys.exit(main())
