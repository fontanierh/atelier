"""Patch playable character materials; shared world materials have their own owner."""
import sys
from pathlib import Path
import unreal
import see_through as cut

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'assets/characters/pipeline'))
import definition


def main():
    cut.collection()  # read only; fail before modifying characters if its owner is incomplete
    changed = []
    for character in map(definition.load, definition.ids()):
        prefixes = tuple(character.toml.get('see_through', ()))
        if not prefixes:
            continue
        for path in sorted(cut.E.list_assets(character.unreal_path, recursive=False)):
            name = path.rsplit('/', 1)[-1].split('.')[0]
            if not name.startswith(prefixes):
                continue
            material = cut.E.load_asset(path)
            if isinstance(material, unreal.Material) and cut.character(material):
                if not cut.save(material):
                    raise RuntimeError('See-through material failed to compile: ' + path)
                changed.append(name)
    unreal.log(f'SEE-THROUGH COMPLETE: {len(changed)} character materials')


if __name__ == '__main__':
    main()
