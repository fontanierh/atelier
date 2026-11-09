"""Hidamari shops as saved objects: one placed shop per object, its geometry the type's shared meshes (no new meshes).

    uv run python games/yorimichi_v2/tools/migrate/shop_objects.py           # check: exit 1 if objects.toml has drifted
    uv run python games/yorimichi_v2/tools/migrate/shop_objects.py --write   # rewrite the HD_Shop_* splits

The donor builds each HD_Shop_NN type once, at the origin (games/yorimichi/world/regions/hidamari/build.py shop(i) and
the kit builders), and layout.py places every copy by transform (`shop_sites()`, `put()`). The V2 area patches therefore
hold instances of the type's mesh, not fused placements: a key with a single whole mesh (`shop-NN`) is one model per
object; a key the donor cut into its four 128 m quadrant meshes (`shop-NN-{0,m1}-{0,m1}`, origin-centred) is one object
whose model is all four quadrant records. Each object takes the instances at its point from every quadrant component
(UV2Migration::SplitPatchObjects, V2ScenePatch.cpp:435) and keeps the same transforms, so nothing changes in the map.

This module only writes the `split` entries of the two Hidamari objects.toml files, from the donor's placements.
"""
from __future__ import annotations

import re
import sys
import tomllib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]                  # games/yorimichi_v2
DONOR_WORLD = ROOT.parent / 'yorimichi' / 'world'           # the legacy generator (placements and types)
REGIONS = ROOT / 'world' / 'regions'
RECORDS = ROOT / 'assets' / 'prop' / 'citysurfaces'          # the recovered city pieces (recover.py)
MODEL_PREFIX = 'prop/citysurfaces/'
REGION_IDS = ('w07-hidamari-harbour', 'w07-hidamari-station')
TAGS = {'w07-hidamari-harbour': 'harbour', 'w07-hidamari-station': 'station'}
KEY = re.compile(r'HD_Shop_\d\d')
WHOLE = re.compile(r'shop-(\d\d)')
QUADRANT = re.compile(r'shop-(\d\d)-cell-(0|m1)-(0|m1)')
HEADER_OLD = '# The fused city-surface pieces (HD_Shop_* _cell_ meshes, streets, squares) stay area patches.'
HEADER_NEW = ('# HD_Shop_* placements are instances of their type (tools/migrate/shop_objects.py): one object per shop, '
              'its model the type\'s mesh.')
BLOCK = re.compile(r'(?m)^(?=\[\[objects\]\])')
SHOP_BLOCK = re.compile(r'(?m)^split = \{key = "HD_Shop_\d\d"')


def placements() -> list[tuple[str, float, float]]:
    """Every HD_Shop_NN placement of the donor layout, metres: (key, x, y), sorted by key then x then y."""
    sys.path.insert(0, str(DONOR_WORLD))
    from regions.hidamari import layout   # no mesh construction: shop_sites() is pure placement data
    rows = [(name, float(x), float(y)) for name, x, y, *_ in layout.shop_sites() if KEY.fullmatch(name)]
    return sorted(rows, key=lambda row: (row[0], row[1], row[2]))


def region_of(x: float, y: float) -> str:
    """The Hidamari region whose bounds_cm (half-open, cm) hold the point; the donor's x = 896 m split is region.toml's."""
    found = []
    for rid in REGION_IDS:
        x0, y0, x1, y1 = tomllib.loads((REGIONS / rid / 'region.toml').read_text())['bounds_cm']
        if x0 <= 100 * x < x1 and y0 <= -100 * y < y1:   # Unreal y = -100 y (inventory/world.md 1)
            found.append(rid)
    if len(found) != 1:
        raise ValueError(f'placement ({x}, {y}) lies in {found or "no"} Hidamari region')
    return found[0]


def models_for(key: str) -> list[str]:
    """The adopted record(s) holding the mesh of a shop type: its whole record, or its four quadrant records."""
    number = key[-2:]
    whole = RECORDS / f'shop-{number}'
    quadrants = sorted(p.name for p in RECORDS.glob(f'shop-{number}-*') if QUADRANT.fullmatch(p.name))
    if whole.is_dir() and not quadrants:
        return [MODEL_PREFIX + whole.name]
    if quadrants and not whole.exists() and len(quadrants) == 4:
        return [MODEL_PREFIX + name for name in quadrants]
    raise ValueError(f'{key}: expected one whole record or four quadrant records, found {quadrants or whole.name}')


def fmt(value: float) -> str:
    text = f'{value:.3f}'.rstrip('0').rstrip('.')
    return text if text not in ('-0', '') else '0'


def entries() -> dict[str, list[dict]]:
    """The HD_Shop split objects of each region, numbered per region and key in placement order (as the migration names them)."""
    result: dict[str, list[dict]] = {rid: [] for rid in REGION_IDS}
    rows = placements()
    total = Counter((region_of(x, y), key) for key, x, y in rows)
    seen: Counter = Counter()
    for key, x, y in rows:
        rid = region_of(x, y)
        seen[(rid, key)] += 1
        index = seen[(rid, key)]
        slug = key.lower().replace('_', '-')          # hd-shop-03
        result[rid].append(dict(
            id=f'object/{TAGS[rid]}/{slug}-{index:02d}',
            key=key, x=x, y=y, models=models_for(key),
            about=f'{key} {index} of {total[(rid, key)]} in {rid}, placed at ({fmt(x)}, {fmt(y)}) m'))
    return result


def block(item: dict) -> str:
    models = item['models']
    model = f'"{models[0]}"' if len(models) == 1 else '[' + ', '.join(f'"{m}"' for m in models) + ']'
    return ('[[objects]]\n'
            f'id = "{item["id"]}"\n'
            f'split = {{key = "{item["key"]}", at = [{fmt(item["x"])}, {fmt(item["y"])}]}}\n'
            f'model = {model}\n'
            f'about = "{item["about"]}"\n')


def rewritten(text: str, items: list[dict]) -> str:
    """objects.toml with its HD_Shop split blocks replaced by `items`; every other block and the header are kept."""
    head, *blocks = BLOCK.split(text)
    head = head.replace(HEADER_OLD, HEADER_NEW)
    if head.count(HEADER_NEW) != 1:
        raise ValueError('objects.toml header lacks the shop note line')
    shops = ''.join(block(item) + '\n' for item in items)
    out, placed = [head], False
    for b in blocks:   # the shop block run stays where the old one was; every other block is kept byte for byte
        if SHOP_BLOCK.search(b):
            if not placed:
                if not out[-1].endswith('\n\n'):
                    out.append('\n')
                out.append(shops)
                placed = True
            continue
        out.append(b)
    if not placed:
        out.append(shops)
    trailing = len(text) - len(text.rstrip('\n'))   # the file's own closing newlines
    return ''.join(out).rstrip('\n') + '\n' * max(trailing, 1)


def plan() -> dict[str, str]:
    """The objects.toml text each Hidamari region should have."""
    result = {}
    for rid, items in entries().items():
        path = REGIONS / rid / 'objects.toml'
        result[rid] = rewritten(path.read_text(), items)
    return result


def main(argv: list[str] | None = None) -> int:
    write = '--write' in (sys.argv[1:] if argv is None else argv)
    drift = []
    for rid, text in plan().items():
        path = REGIONS / rid / 'objects.toml'
        if path.read_text() != text:
            drift.append(rid)
            if write:
                path.write_text(text)
    if drift and not write:
        print('objects.toml is out of date for: ' + ', '.join(drift) + ' (run with --write)', file=sys.stderr)
        return 1
    print(('wrote ' if write else 'up to date: ') + ', '.join(drift or REGION_IDS))
    return 0


if __name__ == '__main__':
    sys.exit(main())
