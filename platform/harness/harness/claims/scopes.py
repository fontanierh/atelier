"""Claim item normalization and the overlap rules.

A claim holds items of three kinds:

* ``scope``: a hierarchical logical ID such as ``region/north/harbour``, ``asset/prop/bench-01``,
  ``shared/material/M_Sea`` or ``boundary/north+south``. A scope overlaps its ancestors and descendants;
  siblings coexist. Different top-level kinds never overlap, so a region claim does not own a shared scope.
* ``path``: one exact repository path.
* ``prefix``: a directory prefix (always ending in ``/``) that covers files whose names do not exist yet.

Paths and prefixes overlap when equal or when one contains the other. Comparison is case-insensitive so a
case-only difference (which a case-insensitive checkout cannot represent) counts as the same file.
"""
import posixpath
import re

KINDS = ('region', 'asset', 'shared', 'boundary')
_SEGMENT = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]*$')


class InvalidItem(ValueError):
    pass


def scope(value):
    if not isinstance(value, str):
        raise InvalidItem(f'scope must be a string: {value!r}')
    parts = value.strip().split('/')
    if len(parts) < 2 or parts[0] not in KINDS:
        raise InvalidItem(f'scope {value!r} must start with one of {", ".join(KINDS)} and name something')
    if parts[0] == 'boundary':
        if len(parts) != 2 or parts[1].count('+') != 1:
            raise InvalidItem(f'boundary scope {value!r} must be boundary/<a>+<b>')
        sides = parts[1].split('+')
        if not all(_SEGMENT.match(side) for side in sides) or sides[0].casefold() == sides[1].casefold():
            raise InvalidItem(f'boundary scope {value!r} needs two different names')
        return 'boundary/' + '+'.join(sorted(sides, key=str.casefold))
    if not all(_SEGMENT.match(part) for part in parts[1:]):
        raise InvalidItem(f'scope {value!r} has an empty or invalid segment')
    return '/'.join(parts)


def path(value):
    if not isinstance(value, str) or not value or '\\' in value or '\0' in value:
        raise InvalidItem(f'path must be a non-empty POSIX repository path: {value!r}')
    if value.startswith('/') or value.endswith('/'):
        raise InvalidItem(f'path {value!r} must be repository-relative and name a file')
    normal = posixpath.normpath(value)
    if normal != value or normal == '.' or normal.split('/')[0] == '..':
        raise InvalidItem(f'path {value!r} must be normalized (no ., .. or repeated /)')
    return normal


def prefix(value):
    if not isinstance(value, str) or not value.endswith('/'):
        raise InvalidItem(f'prefix {value!r} must end in /')
    return path(value[:-1]) + '/'


NORMALIZE = {'scope': scope, 'path': path, 'prefix': prefix}


def overlaps(a, b):
    """True when two (kind, value) items cannot be owned by two different claims at once."""
    (ka, va), (kb, vb) = a, b
    va, vb = va.casefold(), vb.casefold()
    if (ka == 'scope') != (kb == 'scope'):
        return False
    if ka == 'scope':
        sa, sb = va.split('/'), vb.split('/')
        n = min(len(sa), len(sb))
        return sa[:n] == sb[:n]
    if ka == 'path' and kb == 'path':
        return va == vb
    if ka == 'prefix' and kb == 'prefix':
        return va.startswith(vb) or vb.startswith(va)
    p, d = (va, vb) if ka == 'path' else (vb, va)
    return p.startswith(d)


def covers(items, repo_path):
    """Whether a claim's path/prefix items cover one changed repository path."""
    target = repo_path.casefold()
    for kind, value in items:
        value = value.casefold()
        if kind == 'path' and value == target or kind == 'prefix' and target.startswith(value):
            return True
    return False
