"""Actual component receipts must establish both client-local bank scopes."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest

TOOLS = Path(__file__).resolve().parents[1] / 'tools'


def module(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def receipts():
    slots = module('network_soundbank_receipts').SLOTS
    result = {}
    for role in ('server', 'client'):
        for phase in (1, 2, 3):
            dry = role == 'client' or phase == 2
            actors = []
            for person in ('host', 'guest'):
                local = person == ('host' if role == 'server' else 'guest')
                actors.append(dict(player=person, pawn=person, local=local,
                    role=3 if role == 'server' else 2 if local else 1,
                    received_frames=60, applied_frames=60,
                    foot_bank='/Game/AudioBanks/dry_street/DA_Bank.DA_Bank' if dry else 'None',
                    skate_set='/Game/AudioBanks/dry_street/DA_Skate.DA_Skate' if dry else 'None',
                    loops=[dict(component=f'{person}.SkateLoop{i}', component_id=100*(1+int(local))+i,
                        slot=slot, wave=('/Game/AudioBanks/dry_street/W_skate_roll_concrete_01.W_skate_roll_concrete_01'
                            if dry else '/Game/Audio/Skate/roll_01.roll_01') if i == 0 else slot,
                        playing=i == 0, volume=.5 if i == 0 else 0.) for i, slot in enumerate(slots)]))
            result[f'{role}-soundbanks-{phase}'] = dict(passed=True, selection=2 if dry else 0,
                net_mode=2 if role == 'server' else 3, world='actual-game', actors=actors)
    result['server-soundbanks-complete'] = {'passed': True, 'phases': 3}
    return result


def write(folder, data):
    for name, row in data.items():
        (folder / (name + '.json')).write_text(json.dumps(row))


def test_independent_world_preferences_and_exact_original_restoration(tmp_path):
    write(tmp_path, receipts())
    assert all(module('network_soundbank_receipts').soundbank_checks(tmp_path).values())


@pytest.mark.parametrize('defect', ['missing', 'malformed', 'no_roll', 'muted', 'nan', 'cue_only',
                                   'same_pawn', 'wrong_role', 'no_remote_frames', 'replaced_component',
                                   'guest_follows_host', 'lost_original', 'wrong_wave', 'no_host_finish'])
def test_refuses_incomplete_or_synthetic_audio_evidence(tmp_path, defect):
    data = receipts()
    row = data['client-soundbanks-2']
    actor = row['actors'][0]
    loop = actor['loops'][0]
    if defect == 'missing': del data['client-soundbanks-2']
    elif defect == 'malformed': row['actors'] = None
    elif defect == 'no_roll': loop['playing'] = False
    elif defect == 'muted': loop['volume'] = 0.
    elif defect == 'nan': loop['volume'] = float('nan')
    elif defect == 'cue_only': actor['loops'] = [{'cue': 'skate.roll'}]
    elif defect == 'same_pawn': row['actors'][1]['player'] = actor['player']
    elif defect == 'wrong_role': actor['role'] = 2
    elif defect == 'no_remote_frames': actor['applied_frames'] = 0
    elif defect == 'replaced_component': loop['component_id'] = 9999
    elif defect == 'guest_follows_host': data['client-soundbanks-3']['selection'] = 0
    elif defect == 'lost_original': data['server-soundbanks-3']['actors'][0]['loops'][5]['wave'] = 'replacement'
    elif defect == 'wrong_wave': loop['wave'] = '/Game/Unrelated'
    elif defect == 'no_host_finish': del data['server-soundbanks-complete']
    write(tmp_path, data)
    assert not all(module('network_soundbank_receipts').soundbank_checks(tmp_path).values())


def test_soundbank_proof_requires_packaged_pair(monkeypatch):
    review = module('review_network_session')
    monkeypatch.setattr(sys, 'argv', ['review', '--soundbanks', '--listen'])
    with pytest.raises(SystemExit) as result:
        review.main()
    assert result.value.code == 2


def test_soundbank_session_reserves_its_entire_supported_ceiling(tmp_path, monkeypatch):
    from atelier.harness.safety import guarded
    review = module('review_network_session')
    observed = {}
    monkeypatch.setattr(guarded, 'run', lambda argv, report, **kw: observed.update(argv=argv, **kw) or 0)
    network_package_target = module('network_package_target')
    monkeypatch.setitem(sys.modules, 'network_package_target', network_package_target)
    container = tmp_path / 'container'
    container.mkdir()
    app = tmp_path / 'Game.app'
    monkeypatch.setattr(network_package_target, 'package_layout', lambda _: (app, None, None, container))
    monkeypatch.setattr(sys, 'argv', ['review', '--soundbanks', '--listen', '--app', str(app),
        '--cook-receipt', str(tmp_path / 'cook.json'), '--expected-identity', 'identity',
        '--aggregate-memory-gib', '14', '--output', str(container / 'proof')])
    assert review.main() == 0
    assert observed['limit_gib'] == 14
    assert observed['track_tree'] is True
    assert '--soundbanks' in observed['argv'] and '--listen' in observed['argv']
    assert observed['argv'][observed['argv'].index('--aggregate-memory-gib') + 1] == '14'
