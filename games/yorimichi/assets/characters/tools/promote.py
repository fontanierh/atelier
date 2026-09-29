"""Promote an approved character revision from the archive into this repository.

    python games/yorimichi/assets/characters/tools/promote.py warm-original $YORIMICHI_ARCHIVE/output/imagegen/yorimichi-yellow-boy-2026-09-12/game-r18

Copies the revision's .blend (textures packed) and its JSON records over the character's folder, removes the previous
revision's .blend, and updates `revision` and `source` in character.toml. The build notices the new source and
re-exports and re-imports the character. Commit the result.
"""
import re, shutil, sys
from pathlib import Path

CHARACTERS = Path(__file__).resolve().parents[1]


def promote(character, revision_folder):
    target = CHARACTERS / character
    source = Path(revision_folder).resolve()
    manifest = target / 'character.toml'
    if not manifest.exists():
        raise SystemExit(f'no character {character!r} in {CHARACTERS}')
    blends = sorted(source.glob('*.blend'))
    if len(blends) != 1:
        raise SystemExit(f'expected exactly one .blend in {source}, found {[b.name for b in blends]}')
    for old in target.glob('*.blend'):
        old.unlink()
    shutil.copy2(blends[0], target / blends[0].name)
    records = [p for p in source.glob('*.json')] + [p for p in source.glob('README.md')]
    for record in records:
        shutil.copy2(record, target / record.name)
    text = manifest.read_text()
    text = re.sub(r'^revision = "[^"]*"', f'revision = "{source.name}"', text, flags=re.M)
    text = re.sub(r'^source = "[^"]*"', f'source = "{blends[0].name}"', text, flags=re.M)
    manifest.write_text(text)
    print(f'{character}: now {source.name} ({blends[0].name}, {len(records)} records). Run `atelier build yorimichi`, then commit.')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    promote(sys.argv[1], sys.argv[2])
