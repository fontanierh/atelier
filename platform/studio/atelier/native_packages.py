"""A successful native save must leave its actual primary package on disk."""
from pathlib import Path
import re


def save(asset, editor, content_root):
    """@cc [owner:fontanierh,label:correctness] saved-native-primary-required
    A save MUST report success and leave a regular primary file under the declared Content
    root. In-memory registry membership alone MUST NOT prove a saved package. Foreign,
    escaping and linked destinations MUST refuse; the caller must still inventory sidecars.
    """
    name = asset.get_path_name()
    match = re.fullmatch(r'/Game/((?:[A-Za-z0-9_]+/)*([A-Za-z0-9_]+))\.([A-Za-z0-9_]+)', name)
    if match is None or match[2] != match[3]:
        raise RuntimeError('Invalid owned native asset path: '+str(name))
    path = Path(content_root).absolute() / (match[1]+'.uasset')
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise RuntimeError('Linked native package destination')
    if not editor.save_loaded_asset(asset, only_if_is_dirty=False):
        raise RuntimeError('Native package save failed: '+name)
    if any(part.is_symlink() for part in (path, *path.parents)) or not path.is_file():
        raise RuntimeError('Native save did not produce a regular primary package: '+name)
    return path
