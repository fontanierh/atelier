"""Write a playable character's registration record, Content/Data/<id>/character.json, after its pawn exists.

FPlayableCharacter::Scan (CharacterRoster.cpp) registers the character from this file. Its fields and bytes
are character_pawn.py's: the declaration computes them from the committed character.toml, and this step runs
only once the BP_<Name> Item it names has been produced by the native author unit.
"""
import argparse
import json
import os
import tempfile
from atelier.atomic_files import managed_temporary_parent
from pathlib import Path

FIELDS = ('name', 'id', 'class', 'definition', 'build_step', 'default', 'aliases')
MAGIC = b'\xc1\x83\x2a\x9e'


def record(text):
    value = json.loads(text)
    if not isinstance(value, dict) or tuple(value) != FIELDS:
        raise ValueError('Registration record fields differ from character_pawn.py')
    if (not all(isinstance(value[key], str) and value[key] for key in FIELDS[:5])
            or type(value['default']) is not bool
            or not isinstance(value['aliases'], list) or not all(isinstance(a, str) for a in value['aliases'])
            or not value['class'].endswith('_C')):
        raise ValueError('Invalid registration record')
    return value


def write(value, blueprint, output):
    """@cc [owner:fontanierh,label:correctness] c3-character-registration
    The record MUST be written only when its produced Blueprint package is present,
    with character_pawn.py's exact fields and encoding, whole or absent.
    """
    blueprint = Path(blueprint)
    if blueprint.is_symlink() or not blueprint.is_file() or blueprint.read_bytes()[:4] != MAGIC:
        raise ValueError('Registration requires the produced Blueprint package')
    package = value['class'].split('.', 1)[0]
    if blueprint.name != package.rsplit('/', 1)[1] + '.uasset':
        raise ValueError('Registration record names another Blueprint')
    output = Path(output)
    if output.name != 'character.json' or output.parent.name != value['id']:
        raise ValueError('Registration record path differs from Content/Data/<id>/character.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='character-', suffix='.json', dir=managed_temporary_parent(output))
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            stream.write(json.dumps(value, indent=1) + '\n')
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--record', required=True)
    parser.add_argument('--blueprint', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    value = record(args.record)
    write(value, args.blueprint, args.output)
    print(f'CHARACTER REGISTRATION COMPLETE: {value["id"]} {value["class"]}')


if __name__ == '__main__':
    main()
