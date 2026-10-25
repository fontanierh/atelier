"""Record completion of the explicitly selected native owners in each declared family."""
import hashlib
import json
from pathlib import Path
import re


def write_index(families, fixed, destination):
    """@cc [owner:fontanierh,label:correctness] complete-native-family-items
    Every mesh MUST come from a resolved finished-follower Item with its original
    declared package path and actual primary file. Fixed packages MUST have explicit
    producer edges before execution. No generated namespace discovery, old importer
    verification or native parent retirement MAY run in this completion consumer.
    """
    assets = list(fixed)
    meshes = {}
    for parent, family in sorted(families.items()):
        if set(family) != {'destination', 'members'} or not family['members']:
            raise ValueError('Native parent has no completed native members: ' + parent)
        pattern = family['destination']
        if not pattern.startswith('/Game/') or pattern.count('$piece') not in (0, 1):
            raise ValueError('Native parent has no exact finished destination')
        for source, piece in family['members']:
            if '$piece' not in pattern and piece != parent:
                raise ValueError('Fixed native output requires its single declared whole member')
            if (not re.fullmatch('[A-Za-z][A-Za-z0-9_]*', piece)
                    or len(source.products) != 1 or len(source.products[0].paths) != 1):
                raise ValueError('Invalid completed native member')
            root = Path(source.products[0].paths[0])
            package = pattern.replace('$piece', piece)
            primary = root / ('content/Game/' + package.removeprefix('/Game/') + '.uasset')
            if (not root.is_dir() or root.is_symlink() or root.resolve() != root
                    or primary.is_symlink() or not primary.is_file()
                    or primary.resolve() != primary or primary.stat().st_nlink != 1):
                raise ValueError('Completed native family Item lacks its actual primary package')
            if package in meshes:
                raise ValueError('Native membership aliases a package')
            meshes[package] = {'parent': parent, 'sha256': hashlib.sha256(primary.read_bytes()).hexdigest()}
            assets.append(package)
    if not meshes or len(set(assets)) != len(assets) or any(
            not isinstance(package, str) or not package.startswith('/Game/') for package in assets):
        raise ValueError('Completed native roster is empty or ambiguous')
    Path(destination).write_text(json.dumps({'schema': 2, 'assets': sorted(assets), 'meshes': meshes},
                                          sort_keys=True, separators=(',', ':')) + '\n')
