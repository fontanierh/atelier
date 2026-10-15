"""The fit gate (assets/characters/pipeline/fit.py): what makes a character's exported clips fail."""
import importlib.util
import json
import math
import sys
from pathlib import Path

import pytest

PIPELINE = Path(__file__).resolve().parents[1] / 'assets' / 'characters' / 'pipeline'
sys.path.insert(0, str(PIPELINE))
spec = importlib.util.spec_from_file_location('character_fit', PIPELINE / 'fit.py')
fit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fit)
definition = fit.definition

CLIP = {'frames': 30, 'ankle_L_cm': 0.5, 'ankle_R_cm': 1.0, 'lowest_toe_cm': 2.0}


def character(tmp_path, waivers=''):
    folder = tmp_path / 'someone'
    folder.mkdir(exist_ok=True)
    (folder / 'character.toml').write_text('id = "someone"\nsource = "Someone.glb"\nheight_cm = 170\n' + waivers)
    return definition.load('someone', tmp_path)


@pytest.fixture
def no_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr(fit, 'FIT', tmp_path / 'fit')
    (tmp_path / 'fit').mkdir()
    return tmp_path / 'fit'


def test_a_good_clip_passes_without_a_baseline(tmp_path, no_baseline):
    assert fit.check(character(tmp_path), 'adventure', {'Walk': CLIP}) == []


@pytest.mark.parametrize('change, failure', [
    ({'frames': 0}, 'no frames'),
    ({'ankle_L_cm': math.nan}, 'ankle_cm: nan'),
    ({'lowest_toe_cm': math.inf}, 'lowest_toe_cm: inf'),
    ({'ankle_R_cm': 4.5}, 'ankle_cm: 4.5 > 4.0'),
])
def test_a_bad_clip_fails(tmp_path, no_baseline, change, failure):
    failures = fit.check(character(tmp_path), 'adventure', {'Walk': {**CLIP, **change}})
    assert any(failure in f for f in failures), failures


@pytest.mark.parametrize('ankles', [{'ankle_R_cm': math.nan}, {'ankle_R_cm': None}, {}])
def test_each_ankle_must_be_measured(tmp_path, no_baseline, ankles):
    clip = {k: v for k, v in CLIP.items() if k != 'ankle_R_cm'}
    clip.update({k: v for k, v in ankles.items() if v is not None})
    assert fit.check(character(tmp_path), 'adventure', {'Walk': clip}) == ['Walk ankle_cm: nan']


def test_an_empty_report_fails(tmp_path, no_baseline):
    assert fit.check(character(tmp_path), 'adventure', {}) == ['no clips exported']


def test_without_a_baseline_the_other_movers_clips_are_expected(tmp_path, no_baseline):
    for other, names in (('a', ['Walk', 'Run']), ('b', ['Walk', 'Run', 'Own'])):
        (no_baseline / f'{other}.json').write_text(json.dumps({'adventure': {n: {'frames': 30} for n in names}}))
    assert fit.check(character(tmp_path), 'adventure', {'Walk': CLIP}) == ['Run: expected, not exported']
    assert fit.check(character(tmp_path), 'adventure', {'Walk': CLIP, 'Run': CLIP}) == []


def test_a_baseline_metric_cannot_go_missing(tmp_path, no_baseline):
    (no_baseline / 'someone.json').write_text(json.dumps({'bike': {'BikeRide': {
        'frames': 60, **{f'reach_{limb}_cm': 1.0 for limb in ('hand_L', 'hand_R', 'foot_L', 'foot_R')}}}}))
    found = {'BikeRide': {'frames': 60, 'reach_error_cm': {'hand_L': 1.0, 'hand_R': 1.0, 'foot_R': 1.0}}}
    assert fit.check(character(tmp_path), 'bike', found) == ['BikeRide reach_foot_L_cm: nan']


def test_a_missing_metric_fails(tmp_path, no_baseline):
    clip = {k: v for k, v in CLIP.items() if k != 'lowest_toe_cm'}
    assert fit.check(character(tmp_path), 'adventure', {'Walk': clip}) == ['Walk lowest_toe_cm: nan']
    assert fit.check(character(tmp_path), 'bike', {'BikeRide': {'frames': 60}}) == [
        f'BikeRide reach_{limb}_cm: nan' for limb in ('foot_L', 'foot_R', 'hand_L', 'hand_R')]


@pytest.mark.parametrize('limb', ['hand_L', 'hand_R', 'foot_L', 'foot_R'])
def test_each_bike_limb_must_be_measured(tmp_path, no_baseline, limb):
    reach = {k: 0.5 for k in ('hand_L', 'hand_R', 'foot_L', 'foot_R') if k != limb}
    assert fit.check(character(tmp_path), 'bike', {'BikeRide': {'frames': 60, 'reach_error_cm': reach}}) == [
        f'BikeRide reach_{limb}_cm: nan']


def test_a_reach_beyond_the_bound_fails_unless_waived(tmp_path, no_baseline):
    clip = {'frames': 60, 'reach_error_cm': {'hand_L': 5.0, 'hand_R': 0.0, 'foot_L': 0.0, 'foot_R': 0.0}}
    assert fit.check(character(tmp_path), 'bike', {'BikeMount': clip}) == ['BikeMount reach_hand_L_cm: 5.0 > 4.0']
    waived = character(tmp_path, '[[fit]]\nreport = "bike"\nclip = "BikeMount"\nmetric = "reach_hand_L_cm"\n'
                                  'bound = 5.5\nreason = "short of its keyed target"\n')
    assert fit.check(waived, 'bike', {'BikeMount': clip}) == []
    assert fit.check(waived, 'bike', {'BikeRide': clip}) == [
        'BikeRide reach_hand_L_cm: 5.0 > 4.0', 'waiver for BikeMount reach_hand_L_cm: no such clip']


def test_a_waiver_names_everything(tmp_path):
    with pytest.raises(AssertionError, match='names its report'):
        character(tmp_path, '[[fit]]\nreport = "bike"\nclip = "BikeMount"\nmetric = "reach_hand_L_cm"\nbound = 5.5\n')


def test_the_baseline_holds_frames_clips_and_metrics(tmp_path, no_baseline):
    (no_baseline / 'someone.json').write_text(json.dumps({'adventure': {
        'Walk': {'frames': 30, 'ankle_cm': 1.0, 'lowest_toe_cm': 2.0}, 'Run': {'frames': 20, 'ankle_cm': 1.0, 'lowest_toe_cm': 0.}}}))
    c = character(tmp_path)
    assert fit.check(c, 'adventure', {'Walk': CLIP}) == ['Run: expected, not exported']
    found = {'Walk': {**CLIP, 'frames': 31, 'ankle_R_cm': 1.6, 'lowest_toe_cm': 1.4}, 'Run': {**CLIP, 'frames': 20}}
    assert fit.check(c, 'adventure', found) == [
        'Walk: 31 frames, the baseline 30',
        'Walk ankle_cm: 1.6, the baseline 1.0 (margin 0.5)',
        'Walk lowest_toe_cm: 1.4, the baseline 2.0 (margin 0.5)']


def test_the_shared_waiver_covers_the_donors_double_jump(tmp_path, no_baseline):
    clip = {**CLIP, 'ankle_L_cm': 19.5}
    assert fit.check(character(tmp_path), 'adventure', {'DoubleJump': clip}) == []
    assert fit.check(character(tmp_path), 'adventure', {'Walk': clip}) == ['Walk ankle_cm: 19.5 > 4.0']


@pytest.mark.parametrize('baseline', sorted(fit.FIT.glob('*.json')), ids=lambda p: p.stem)
def test_every_baseline_belongs_to_a_mover(baseline):
    assert baseline.stem in {c.id for c in definition.movers()}
    data = json.loads(baseline.read_text())
    assert set(data) <= set(fit.REPORTS) and all(data.values())
    for clips in data.values():
        for values in clips.values():
            assert values['frames'] > 0 and all(math.isfinite(v) for v in values.values())


def test_grips_seed_a_draft_from_another_character():
    grips = PIPELINE.parent / 'grips'
    spec = importlib.util.spec_from_file_location('grip_seed', grips / 'seed.py')
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    source = json.loads((grips / 'modori' / 'poses.json').read_text())
    moments = {'character': 'someone', 'grips': [{'id': 'sword_R'}, {'id': 'glider_L'}, {'id': 'bow_R'}]}
    poses = seed.seed(source, moments, '20261013-120000-000', '2026-10-13T12:00:00.000Z')
    assert poses['character'] == 'someone' and sorted(poses['grips']) == ['glider_L', 'sword_R']
    for gid, st in poses['grips'].items():
        assert st['status'] == 'draft' and st['derived'] is None and 'anchor' not in st
        assert st['params'] == source['grips'][gid]['params'] and st['offset'] == source['grips'][gid]['offset']
    assert poses['grips']['glider_L']['prop_placed'] and 'prop_placed' not in poses['grips']['sword_R']


def test_a_grip_check_fails_missing_or_drifting_grips():
    spec = importlib.util.spec_from_file_location('grip_check', PIPELINE.parent / 'grips' / 'check.py')
    check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check)
    held = {'rows': 12, 'hand_mm_from_poser': {'median': 0., 'max': 0.}, 'spread_mm': {'hand_R': 0., 'thumb_end_R': 0.},
            'turn_spread_deg': .003, 'ik_miss_max_cm': 0.}
    assert check.failed({'sword_R': held}, ['sword_R']) == []
    assert check.failed({'sword_R': held}, ['sword_R', 'glider_R']) == ['glider_R: no rows at full weight']
    drifting = {**held, 'spread_mm': {'hand_R': 0., 'thumb_end_R': 2.5}, 'ik_miss_max_cm': math.nan}
    assert check.failed({'sword_R': drifting}, ['sword_R']) == ['sword_R spread_mm: 2.5 > 1.0', 'sword_R ik_miss_max_cm: nan > 0.5']


def test_horse_clips_are_held_to_their_reaches_like_the_bike(tmp_path, no_baseline):
    reach = {'hand_L': 0.0, 'hand_R': 0.0, 'foot_L': 0.0, 'foot_R': 4.5}
    assert 'horse' in fit.REPORTS
    assert fit.check(character(tmp_path), 'horse', {'HorseWalk': {'frames': 60, 'reach_error_cm': reach}}) == [
        'HorseWalk reach_foot_R_cm: 4.5 > 4.0']
    assert fit.check(character(tmp_path), 'horse', {'HorseWalk': {'frames': 60, 'reach_error_cm': {**reach, 'foot_R': 0.}}}) == []
