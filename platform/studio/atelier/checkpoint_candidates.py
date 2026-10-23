"""Typed native-candidate scopes and prior native evidence.

Donor ranking and staging are retired: a step's result comes back only from its own action
entry, saved under its exact input key, or the step runs. The scope type stays for recipes, and
prior evidence for batch finalization.
"""
from dataclasses import dataclass
import os
import re

from .native_candidates import task_name
from .build_cache import atomic_json
from .checkpoint_store import CheckpointError, safe_destination


@dataclass(frozen=True)
class CandidateScope:
    files: tuple = ()
    directories: tuple = ()
    donor_task: str | None = None


def save_prior(ctx, task, nonce, stamp):
    """Non-success historical evidence; the caller still invalidates its actual build stamp."""
    if not stamp:
        return None
    task_name(task)
    if not re.fullmatch('[0-9a-f]{24}', nonce) or not isinstance(stamp, dict):
        raise CheckpointError('Invalid prior native evidence owner or invocation')
    path = safe_destination(ctx.out, '.state/mesh-import-prior/' + task + '/' + nonce + '.json')
    if os.path.lexists(path):
        raise CheckpointError('Prior native invocation evidence already exists')
    atomic_json(path, dict(schema=1, task=task, nonce=nonce, stamp=stamp,
                           observed_context=getattr(ctx, 'checkpoint_observed_context', None)))
    return path
