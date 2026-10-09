"""Each character's merged-move-set config (assets/characters/<id>/adventure.toml), which the generic retarget
(adventure/retarget.py) and import (Scripts/import_adventure_moveset.py) read in place of per-character branches."""
import tomllib
from pathlib import Path

import pytest

CHARS = Path(__file__).resolve().parents[1] / 'assets' / 'characters'
SPECS = {p.parent.name: tomllib.loads(p.read_text()) for p in sorted(CHARS.glob('*/adventure.toml'))}
FIT = {'carry', 'push', 'tilt', 'yaw', 'mount', 'crouch'}


def pascal(character):
    return ''.join(word.title() for word in character.split('-'))


def test_the_playable_characters_have_one():
    assert {'cairo', 'modori', 'sword-trainer'} <= set(SPECS)


@pytest.mark.parametrize('character', sorted(SPECS))
def test_layout(character):
    spec = SPECS[character]
    assert (CHARS / character / 'character.toml').exists()
    assert spec['mesh'] == f'/Game/{pascal(character)}/SK_{pascal(character)}'   # the character importer names it so
    for key in ('base', 'dest', 'definition'):
        assert spec[key].startswith('/Game/'), key
    assert isinstance(spec['keep_base_actions'], bool)
    assert set(spec.get('fit', {})) <= FIT


@pytest.mark.parametrize('character', sorted(SPECS))
def test_fit(character):
    fit = SPECS[character].get('fit', {})
    for vector in fit.get('push', {}).values():
        assert len(vector) == 3 and all(isinstance(v, float) for v in vector)
    for piece in fit.get('carry', {}).values():
        assert len(piece['offset']) == 3 and isinstance(piece['pitch'], (int, float))
    assert 0. <= fit.get('mount', 0.) <= 1.
    if 'crouch' in fit:
        assert set(fit['crouch']) == {'pivot', 'yaw', 'pitch', 'out'}
        assert fit.get('yaw'), 'the crouched carry turns the pieces that `yaw` turns'


def test_one_donor():
    donors = [c for c, spec in SPECS.items() if 'donor' in spec]
    assert donors == ['cairo']
    donor = SPECS['cairo']['donor']
    assert donor['double_jump'] in donor['clips']
    assert all(action['clip'] in donor['clips'] for action in donor['actions'].values())
    assert not set(donor['clips']) & set(donor['gestures'])
    assert isinstance(donor['fps'], int) and donor['folder'].startswith('/Game/')
