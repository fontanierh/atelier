"""Independent tree copies used by the product transfer protocol."""
import os
import shutil


def copy_tree(source, target, source_repo, target_repo, clone):
    if not source.exists() and not source.is_symlink():
        return
    if source.is_dir() and not source.is_symlink():
        target.mkdir(parents=True, exist_ok=True)
        for item in source.iterdir():
            copy_tree(item, target / item.name, source_repo, target_repo, clone)
        shutil.copystat(source, target)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        target.unlink()
    if source.is_symlink():
        link = os.readlink(source)
        if link.startswith(str(source_repo) + '/'):
            link = str(target_repo) + link[len(str(source_repo)):]
        target.symlink_to(link)
    elif clone is not None and clone(os.fsencode(source), os.fsencode(target), 0) == 0:
        shutil.copystat(source, target)
    else:
        shutil.copy2(source, target)
