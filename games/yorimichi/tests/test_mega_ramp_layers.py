"""A change to the mini-mega's shape rebuilds the ramp and the map, never the terrain or the world import."""
from pathlib import Path
from types import SimpleNamespace

from atelier import build

MEGA = Path(__file__).resolve().parents[1] / 'world' / 'regions' / 'mega'


def changed_by(edited, tmp_path, monkeypatch):
    """Steps whose fingerprint changes when `edited` changes. Inputs hash by name, and an input that is or contains
    `edited` hashes differently afterwards, so the test reads the recipe's dependencies and needs no built files."""
    def stand_in(digest, path):
        inside = str(path) == str(edited) or str(edited).startswith(f'{path}/')
        digest.update(str(path).encode() + (b'edited' if inside else b''))
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path, logs=tmp_path/'logs', stamps=tmp_path/'stamps', uproject=None)
    steps = build.load_recipe('yorimichi').steps(ctx)

    def prints():
        done = {}
        for step in steps:
            done[step.name] = build.fingerprint(step, done)
        return done
    monkeypatch.setattr(build, '_hash_path', lambda digest, path: digest.update(str(path).encode()))
    before = prints()
    monkeypatch.setattr(build, '_hash_path', stand_in)
    after = prints()
    return {name for name in before if before[name] != after[name]}


def test_ramp_shape_rebuilds_only_the_ramp_and_the_map(tmp_path, monkeypatch):
    assert changed_by(MEGA/'ramp.py', tmp_path, monkeypatch) == {'world.mega', 'world.map', 'unreal.mega', 'data.stage'}


def test_ramp_place_still_reshapes_the_terrain(tmp_path, monkeypatch):
    changed = changed_by(MEGA/'layout.py', tmp_path, monkeypatch)
    assert {'world.layout', 'world.terrain', 'world.mega', 'world.map', 'unreal.world', 'unreal.mega'} <= changed
