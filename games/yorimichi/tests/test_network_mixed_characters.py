"""Different players keep their own requested rig and applied equipment."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest


def session_module():
    path = Path(__file__).resolve().parents[1] / 'tools/review_network_session.py'
    spec = importlib.util.spec_from_file_location('network_mixed_character_review', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def receipts():
    people = [dict(id=player, rider=rider, pawn_class='/Script/Yorimichi.' + rider + 'Character',
                   ready=True, moves_ready=True, pawn_shield=shield, applied_shield=shield)
              for player, rider, shield in [('host', 'Cairo', False), ('guest', 'Modori', True)]]
    return {role: dict(local_player_id=player, people=json.loads(json.dumps(people)))
            for role, player in [('server', 'host'), ('client', 'guest')]}


def check(tmp_path, data):
    for role, receipt in data.items():
        (tmp_path / (role + '-connected.json')).write_text(json.dumps(receipt))
    return session_module().mixed_character_checks(tmp_path)


def test_different_characters_and_equipment_agree_on_both_observers(tmp_path):
    assert all(check(tmp_path, receipts()).values())


@pytest.mark.parametrize('fault', ['same_player', 'same_character', 'wrong_class', 'observer_disagreement',
                                  'equipment_leak', 'missing_moves', 'missing_player'])
def test_wrong_per_player_application_cannot_pass(tmp_path, fault):
    data = receipts()
    if fault == 'same_player':
        data['client']['local_player_id'] = 'host'
    elif fault == 'same_character':
        for receipt in data.values():
            receipt['people'][1].update(rider='Cairo', pawn_class='/Script/Yorimichi.CairoCharacter')
    elif fault == 'wrong_class':
        for receipt in data.values():
            receipt['people'][1]['pawn_class'] = '/Script/Yorimichi.NoxCharacter'
    elif fault == 'observer_disagreement':
        data['client']['people'][1]['rider'] = 'Cairo'
    elif fault == 'equipment_leak':
        data['client']['people'][0]['applied_shield'] = True
    elif fault == 'missing_moves':
        del data['server']['people'][1]['moves_ready']
    else:
        data['client']['people'].pop()
    assert not all(check(tmp_path, data).values())


def test_mixed_choice_flag_reaches_the_guarded_gameplay_worker(tmp_path, monkeypatch):
    from atelier.safety import guarded
    module = session_module()
    observed = []
    monkeypatch.setattr(guarded, 'run', lambda command, *args, **kwargs: observed.extend(command) or 0)
    monkeypatch.setattr(sys, 'argv', ['review_network_session.py', '--mixed-characters', '--render-view', 'guest',
                                    '--aggregate-memory-gib', '18', '--rendered-memory-gib', '12',
                                    '--lag-ms', '60', '--variance-ms', '15', '--loss-percent', '2',
                                    '--output', str(tmp_path / 'run')])
    assert module.main() == 0
    assert all(flag in observed for flag in ('--mixed-characters', '--listen', '--gameplay'))


def test_mixed_choices_refuse_the_symmetric_feature_fixture(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['review_network_session.py', '--mixed-characters', '--feature-case', 'equipment'])
    with pytest.raises(SystemExit) as error:
        session_module().main()
    assert error.value.code == 2
