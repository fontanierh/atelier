"""Vehicle adapters share one raster without sharing mutable grid or audit policy."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np

GAME=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(GAME/'world'))
import walk_raster


def adapter(kind):
    path=GAME/f'assets/vehicles/{kind}/walk.py'
    spec=importlib.util.spec_from_file_location(kind+'_walk_adapter_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_vehicle_grids_and_clearance_settings_remain_per_instance():
    ferry,gondola=adapter('ferry'),adapter('gondola')
    assert ferry.edt is gondola.edt is walk_raster.edt
    assert ferry.bfs_path is gondola.bfs_path is walk_raster.bfs_path
    def deck(module):
        return module.Deck('floor',0,3,0,2,lambda X,Y:np.ones(X.shape,bool),
                           lambda X,Y:np.zeros(X.shape),set()).rasterise([])
    f=deck(ferry);gondola.CELL=.02;cabin=deck(gondola)
    before=cabin.cell(1.,1.),cabin.snap(1.,1.),cabin.dist.copy()
    gondola.CELL=.05;station=deck(gondola)
    assert f.cell_size==station.cell_size==.05 and cabin.cell_size==.02
    assert f.sliver==.3 and cabin.sliver==station.sliver==.44
    assert not f.record_routes and cabin.record_routes and station.record_routes
    assert cabin.cell(1.,1.)==before[0] and cabin.snap(1.,1.)==before[1]
    np.testing.assert_array_equal(cabin.dist,before[2])


def test_gondola_audit_reads_and_writes_only_the_alternate_build_root(tmp_path):
    output=tmp_path/'alternate'/'yorimichi'/'gondola';output.mkdir(parents=True)
    names=('cabin','valley','rim','crater')
    for name in names:(output/f'layout_{name}.json').write_text(json.dumps({'piece':name}))
    # Isolate interpreter/bootstrap state; geometry reports are stand-ins so this
    # test checks real audit path/receipt handling independently of mesh fixtures.
    code=f'''import sys,json
from pathlib import Path
sys.path.insert(0,{str(GAME/'assets/vehicles/gondola')!r})
import walk
assert walk.OUT==Path({str(output)!r})
walk.cabin_report=lambda:json.loads((walk.OUT/'layout_cabin.json').read_text())
walk.station_report=lambda key:json.loads((walk.OUT/('layout_'+key+'.json')).read_text())
walk.verdict=lambda report:[]
report,failures=walk.audit(quiet=True)
assert not failures and set(report['pieces'])==set({names!r})
assert set(report['inputs']['layouts'])==set({names!r})
assert (walk.REVIEW/'walk_report.json').is_file()
'''
    subprocess.run([sys.executable,'-c',code],cwd=tmp_path,
                   env={**os.environ,'ATELIER_BUILD_ROOT':str(tmp_path/'alternate')},
                   capture_output=True,text=True,check=True,timeout=30)
    report=json.loads((output/'review/walk_report.json').read_text())
    assert report['all_pass'] and report['inputs']['raster_sha256']
    assert not (tmp_path/'build').exists()


def test_gondola_numeric_raster_does_not_require_pillow(tmp_path,monkeypatch):
    gondola=adapter('gondola')
    monkeypatch.setitem(sys.modules,'PIL',None)
    deck=gondola.Deck('floor',0,1,0,1,lambda X,Y:np.ones(X.shape,bool),
                      lambda X,Y:np.zeros(X.shape),set()).rasterise([])
    assert gondola.label(deck.walk)[1]==1
    path=tmp_path/'review.png'
    assert gondola.draw(deck,[],[],[],path) is None
    assert not path.exists()
