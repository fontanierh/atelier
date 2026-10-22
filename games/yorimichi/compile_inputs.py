"""Selected editor-build inputs, excluding agent contract prose rather than native sources."""
from pathlib import Path

from atelier import build_inputs


def files(roots):
    """@cc [owner:fontanierh,label:correctness] editor-compile-source-membership
    Every selected source/config/plugin member MUST remain a compile input except the existing
    legacy generated/documentation exclusions and files named CONTRACTS. CONTRACTS are agent
    guidance, never native build inputs; a future native reader MUST explicitly declare that file.
    Unknown extensions MUST remain covered. Membership MUST be observed anew for each selected
    fingerprint, and linked or unreadable trees MUST refuse rather than silently omit native code.
    """
    result = []

    def visit(path):
        if path.is_symlink():
            raise ValueError(f'Linked editor compile input: {path}')
        if path.is_dir():
            for child in sorted(path.iterdir()):
                if (child.name not in build_inputs.SKIP_PARTS and child.name != 'CONTRACTS'
                        and child.suffix not in build_inputs.SKIP_SUFFIXES):
                    visit(child)
        else:
            # Keep missing roots explicit, matching the old directory input's missing identity.
            result.append(path)

    for root in roots:
        visit(Path(root))
    return result
