"""Pin the upstream review action's transitive actions without maintaining a fork of its code."""
import hashlib
from pathlib import Path
import re
import sys


# .github/actions/contract-review/action.yml at spolu/code-contracts commit
# 6d1b1a945d1fe02a43bac567341b77ccfdf3ae33. Update the revision, hash and reviewed pins together.
SOURCE_SHA256 = '25deeb8f8b39a747e1c466721b23a4a11cee59f4fc1ff5c69701d554a018bb72'
CODEX_VERSION = '0.162.1'
ACTION_PINS = {
    'actions/github-script@v7': 'actions/github-script@f28e40c7f34bde8b3046d885e986cb6290c5673b',
    'actions/checkout@v5': 'actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09',
    'actions/setup-node@v4': 'actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020',
    'openai/codex-action@v1': 'openai/codex-action@1d82a3dba7c7988ec71ecae1ed5b8e8db96495c5',
}


def prepare(action):
    """@cc [owner:fontanierh,label:security] immutable-review-toolchain
    Only the reviewed upstream action bytes may be adapted. Every referenced action and the Codex
    CLI/proxy version MUST be pinned before use. Checker dependency installation MUST disable lifecycle scripts.
    """
    action = Path(action)
    original = action.read_bytes()
    if hashlib.sha256(original).hexdigest() != SOURCE_SHA256:
        raise ValueError('Upstream review action differs from the reviewed revision')
    source = original.decode()
    for before, after in ACTION_PINS.items():
        if before not in source:
            raise ValueError(f'Missing expected upstream action: {before}')
        source = source.replace(before, after)
    source = source.replace('        npm ci\n', '        npm ci --ignore-scripts\n')
    effort = '        effort: ${{ inputs.effort }}\n'
    if effort not in source or 'npm ci --ignore-scripts' not in source:
        raise ValueError('Upstream tool installation or model configuration changed')
    source = source.replace(effort, effort + f'        codex-version: {CODEX_VERSION}\n')
    for action_ref in re.findall(r'^\s*uses:\s*(\S+)', source, re.MULTILINE):
        if not re.fullmatch(r'[\w/-]+@[0-9a-f]{40}', action_ref):
            raise ValueError(f'Unpinned transitive action: {action_ref}')
    action.write_text(source)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python -m atelier.contract_review_tools ACTION_YML')
    prepare(sys.argv[1])
