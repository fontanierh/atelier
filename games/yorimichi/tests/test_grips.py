"""The grip poser's committed saves (assets/characters/grips/<character>/, docs/GRIPS.md): game.py rebuilds from them
the grips.json committed beside them, which the characters.<character>_grips step writes for the game."""
import argparse
import importlib.util
import json
from pathlib import Path

import pytest

GRIPS = Path(__file__).resolve().parents[1] / 'assets' / 'characters' / 'grips'
CHARACTERS = sorted(p.parent.name for p in GRIPS.glob('*/poses.json'))


def game():
    spec = importlib.util.spec_from_file_location('grips_game', GRIPS / 'game.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_modori_is_committed():
    assert 'modori' in CHARACTERS


@pytest.mark.parametrize('character', CHARACTERS)
def test_game_rebuilds_the_committed_grips(character, tmp_path, monkeypatch):
    module = game()
    monkeypatch.setattr(module.yori, 'GAME', tmp_path)
    monkeypatch.setattr(module.yori, 'REPO', tmp_path)
    module.main(argparse.Namespace(character=character, source=GRIPS / character))
    built = json.loads((tmp_path / 'unreal' / 'Content' / 'Data' / character / 'grips.json').read_text())
    assert built == json.loads((GRIPS / character / 'grips.json').read_text())
    assert 'by' not in (built['source']['saved'] or {})   # a saver's login stays out of the game's data
