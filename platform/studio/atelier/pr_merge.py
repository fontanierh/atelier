"""Retain the producer's existing work before merging; never build to manufacture a warm cache."""
import json
from pathlib import Path
import threading

from . import build_checkpoints, paths
from .checkpoint_store import CheckpointError
from .pr_media import remote_repository
from .release import GitHub


def merge(pr, *, source=None, echo=print):
    """@cc [owner:fontanierh,label:correctness] cache-before-pr-merge
    A PR merge MUST retain the selected completed producer's existing artifacts locally first.
    Retention failure MUST prevent the merge. A checkout with no built artifacts MUST NOT be
    built to satisfy retention. The merge MUST require green exact-head Studio Python CI and
    bind the GitHub merge to that same head, without changing or cleaning the producer checkout.
    Independent review remains a required agent guideline; this command MUST NOT claim it ran.
    """
    repository = '/'.join(remote_repository('origin', paths.REPO))
    github = GitHub(repository, threading.Event())
    def inspect():
        return json.loads(github.run(['pr', 'view', str(pr), '--repo', repository,
                                      '--json', 'url,state,isDraft,headRefOid,statusCheckRollup']))
    info = inspect()
    if info.get('state') not in ('OPEN', 'MERGED') or info.get('isDraft'):
        raise CheckpointError('Only a ready open or already merged PR can retain artifacts and merge')
    head = info.get('headRefOid', '')
    if len(head) != 40 or not all(c in '0123456789abcdef' for c in head):
        raise CheckpointError('Cannot determine the PR head to merge')
    def require_ci(value):
        checks = [c for c in value.get('statusCheckRollup', []) if c.get('name') == 'Studio Python / macOS']
        if not checks or any(c.get('status') != 'COMPLETED' or c.get('conclusion') != 'SUCCESS' for c in checks):
            raise CheckpointError('Studio Python / macOS must pass on the exact PR head before merging')
    if info['state'] == 'OPEN':
        require_ci(info)
    retained = build_checkpoints.retain(Path(source).resolve() if source else paths.REPO, echo=echo)
    # Retention can queue or copy for a while; never merge a different revision afterward.
    latest = inspect()
    if latest.get('headRefOid') != head:
        raise CheckpointError('PR head changed during artifact retention; recheck CI and independent review')
    if latest.get('state') == 'MERGED':
        echo('PR already merged; existing producer artifacts retained locally')
    else:
        if latest.get('state') != 'OPEN' or latest.get('isDraft'):
            raise CheckpointError('PR is no longer ready to merge; local checkpoints retained')
        require_ci(latest)
        github.run(['pr', 'merge', str(pr), '--repo', repository, '--squash', '--match-head-commit', head], timeout=120)
        final = inspect()
        echo(('Merged ' if final.get('state') == 'MERGED' else 'Merge requested; confirm completion: ') + info['url'])
    echo(f'{len(retained)} local build checkpoint(s) retained; no build or cook requested')
    return 0
