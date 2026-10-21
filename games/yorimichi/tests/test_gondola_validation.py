"""A passing label cannot authorize missing or stale kit walking proof."""
import json
from pathlib import Path
import sys

import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'world'))
from gondola import validation


@pytest.mark.parametrize('fault',['missing','failed','layout','checker','incomplete'])
def test_kit_walking_report_is_complete_current_and_required(tmp_path,monkeypatch,fault):
    p=validation.PARAMETERS
    monkeypatch.setattr(p,'source_hash',lambda:'canonical')
    root=tmp_path/'gondola'
    for name in p.product_files():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'product')
    manifest={'failures':[],'soft_fail':False,'source_hash':'canonical','parameters':p.DEFAULTS,'walk':{'all_pass':True}}
    (root/'manifest.json').write_text(json.dumps(manifest))
    report={'all_pass':True,'failures':[],'pieces':{name:{} for name in ('cabin','valley','rim','crater')},
            'inputs':{'checker_sha256':validation.sha(validation.KIT/'walk.py'),
                      'layouts':{name:validation.sha(root/f'layout_{name}.json') for name in ('cabin','valley','rim','crater')}}}
    path=root/'review/walk_report.json';path.write_text(json.dumps(report))
    validation.kit_snapshot(tmp_path)
    if fault=='missing':
        path.unlink()
    elif fault=='layout':
        (root/'layout_rim.json').write_text('changed collision')
    else:
        if fault=='failed':report['failures']=['disconnected route']
        if fault=='checker':report['inputs']['checker_sha256']='old checker'
        if fault=='incomplete':del report['pieces']['crater']
        path.write_text(json.dumps(report))
    with pytest.raises((ValueError,FileNotFoundError)):
        validation.kit_snapshot(tmp_path)
