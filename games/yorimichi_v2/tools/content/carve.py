"""Carved sources: a record whose remainder is derived from its committed fused original and a committed selection.

A carved tile (tools/migrate/brinecove_split_apply.py, brinecove_market.py) cuts objects out of a fused donor mesh. The
record keeps the fused original as its first pinned source (the bytes tools/migrate/recover.py produced), and a
selection file that lists which of the original's triangles the remainder keeps. The remainder is never committed.
The targeted import derives it under build/yorimichi_v2/derived/<record>/ (materialize, called only by the import's
preparation), and the import fingerprint covers the original's and the selection's hashes.

    asset.toml   [[sources]] src/SM_BC_X.glb         the fused original (pinned)
                 [[sources]] src/SM_BC_X.carve.json  the selection (pinned)
                 [derive] kind = "carve", version = 1, original, selection
    selection    {"schema": 1, "triangles": N, "kept": [[a, b], ...], "removed": [[a, b], ...]}
                 half-open ranges of triangle ordinals, in the order glb_subset.triangles yields them

The remainder is glb_subset.subset_glb of the original with the kept ordinals, except that a selection keeping every
triangle is the original's own bytes. Standard library only (with glb_subset), so every check runs from a checkout.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from glb_subset import parse_glb, subset_glb, triangles

SCHEMA = 1
DERIVE_KIND, DERIVE_VERSION = 'carve', 1
DERIVED = 'derived'            # build/yorimichi_v2/derived/<record id>/<original name>: the import's own file


class CarveError(ValueError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def selection_name(original_name: str) -> str:
    """SM_BC_X.glb -> SM_BC_X.carve.json: the selection file that sits beside the original."""
    return original_name.removesuffix('.glb') + '.carve.json'


def ranges(ordinals: list[int]) -> list[list[int]]:
    """Ascending, unique ordinals as half-open [start, end) ranges."""
    out: list[list[int]] = []
    for n in ordinals:
        if out and out[-1][1] == n:
            out[-1][1] = n + 1
        else:
            out.append([n, n + 1])
    return out


def selection_text(total: int, kept: list[int]) -> str:
    """The reviewable selection file: what the remainder keeps and what it removes, both as ranges of ordinals."""
    kept = sorted(set(kept))
    if kept and (kept[0] < 0 or kept[-1] >= total):
        raise CarveError(f'kept ordinal outside 0..{total - 1}')
    keep = set(kept)
    removed = [n for n in range(total) if n not in keep]
    body = {'schema': SCHEMA, 'triangles': total,
            'about': 'Which triangles of the fused original the remainder keeps (kept) and removes (removed), as half-open '
                     'ranges of triangle ordinals in glb_subset.triangles order. tools/content/carve.py derives the remainder.',
            'kept': ranges(kept), 'removed': ranges(removed)}
    return json.dumps(body, indent=2, sort_keys=True) + '\n'


def _ordinals(name: str, value, total: int) -> list[int]:
    if not isinstance(value, list):
        raise CarveError(f'selection {name} must be a list of [start, end) ranges')
    out, last = [], 0
    for pair in value:
        if not (isinstance(pair, list) and len(pair) == 2 and all(isinstance(v, int) for v in pair)):
            raise CarveError(f'selection {name}: {pair!r} is not a [start, end) range')
        start, end = pair
        if not (last <= start < end <= total):
            raise CarveError(f'selection {name}: range {pair} is out of order or outside 0..{total}')
        out += range(start, end)
        last = end
    return out


def load_selection(data: bytes) -> tuple[int, list[int]]:
    """(triangles, kept ordinals) of a selection file; refuses one whose kept and removed ranges do not partition 0..N."""
    try:
        body = json.loads(data)
    except ValueError as error:
        raise CarveError(f'selection is not JSON: {error}') from None
    if not isinstance(body, dict) or body.get('schema') != SCHEMA or not isinstance(body.get('triangles'), int):
        raise CarveError(f'selection needs schema {SCHEMA} and an integer triangles count')
    total = body['triangles']
    kept = _ordinals('kept', body.get('kept'), total)
    removed = _ordinals('removed', body.get('removed'), total)
    if sorted(kept + removed) != list(range(total)):
        raise CarveError('selection kept and removed ranges do not partition the triangles')
    return total, kept


def triangle_count(model: dict) -> int:
    return sum(1 for _ in triangles(model))


def remainder_bytes(original: bytes, name: str, kept: list[int], total: int) -> bytes:
    """The remainder's bytes from the original's bytes: the original itself when every triangle is kept."""
    if kept == list(range(total)):
        return original
    model = parse_glb(original, name)
    if triangle_count(model) != total:
        raise CarveError(f'{name} has {triangle_count(model)} triangles, the selection says {total}')
    return subset_glb(model, kept, Path(name).stem)[0]


def derive(folder: Path, derive_table: dict) -> bytes:
    """The remainder bytes of a record folder: its original and selection, read from the folder, nothing written."""
    original = (folder / derive_table['original']).read_bytes()
    total, kept = load_selection((folder / derive_table['selection']).read_bytes())
    return remainder_bytes(original, Path(derive_table['original']).name, kept, total)


def remainder_model(folder: Path, derive_table: dict) -> dict:
    """The derived remainder as a parsed model (for the placement and partition checks)."""
    return parse_glb(derive(folder, derive_table), Path(derive_table['original']).name)


def materialize(asset, build_root: Path) -> Path:
    """Write the derived remainder under build_root/derived/<record>/ for the import (deterministic path, rewritten
    only when its bytes differ). Called by the targeted import's preparation, never by a normal build."""
    if asset.derive is None:
        raise CarveError(f'{asset.id} is not a carved record')
    data = derive(asset.folder, asset.derive)
    out = build_root / DERIVED / asset.id / Path(asset.derive['original']).name
    if not (out.is_file() and sha256(out.read_bytes()) == sha256(data)):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
    return out


def plan_sources(asset, build_root: Path) -> list[Path]:
    """The files the importer reads for an asset: its sources, or the derived remainder for a carved record."""
    if asset.derive is None:
        return [asset.folder / s.path for s in asset.sources]
    return [materialize(asset, build_root)]


def derive_table(original: str, selection: str) -> str:
    """The [derive] table of asset.toml (game-record relative paths)."""
    return (f'[derive]\nkind = "{DERIVE_KIND}"\nversion = {DERIVE_VERSION}\noriginal = "{original}"\n'
            f'selection = "{selection}"\n')


def with_derive(text: str, original: str, selection: str) -> str:
    """asset.toml text with the [derive] table placed before [recipe] (exactly one [recipe] in the text)."""
    marker = '\n\n[recipe]\n'
    if text.count(marker) != 1:
        raise CarveError('asset.toml has no single [recipe] table to place [derive] before')
    return text.replace(marker, '\n\n' + derive_table(original, selection) + '\n[recipe]\n', 1)


def triangle_keys(model: dict) -> list[tuple]:
    """One key per triangle, in triangles() order: material name and each corner's position, normal and UV. Two
    triangles with equal keys are the same triangle for every byte write_subset emits."""
    keys = []
    for prim in model['prims']:
        name = model['materials'][prim['material']] if prim['material'] >= 0 else ''
        pos, idx = prim['positions'], prim['indices']
        normal, uv = prim.get('NORMAL'), prim.get('TEXCOORD_0')
        for i in range(0, len(idx) - 2, 3):
            corners = tuple((pos[idx[i + j]], normal[idx[i + j]] if normal else None,
                             uv[idx[i + j]] if uv else None) for j in range(3))
            keys.append((name, corners))
    return keys
