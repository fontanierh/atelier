"""A passing label cannot authorize missing or stale kit walking proof."""
import json
from pathlib import Path
import sys

import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'world'))
from gondola import validation


@pytest.mark.parametrize('fault',['missing','failed','layout','checker','raster','incomplete'])
def test_kit_walking_report_is_complete_current_and_required(tmp_path,monkeypatch,fault):
    raster=tmp_path/'walk_raster.py';raster.write_text('original raster core')
    monkeypatch.setattr(validation,'RASTER',raster)
    p=validation.PARAMETERS
    monkeypatch.setattr(p,'source_hash',lambda:'canonical')
    root=tmp_path/'gondola'
    for name in p.product_files():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'product')
    manifest={'failures':[],'soft_fail':False,'source_hash':'canonical','parameters':p.DEFAULTS,'walk':{'all_pass':True}}
    (root/'manifest.json').write_text(json.dumps(manifest))
    report={'all_pass':True,'failures':[],'pieces':{name:{} for name in ('cabin','valley','rim','crater')},
            'inputs':{'checker_sha256':validation.sha(validation.KIT/'walk.py'),'raster_sha256':validation.sha(raster),
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
        if fault=='raster':raster.write_text('changed raster core')
        if fault=='incomplete':del report['pieces']['crater']
        path.write_text(json.dumps(report))
    with pytest.raises((ValueError,FileNotFoundError)):
        validation.kit_snapshot(tmp_path)


@pytest.mark.parametrize('fault',['missing','failed','coverage','count','height','allowance','surfaces'])
def test_complete_access_floor_receipt_is_required(fault):
    access={'surfaces':[{}],'ground_proof':{'complete_coverage':True,'surfaces':1,
            'maximum_intrusion_m':.01,'allowance_m':.03,'pass':True}}
    validation.validate_access_ground(access)
    proof=access['ground_proof']
    if fault=='missing':del access['ground_proof']
    elif fault=='failed':proof['pass']=False
    elif fault=='coverage':proof['complete_coverage']=False
    elif fault=='count':proof['surfaces']=0
    elif fault=='height':proof['maximum_intrusion_m']=float('nan')
    elif fault=='allowance':proof['allowance_m']=.3
    elif fault=='surfaces':access['surfaces']=[]
    with pytest.raises(ValueError,match='complete access-floor proof'):
        validation.validate_access_ground(access)


@pytest.mark.parametrize('fault',['missing','failed','poses','direction','points','representation','vertices','bound','roundtrip','nan','hardware','axis','allowance','frame','transform','world'])
def test_final_stored_rope_proof_is_complete_and_required(fault):
    proof={'pass':True,'representation':'fbx-float32-cm-ring-axis','directions':[-1,1],
           'poses':42,'points_per_pose':114,'matched_vertices':120,
           'control_point_frame':'mesh-local','world_transform_applied':True,'world_displacement_m':.0003,
           'max_error_mm':1.8,'bound_mm':1.805,'control_point_error_m':0.,'control_point_allowance_m':.0002,'axis_extra_m':.0001,
           'axis_bound_m':.0003,'hardware_bound_m':.0997}
    row={'stored_contact':proof,'axis_deviation_m':.0002}
    validation.validate_stored_contact(row,42,.1)
    if fault=='missing':row.clear()
    elif fault=='failed':proof['pass']=False
    elif fault=='poses':proof['poses']=21
    elif fault=='direction':proof['directions']=[-1]
    elif fault=='points':proof['points_per_pose']=57
    elif fault=='representation':proof['representation']='ideal double axis'
    elif fault=='vertices':proof['matched_vertices']=0
    elif fault=='bound':proof['bound_mm']=1.8
    elif fault=='roundtrip':proof['control_point_error_m']=.01
    elif fault=='nan':proof['max_error_mm']=float('nan')
    elif fault=='hardware':proof['hardware_bound_m']=.094
    elif fault=='axis':proof['axis_bound_m']=.0001
    elif fault=='allowance':proof['control_point_allowance_m']=.01
    elif fault=='frame':proof.pop('control_point_frame')
    elif fault=='transform':proof['world_transform_applied']=False
    elif fault=='world':proof['world_displacement_m']=float('nan')
    with pytest.raises(ValueError,match='stored rope contact proof'):
        validation.validate_stored_contact(row,42,.1)
