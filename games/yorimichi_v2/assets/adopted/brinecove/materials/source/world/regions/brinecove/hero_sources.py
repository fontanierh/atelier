"""The committed hero models the production export ships, checked before export.

Every Brinecove model the source library lists must be present, match the library's checksum and match its own
provenance record's output checksum. The production export fails on any gap instead of falling back to the
procedural stand-ins the authoring viewer keeps for unfinished assets. Plain Python.
"""
import hashlib
import json

from brinecove.paths import ASSETS, MODELS
from source_registry import models as selected_models

LIBRARY = ASSETS.parent / 'source-library.json'
PREFIX = 'brinecove/models/'


def verify(library=LIBRARY, models=MODELS):
    """{slug: path} of every listed model, or ValueError naming each missing or altered one."""
    files = selected_models(library, PREFIX)
    listed = {key[len(PREFIX):-len('.glb')]: entry for key, entry in files.items()
              if key.startswith(PREFIX) and key.endswith('.glb')}
    if not listed:
        raise ValueError(f'{library.name} lists no Brinecove models')
    problems, found = [], {}
    for slug, entry in sorted(listed.items()):
        path, record = models / f'{slug}.glb', models / f'{slug}.provenance.json'
        if not path.exists():
            problems.append(f'{slug}.glb is missing')
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry['sha256']:
            problems.append(f'{slug}.glb differs from {library.name}')
        elif not record.exists():
            problems.append(f'{slug}.provenance.json is missing')
        elif json.loads(record.read_text()).get('output_sha256') != digest:
            problems.append(f'{slug}.glb differs from its provenance record')
        else:
            found[slug] = path
    if problems:
        raise ValueError('Brinecove hero models: ' + '; '.join(problems))
    return found
