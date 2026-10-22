"""Selected editor-build inputs, excluding agent contract prose rather than native sources."""
from pathlib import Path
import stat

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

    def visit(path, member=False):
        try:
            info = path.lstat()
        except FileNotFoundError:
            if member:
                raise
            # Keep missing roots explicit, matching the old directory input's missing identity.
            result.append(path)
            return
        if stat.S_ISLNK(info.st_mode):
            raise ValueError(f'Linked editor compile input: {path}')
        if stat.S_ISDIR(info.st_mode):
            for child in sorted(path.iterdir()):
                if child.name not in build_inputs.SKIP_PARTS:
                    visit(child, member=True)
        elif stat.S_ISREG(info.st_mode):
            if not member or (path.name != 'CONTRACTS' and path.suffix not in build_inputs.SKIP_SUFFIXES):
                result.append(path)
        else:
            raise ValueError(f'Non-regular editor compile input: {path}')

    for root in roots:
        visit(Path(root))
    return result
