"""Stable plant package names shared by source production and placement assembly."""
import json
from pathlib import Path
import re


def name(prototype):
    if not re.fullmatch('[a-z]+(?:_[a-z0-9]+)*', prototype):
        raise ValueError('Invalid foliage prototype name')
    return 'SM_BC_Plant_' + ''.join(part.title() for part in prototype.split('_'))


def definitions():
    names = json.loads(Path(__file__).with_name('foliage_catalog.json').read_text())
    if (not isinstance(names, list) or not names or not all(isinstance(item, str) for item in names)
            or len(set(names)) != len(names)):
        raise ValueError('Invalid foliage model catalogue')
    for prototype in names:
        name(prototype)
    folder = Path(__file__).with_name('foliage_models')
    if {p.name for p in folder.glob('*.json')} != {prototype + '.json' for prototype in names}:
        raise ValueError('Foliage model catalogue differs from committed definitions')
    selected = [folder / (prototype + '.json') for prototype in names]
    if folder.is_symlink() or any(p.is_symlink() or not p.is_file() for p in selected):
        raise ValueError('Foliage model definitions must be regular source files')
    return selected
