"""Packages an Unreal run saved, read from its own log: evidence that an import stayed inside its owned outputs."""
import re
from pathlib import Path

SAVED = re.compile(r"LogSavePackage: Moving '[^']*' to '([^']+)'")


def saved(log_path, content):
    """Content-relative paths of every package the run saved into `content` (the project's Content folder)."""
    content = Path(content)
    marker = '/' + content.parent.name + '/' + content.name + '/'
    log_path = Path(log_path)
    text = log_path.read_text(errors='ignore') if log_path.is_file() else ''
    return sorted({destination.replace('\\', '/').split(marker, 1)[1]
                   for destination in SAVED.findall(text) if marker in destination.replace('\\', '/')})


def foreign(log_path, content):
    """Saved package files that lie outside the project's Content folder."""
    content = Path(content)
    marker = '/' + content.parent.name + '/' + content.name + '/'
    log_path = Path(log_path)
    text = log_path.read_text(errors='ignore') if log_path.is_file() else ''
    return sorted({d.replace('\\', '/') for d in SAVED.findall(text) if marker not in d.replace('\\', '/')})


def outside(log_path, content, roots):
    """Saved packages that no declared output root covers."""
    content, roots = Path(content), [Path(root) for root in roots]
    return [relative for relative in saved(log_path, content)
            if not any(content / relative == root or root in (content / relative).parents for root in roots)]
