"""The small families' material instances (tools/migrate/small_instances.py): each instance's generator values agree
with its committed editor read, or it is held with its reason. The donor-backed tests skip without a donor checkout
(V2_FAMILIES_DONOR); the reads themselves are committed."""
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'migrate'))
import small_instances as si  # noqa: E402

DONOR = Path(os.environ['V2_FAMILIES_DONOR']) if os.environ.get('V2_FAMILIES_DONOR') else None
needs_donor = pytest.mark.skipif(DONOR is None or not (DONOR / 'build/yorimichi/megapark/build.json').is_file(),
                                 reason='no donor checkout')


@needs_donor
def test_the_mega_park_instances_agree_except_the_two_natural_seams():
    verdict = si.agreement('megapark', DONOR)
    assert len(verdict) == 24
    held = sorted(p for p, v in verdict.items() if not v['agree'])
    assert held == ['/Game/MegaPark/Materials/MI_4cef5bb305cb09eb_Seam', '/Game/MegaPark/Materials/MI_b4686eeb54647811_Seam']
    assert all(v['held'] == ['a two-sided base-property override (recipe v2 cannot state it)'] for p, v in verdict.items() if p in held)


@needs_donor
def test_the_belmonte_instances_all_agree():
    verdict = si.agreement('belmonte', DONOR)
    assert len(verdict) == 7 and all(v['agree'] for v in verdict.values())


@needs_donor
def test_the_tree_house_instances_agree_and_the_pane_is_not_named_by_its_generator():
    verdict = si.agreement('treehouse', DONOR)
    assert sorted(p for p, v in verdict.items() if not v['agree']) == ['/Game/Japan/Treehouse/Materials/MI_TH_pane']
    assert verdict['/Game/Japan/Treehouse/Materials/MI_TH_pane']['held'] == ['the generator does not name this instance']


@needs_donor
def test_the_hidamari_and_fx_instances_agree_and_their_masters_are_held_as_not_instances():
    hid = si.agreement('hidamari', DONOR)
    assert hid['/Game/Japan/Hidamari/Materials/MI_HD_flat']['agree'] is True
    fx = si.agreement('fx', DONOR)
    assert sum(v['agree'] for v in fx.values()) == 4
    assert all(not v['agree'] for p, v in fx.items() if '/M_FX_' in p)


def test_the_committed_reads_name_the_instances_the_tests_assume():
    counts = {f: len(json.loads((si.READS / f'{f}.json').read_text())) for f in si.EXPECTED}
    assert counts == {'megapark': 24, 'belmonte': 7, 'treehouse': 5, 'hidamari': 3, 'fx': 7}


def claim_written():
    """True once the SMALLFAM claim has written its records: the adopted records it moves are then gone."""
    return not (si.GAME / 'assets/adopted/megapark/shared-materials-wood/asset.toml').is_file()


@needs_donor
def test_every_planned_instance_record_loads_and_names_its_outputs(tmp_path):
    """Before the claim: the instance records the claim plans load through the record loader, one row per output.
    After it: the written material records load, and together they name the 37 instances."""
    import records
    import small_families as sf
    if claim_written():
        paths = sorted((si.GAME / 'assets/material').glob('**/asset.toml'))
        loaded = [records.load_asset(p) for p in paths]
        mi = [a for a in loaded if a.kind == 'material-instance' and a.id.endswith('-instances')]
        assert len(mi) == 10, len(mi)
        assert sum(len(a.outputs) for a in mi) == 37
        return
    recs = sf.instance_records(sf.GAME, DONOR, {})
    assert len(recs) == 10
    assert sum(len(r.outputs) for r in recs) == 37
    for rec in recs:
        path = tmp_path / (rec.id.replace('/', '__') + '.toml')
        path.write_text(sf.instance_record_text(rec))
        asset = records.load_asset(path)
        assert asset.kind == 'material-instance' and asset.authority == 'generated'
        assert sorted(r['package'] for r in rec.instances) == sorted(rec.outputs)
