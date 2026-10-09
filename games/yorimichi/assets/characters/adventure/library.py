"""The committed motion reference, sword and paraglider used by the merged move set.

The reference rig contains a small marker mesh and the animation skeleton, never a playable character.
All inputs live in source/; builds need no external character library or personal cache.
"""
import json
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROSTER = HERE / 'roster.toml'
SOURCE = HERE / 'source'


def root():
    return SOURCE


def mechanics():
    return SOURCE / 'mechanics.json'


def available():
    return (SOURCE / 'manifest.json').is_file()


def roster():
    return tomllib.loads(ROSTER.read_text())


def entry(entry_id):
    item = json.loads((SOURCE / 'manifest.json').read_text())['entries'][entry_id]
    return {**item, 'id': entry_id, 'glb': SOURCE / item['glb'],
            'curves': SOURCE / item['curves'] if item.get('curves') else None}


def sources():
    return sorted(path for path in SOURCE.iterdir() if path.is_file()) if available() else []
