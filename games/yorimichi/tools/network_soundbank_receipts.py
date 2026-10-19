"""Validate actual native component observations; never accept cue logs as playback.

The native gameplay driver publishes three phases only while both real riders have
playing roll components. The guest's local preference must remain independent of
host changes. Normal network lifecycle receipts establish admission and disconnect.
"""
import json
import math

SLOTS = ('roll', 'grind', 'slide', 'skid', 'scrape', 'roll_wood', 'roll_metal',
         'roll_asphalt', 'roll_stone', 'roll_dirt', 'roll_grass', 'roll_sand')


def soundbank_checks(folder):
    """Fail closed on missing, malformed, replaced or non-playing actor emitters."""
    try:
        rows = {(role, phase): json.loads((folder / f'{role}-soundbanks-{phase}.json').read_text())
                for role in ('server', 'client') for phase in (1, 2, 3)}
        done = json.loads((folder / 'server-soundbanks-complete.json').read_text())
        assert done == {'passed': True, 'phases': 3}
        identities = {}
        components = {}
        waves = {}
        for (role, phase), row in rows.items():
            selection = 2 if role == 'client' or phase == 2 else 0
            assert row['passed'] is True and row['selection'] == selection
            assert row['net_mode'] == (2 if role == 'server' else 3)
            assert row['world'] and len(row['actors']) == 2
            assert sorted(actor['local'] for actor in row['actors']) == [False, True]
            people = set()
            for actor in row['actors']:
                person = actor['player']
                assert isinstance(person, str) and person and person not in people
                people.add(person)
                local = actor['local']
                assert actor['pawn'] and actor['role'] == (3 if role == 'server' else 2 if local else 1)
                if not local:
                    assert actor['received_frames'] > 0 and actor['applied_frames'] > 0
                if selection == 2:
                    assert actor['foot_bank'] == '/Game/AudioBanks/dry_street/DA_Bank.DA_Bank'
                    assert actor['skate_set'] == '/Game/AudioBanks/dry_street/DA_Skate.DA_Skate'
                else:
                    assert actor['foot_bank'] == actor['skate_set'] == 'None'
                loops = actor['loops']
                assert len(loops) == len(SLOTS) and tuple(loop['slot'] for loop in loops) == SLOTS
                assert len({loop['component'] for loop in loops}) == len(SLOTS)
                assert len({loop['component_id'] for loop in loops}) == len(SLOTS)
                assert all(isinstance(loop['component_id'], int) and loop['component_id'] > 0 and
                           isinstance(loop['wave'], str) and loop['wave'] and
                           type(loop['playing']) is bool and math.isfinite(loop['volume']) and
                           loop['volume'] >= 0 for loop in loops)
                assert any(loop['playing'] and loop['volume'] > .001 and
                           (loop['slot'] == 'roll' or loop['slot'].startswith('roll_')) for loop in loops)
                key = role, person
                identity = actor['pawn'], actor['role'], local
                component = tuple((loop['component'], loop['component_id']) for loop in loops)
                wave = tuple(loop['wave'] for loop in loops)
                if key in identities:
                    assert identities[key] == identity and components[key] == component
                identities[key], components[key] = identity, component
                waves[role, phase, person] = wave
                assert wave[0] == ('/Game/AudioBanks/dry_street/W_skate_roll_concrete_01.W_skate_roll_concrete_01'
                                   if selection else '/Game/Audio/Skate/roll_01.roll_01')
            assert people == {actor['player'] for actor in rows['server', 1]['actors']}
        for person in {actor['player'] for actor in rows['server', 1]['actors']}:
            assert waves['server', 1, person] == waves['server', 3, person]
            assert waves['server', 1, person] != waves['server', 2, person]
            assert waves['client', 1, person] == waves['client', 2, person] == waves['client', 3, person]
        server_local = next(actor['player'] for actor in rows['server', 1]['actors'] if actor['local'])
        client_local = next(actor['player'] for actor in rows['client', 1]['actors'] if actor['local'])
        assert server_local != client_local
        return {'actual_network_soundbank_components': True}
    except (OSError, ValueError, TypeError, KeyError, AssertionError):
        return {'actual_network_soundbank_components': False}
