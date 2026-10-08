"""The retained move set builds from committed inputs without a character model or external cache."""
import hashlib
import importlib.util
import json
import tomllib
from pathlib import Path

import numpy as np

MOTION = Path(__file__).resolve().parents[1] / 'assets/characters/adventure'
SOURCE = MOTION / 'source'


def module(name):
    spec = importlib.util.spec_from_file_location('motion_' + name, MOTION / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_only_the_motion_reference_and_two_props_are_shipped():
    manifest = json.loads((SOURCE / 'manifest.json').read_text())
    assert set(manifest['entries']) == {'reference', 'sword', 'glider'}
    assert set(manifest['files']) == {p.name for p in SOURCE.iterdir()} - {'manifest.json'}
    for name, digest in manifest['files'].items():
        assert hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == digest
    library = module('library')
    assert library.available() and library.root() == SOURCE
    assert all(path.is_file() for path in library.sources())
    for name in manifest['entries']:
        entry = library.entry(name)
        assert entry['glb'].is_file()
        assert entry['curves'] is None or entry['curves'].is_file()


def test_every_retained_motion_is_used_and_every_action_has_timing():
    spec = tomllib.loads((MOTION / 'moves.toml').read_text())
    roster = tomllib.loads((MOTION / 'roster.toml').read_text())['character'][0]
    requested = set(roster['clips'])
    requested.update(action['clip'] for action in spec['action'].values())
    requested.update(sample['clip'] for rows in spec['blend'].values() for sample in rows)
    curves = json.loads((SOURCE / 'animations.json').read_text())
    assert {clip['name'] for clip in curves['animations']} == requested
    assert set(spec['equipment']) == {'sword', 'glider'}
    mechanics = json.loads((SOURCE / 'mechanics.json').read_text())
    for action in spec['action'].values():
        if 'as' in action:
            elements = mechanics['animation_timelines'][f"GameROMPlayer/Actor/AS/{action['as']}.bas"]
            files = {e['parameters'].get('FileName') for e in elements}
            assert action['clip'] in files
            assert action.get('events', action['clip']) in files
    assert set(spec['params']['actions']) <= {a['Def']['ClassName'] for a in mechanics['player_actions']}
    assert set(spec['params']['globals']) <= mechanics['player_parameters'].keys()


def test_neutral_rig_retains_the_animation_skeleton_without_character_surfaces():
    bake = module('bake')
    rig, _ = bake.read_glb(SOURCE / 'reference-rig.glb')
    curves = json.loads((SOURCE / 'animations.json').read_text())
    assert not rig.get('images') and not rig.get('textures') and not rig.get('materials')
    assert len(rig['meshes']) == 1
    primitive = rig['meshes'][0]['primitives'][0]
    assert rig['accessors'][primitive['attributes']['POSITION']]['count'] == 3
    assert {b['name'] for b in curves['skeleton']} <= {n.get('name') for n in rig['nodes']}
    for clip in curves['animations']:
        poses = bake.sample_clip(curves['skeleton'], clip, np.array([0., float(clip['frames'])]))
        assert np.isfinite(poses).all(), clip['name']


def test_marker_rig_can_bake_an_animation_with_the_original_pose(tmp_path):
    bake = module('bake')
    target = tmp_path / 'reference.glb'
    summary = bake.bake(SOURCE / 'reference-rig.glb', SOURCE / 'animations.json', target, clips=['Nml_Wait'])
    assert summary['clips'][0]['source'] == 'Nml_Wait'
    assert bake.check(SOURCE / 'reference-rig.glb', SOURCE / 'animations.json', target, 'Nml_Wait', 5) < 1e-5
