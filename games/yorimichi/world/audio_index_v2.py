"""Record the exact completed native audio roster without scanning generated folders."""
import json
from pathlib import Path
import re


def write_index(families, destination):
    """@cc [owner:fontanierh,label:correctness] completed-audio-roster
    Every row MUST come from a resolved finished-wave token and its original package
    pattern. The index MUST NOT discover files, import assets or certify missing waves.
    The engine's actual Item edges establish completion before this body executes.
    """
    packages = []
    for name, family in sorted(families.items()):
        if set(family) != {'destination', 'members'} or not family['members']:
            raise ValueError('audio cue has no completed finished waves: ' + name)
        pattern = family['destination']
        if not pattern.startswith('/Game/') or pattern.count('$piece') != 1:
            raise ValueError('audio cue has no exact package pattern')
        for source, piece in family['members']:
            if (not re.fullmatch('[A-Za-z][A-Za-z0-9_]*', piece)
                    or len(source.products) != 1 or len(source.products[0].paths) != 1
                    or not source.products[0].paths[0].is_dir()):
                raise ValueError('audio cue has an invalid completed member')
            packages.append(pattern.replace('$piece', piece))
    if not packages or len(set(packages)) != len(packages):
        raise ValueError('native audio roster is empty or aliases a package')
    Path(destination).write_text(json.dumps({'schema': 1, 'packages': sorted(packages)},
                                           sort_keys=True, separators=(',', ':')) + '\n')
