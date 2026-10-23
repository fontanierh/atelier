"""The region importer must retain the audited opening and refuse stale source/product identities."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world'))
from regions.hidamari.ferry_source import validated_harbor  # noqa: E402


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def proof(tmp_path):
    repo = tmp_path / 'repo'; build = repo / 'build/yorimichi'
    paths = {'code': repo / 'games/yorimichi/world/regions/hidamari/ferry_cut.py',
             'layout': repo / 'games/yorimichi/world/regions/ferry/route.py',
             'ground': build / 'terrain/final.npz',
             'base': build / 'hidamari/assets/HD_Harbor.fbx',
             'site': build / 'ferry/terminals/site.json',
             'mesh': build / 'hidamari/ferry/HD_Harbor.fbx',
             'receipt': build / 'hidamari/ferry/cut.json'}
    for key in ('code', 'layout', 'ground', 'base', 'mesh'):
        p = paths[key]; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(key)
    paths['site'].parent.mkdir(parents=True, exist_ok=True)
    site = {'pass': True, 'inputs': {'code': {str(paths[k].relative_to(repo)): sha(paths[k]) for k in ('code', 'layout')},
            'exports': {'hidamari': {str(paths[k].relative_to(build)): sha(paths[k]) for k in ('base', 'ground')}}}}
    probes = {}
    for name in ('hidamari', 'brinecove', 'crossing'):
        path = build / f'ferry/terminals/world_{name}.npz'
        path.write_bytes(b'probe')
        probes[name] = sha(path)
    site['inputs']['world_probes'] = probes
    paths['site'].write_text(json.dumps(site))
    cut = {'failures': [], 'cuts': [{'cap_normals_pass': True}],
           'source': str(paths['base'].relative_to(build)), 'site': str(paths['site'].relative_to(build)),
           'inputs': {str(paths[k].relative_to(repo)): sha(paths[k]) for k in ('code', 'base', 'site')},
           'output_sha256': sha(paths['mesh'])}
    paths['receipt'].write_text(json.dumps(cut))
    return repo, build, paths, cut


def test_importer_selects_only_the_final_region_source(tmp_path):
    repo, build, paths, _ = proof(tmp_path)
    assert validated_harbor(build, repo) == paths['mesh']
    assert validated_harbor(build, repo) != paths['base']


@pytest.mark.parametrize('changed', ['code', 'layout', 'ground', 'base', 'site', 'mesh'])
def test_changed_source_or_product_refuses(tmp_path, changed):
    repo, build, paths, _ = proof(tmp_path)
    if changed == 'site':
        site = json.loads(paths['site'].read_text()); site['pass'] = False
        paths['site'].write_text(json.dumps(site))
    else:
        paths[changed].write_text('changed')
    with pytest.raises(ValueError, match='failed|changed'):
        validated_harbor(build, repo)


@pytest.mark.parametrize('change', ['inward-cap', 'missing-cuts', 'different-source'])
def test_failed_or_incomplete_cut_refuses(tmp_path, change):
    repo, build, paths, cut = proof(tmp_path)
    if change == 'inward-cap': cut['cuts'][0]['cap_normals_pass'] = False
    elif change == 'missing-cuts': cut['cuts'] = []
    else: cut['source'] = 'hidamari/assets/another.fbx'
    paths['receipt'].write_text(json.dumps(cut))
    with pytest.raises(ValueError, match='failed|different source'):
        validated_harbor(build, repo)


def test_changed_probe_refuses_without_loading_geometry(tmp_path):
    repo, build, _, _ = proof(tmp_path)
    (build/'ferry/terminals/world_crossing.npz').write_bytes(b'changed probe')
    with pytest.raises(ValueError, match='changed'):
        validated_harbor(build, repo)


def test_unreal_preflight_needs_only_standard_library(tmp_path):
    import subprocess
    world = Path(__file__).resolve().parents[1]/'world'
    code = """import sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from regions.ferry import service
try:
    service.preflight(Path(sys.argv[2]))
except FileNotFoundError:
    pass
else:
    raise AssertionError('Missing receipts must refuse')
assert not {'numpy','bpy','mathutils'}.intersection(sys.modules)
"""
    subprocess.run([sys.executable,'-S','-c',code,str(world),str(tmp_path)],check=True)


def test_harbor_water_and_ferry_wake_keep_surf_and_fade_below_100_cm_s():
    root = Path(__file__).resolve().parents[1]
    harbor_mat = (root / 'unreal/Scripts/harbor_material.py').read_text()
    import_ferry = (root / 'unreal/Scripts/import_ferry.py').read_text()
    ferry_cpp = (root / 'unreal/Source/Yorimichi/FerryService.cpp').read_text()
    # Harbor water retains waterline surf and foam inside the harbor (E -> 1).
    assert 'harbor_foam' in harbor_mat and 'max(surf,fleck)' in harbor_mat
    assert 'return lerp(C,inner,E);' in harbor_mat
    # Single mesh FY_Wake and single material M_FerryWake, no Niagara, fading to zero below ~100 cm/s.
    assert '/Game/Ferry/Materials/M_FerryWake' in import_ferry
    assert '/Game/Ferry/Ship/FY_Wake' in import_ferry
    assert 'smoothstep(95.0, 240.0, S)' in import_ferry
    assert 'FMath::SmoothStep(100.f, 260.f, SpeedCmPerS)' in ferry_cpp
    assert 'Niagara' not in import_ferry and 'Niagara' not in ferry_cpp
