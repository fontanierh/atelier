"""Copy the BOTW library files the game uses into ../botw-library, the committed copy that library.py reads.

    uv run python games/yorimichi/assets/characters/botw/vendor.py

Run it after a roster change (roster.toml, moves.toml, ../horses/roster.toml). It reads the full library and
botw-extract in the cache (README.md) and writes, laid out as there:

- every file the BOTW and horse rosters read (library.sources, horses/export.py sources);
- the library's catalog/archive-info.json and the asset.json of every entry they use;
- botw-extract's extended catalogs (catalog.json, clothing.json), cut down to those entries.

It replaces the whole copy, so files the rosters no longer read go.
"""
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

os.environ['ATELIER_BOTW_CACHE'] = '1'   # read the cache, not the copy being replaced
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); import library  # noqa: E402


def horses():
    spec = importlib.util.spec_from_file_location('horses_export', HERE.parent / 'horses' / 'export.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    if not library.available():
        sys.exit(f'no BOTW library in {library.root()} (README.md says how to fetch it)')
    used, garments = set(), set()
    entry, garment = library.entry, library.garment
    library.entry = lambda i: (used.add(i), entry(i))[1]
    library.garment = lambda g: (garments.add(g), garment(g))[1]
    files = set(library.sources()) | set(horses().sources())
    files.add(library.root() / 'catalog' / 'archive-info.json')
    for i in used:
        files.update(library.root().glob(f'library/*/{i}/asset.json'))
    cache = library.base().resolve()
    if library.VENDOR.exists():
        shutil.rmtree(library.VENDOR)
    for f in sorted(files):
        target = library.VENDOR / Path(f).resolve().relative_to(cache)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)
    for name, ids in (('catalog.json', used), ('clothing.json', garments)):
        data = json.loads((library.extract() / 'playground' / 'private' / name).read_text())
        data['entries'] = [item for item in data['entries'] if item['id'] in ids]
        target = library.VENDOR / 'botw-extract' / 'playground' / 'private' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=1) + '\n')
    size = sum(p.stat().st_size for p in library.VENDOR.rglob('*') if p.is_file())
    print(f'BOTW LIBRARY COPY {len(files) + 2} files, {size / 1e6:.1f} MB, {len(used)} entries, {len(garments)} garments', flush=True)


if __name__ == '__main__':
    main()
