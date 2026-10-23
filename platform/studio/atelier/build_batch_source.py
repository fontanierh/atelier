"""The executed warm-source adapter's action data, separate from batch scheduling."""
from pathlib import Path


def action(command, *, name, game, nonce, prior, blender):
    """@cc [owner:fontanierh,label:correctness] complete-batch-source-invocation
    A warm source action MUST execute its original script, arguments and declared environment.
    Ownership bindings MUST be explicit for every action. A predecessor's script environment
    MUST NOT substitute for omitted values. Paths/nonces MAY identify the current invocation;
    they MUST NOT be promoted into reusable geometry authority.
    """
    return dict(name=name, script=str(command.script), args=list(command.args) if blender else [],
                env={k: v for k, v in command.env if k != 'ATELIER_BUILD_PRIOR_STAMP'}
                | dict(ATELIER_BUILD_TASK=name, ATELIER_BUILD_GAME=game,
                       ATELIER_BUILD_SCRIPT=str(command.script), ATELIER_MESH_REUSE_NONCE=nonce)
                | ({'ATELIER_BUILD_PRIOR_STAMP': str(prior)} if prior is not None else {}))


def support():
    root = Path(__file__).parent
    return {name: root / name for name in ('build_batch_source.py', 'build_batch_worker.py')}
