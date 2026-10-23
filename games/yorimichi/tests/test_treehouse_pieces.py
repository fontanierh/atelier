"""Complete dressing ownership, exact receiving inventories and normal recipe wiring."""
import copy
import ast
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from types import SimpleNamespace

GAME = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('treehouse_piece_test', GAME / 'treehouse_pieces.py')
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)


@pytest.mark.parametrize('dirty', [False, True])
def test_piece_save_keeps_clean_bytes_and_saves_changed_current_finishing(tmp_path, dirty):
    source = GAME / 'unreal/Scripts/import_treehouse_pieces.py'
    function = next(n for n in ast.parse(source.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == 'save_piece')
    scope = dict(DESTINATION=P.DESTINATION, NAME=P.NAME, package_inventory=P.package_inventory)
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), scope)
    name = 'TH_Dressing_cell_-1_0'
    package = P.DESTINATION + '/' + name
    primary = tmp_path / (package.removeprefix('/Game/') + '.uasset')
    primary.parent.mkdir(parents=True)
    primary.write_bytes(b'prior')
    prior = primary.stat().st_mtime_ns
    calls = []
    def save(mesh, *, only_if_is_dirty):
        calls.append(only_if_is_dirty)
        if dirty or not only_if_is_dirty:
            primary.write_bytes(b'finished')
        return True
    mesh = SimpleNamespace(get_name=lambda: name, get_path_name=lambda: package + '.' + name)
    scope['save_piece'](mesh, SimpleNamespace(save_loaded_asset=save), tmp_path)
    assert calls == [True]
    assert primary.read_bytes() == (b'finished' if dirty else b'prior')
    if not dirty:
        assert primary.stat().st_mtime_ns == prior
    primary.unlink()
    with pytest.raises((ValueError, OSError)):
        scope['save_piece'](mesh, SimpleNamespace(save_loaded_asset=lambda *a, **k: True), tmp_path)
    primary.symlink_to(tmp_path / 'external')
    with pytest.raises(AssertionError, match='Linked'):
        scope['save_piece'](mesh, SimpleNamespace(save_loaded_asset=lambda *a, **k: pytest.fail('must refuse before save')), tmp_path)


def manifest():
    rows = [dict(name=f'TH_Dressing_cell_-1_{i}', triangles=1, min=[-2,0,0], max=[-1,1,1],
                 sha256=hashlib.sha256(b'fbx').hexdigest(), used_slots=['TH_wood']) for i in range(2)]
    return dict(version=1, complete=True, parent='TH_Dressing', triangle_limit=32768,
                cell_metres=64, uv_channels=list(P.UVS), collision_boxes=0,
                source_triangles=2, min=[-2,0,0], max=[-1,1,1], slots=['TH_wood', 'TH_pane'], pieces=rows)


@pytest.mark.parametrize('bad', ['partial','parent','budget','duplicate','sum','uv','collision','bounds','slot','hash'])
def test_no_parent_or_partial_fade_geometry_can_enter_runtime_membership(bad):
    data = manifest()
    assert len(P.members(data)) == 2
    if bad == 'partial': data['complete'] = False
    if bad == 'parent': data['pieces'][0]['name'] = 'TH_Dressing'
    if bad == 'budget': data['pieces'][0]['triangles'] = 32769
    if bad == 'duplicate': data['pieces'][1]['name'] = data['pieces'][0]['name']
    if bad == 'sum': data['source_triangles'] += 1
    if bad == 'uv': data['uv_channels'][4] = 'RecomputedCapsule'
    if bad == 'collision': data['collision_boxes'] = 1
    if bad == 'bounds': data['pieces'][0]['min'][0] = float('nan')
    if bad == 'slot': data['slots'][0] = '../foreign'
    if bad == 'hash': data['pieces'][0]['sha256'] = 'missing'
    with pytest.raises(ValueError): P.members(data)


def sources(out):
    root = out / 'treehouse'
    for folder in ('assets/dressing','textures','props','trees'):
        (root / folder).mkdir(parents=True)
    data = manifest()
    (root / 'pieces.json').write_text(json.dumps(data))
    for row in data['pieces']:
        (root / 'assets/dressing' / (row['name'] + '.fbx')).write_bytes(b'fbx')
    for filename, value in (('textures/textures.json', {'wood':{}, 'bark':{}}),
                            ('props/props.json', dict.fromkeys(P.PROPS, {})), ('trees/trees.json', dict.fromkeys(P.TREES, {}))):
        (root / filename).write_text(json.dumps(value))
    parents={'TH_Dressing':[row['name'] for row in data['pieces']]};assets={}
    for row in data['pieces']:
        assets[row['name']]=dict(row,parent='TH_Dressing',collision_hulls=0,slots=data['slots'],
            uv_channels=list(P.UVS),fbx='assets/dressing/'+row['name']+'.fbx')
    for parent,folder in (('TH_Structure','structure'),('TH_Frame','frame'),('TH_Trunks','trunks')):
        name=parent+'_cell_0_0' if parent=='TH_Structure' else parent
        parents[parent]=[name]
        path=root/'assets'/folder/(name+'.fbx');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'fbx')
        assets[name]=dict(name=name,parent=parent,collision_hulls=0,slots=['TH_wood'],used_slots=['TH_wood'],triangles=1,
            min=[0,0,0],max=[1,1,1],sha256=hashlib.sha256(b'fbx').hexdigest(),fbx=str(path.relative_to(root)),
            uv_channels=list(P.UVS) if parent=='TH_Frame' else ['UVMap'])
    (root/'surfaces.json').write_text(json.dumps(dict(schema=1,complete=True,parents=parents,assets=assets)))
    return data


def test_current_sources_require_matching_payloads_and_no_production_whole(tmp_path):
    data = sources(tmp_path)
    assert P.sources_present(tmp_path)
    file = P.source_files(tmp_path)[0]
    file.write_bytes(b'changed')
    assert not P.sources_present(tmp_path)
    file.write_bytes(b'fbx')
    old = tmp_path / 'treehouse/assets/TH_Dressing.fbx'
    old.write_bytes(b'whole')
    assert not P.sources_present(tmp_path)
    old.unlink()
    file.unlink(); file.symlink_to(tmp_path / 'missing')
    assert not P.sources_present(tmp_path)
    assert len(data['pieces']) == 2


def receiving(out, content):
    data = sources(out)
    assets = P.expected_assets(out)
    for package in assets:
        path = content / (package.removeprefix('/Game/') + '.uasset')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(package.encode())
    from treehouse_surfaces import rows
    report = dict(surfaces=[row['package'] for row in rows(out)],
                  surfaces_sha256=hashlib.sha256((out/'treehouse/surfaces.json').read_bytes()).hexdigest(),
                  assets=assets, dressing=[P.DESTINATION+'/'+row['name'] for row in data['pieces']],
                  pieces_sha256=hashlib.sha256((out/'treehouse/pieces.json').read_bytes()).hexdigest(),
                  files=P.package_inventory(content, assets))
    (out/'treehouse/import-report.json').write_text(json.dumps(report))
    return report


@pytest.mark.parametrize('bad', ['piece','frame','material','texture','changed','sidecar','roster','parent','parent_sidecar'])
def test_whole_task_presence_requires_all_current_saved_groups_and_parent_absence(tmp_path, bad):
    out, content = tmp_path/'out', tmp_path/'Content'
    report = receiving(out, content)
    assert P.present(out, content)
    package = content/'Japan/Assets/TH_Frame.uasset'
    if bad in ('piece','frame','material','texture'):
        candidates = [x for x in report['assets'] if
                      (bad == 'piece' and x.startswith(P.DESTINATION+'/')) or
                      (bad == 'frame' and x.endswith('/TH_Frame')) or
                      (bad == 'material' and '/Materials/' in x) or
                      (bad == 'texture' and '/Textures/' in x)]
        (content/(candidates[0].removeprefix('/Game/')+'.uasset')).unlink()
    if bad == 'changed': package.write_bytes(b'changed saved geometry')
    if bad == 'sidecar': package.with_suffix('.ubulk').write_bytes(b'unrecorded bulk')
    if bad == 'roster':
        changed = copy.deepcopy(report); changed['assets'].pop()
        (out/'treehouse/import-report.json').write_text(json.dumps(changed))
    if bad in ('parent','parent_sidecar'):
        parent = content/('Japan/Assets/TH_Dressing' + ('.uasset' if bad == 'parent' else '.ubulk'))
        parent.write_bytes(b'superseded')
    assert not P.present(out, content)


def test_treehouse_recipe_declares_complete_piece_products_and_actual_helpers(monkeypatch):
    from atelier import build
    monkeypatch.setenv('ATELIER_SKIP_ADVENTURE','1')
    from types import SimpleNamespace
    steps = build.load_recipe('yorimichi').steps(SimpleNamespace(game='yorimichi', out=Path('/tmp/treehouse-recipe'), uproject=None))
    by_name = {step.name:step for step in steps}
    producer, native = by_name['world.treehouse'], by_name['unreal.treehouse']
    assert GAME/'world/mesh_pieces.py' in producer.inputs
    assert GAME/'world/regions/treehouse/dressing.py' in producer.inputs
    assert GAME/'treehouse_pieces.py' in producer.inputs and GAME/'treehouse_pieces.py' in native.inputs
    assert native.reads == ['treehouse.meshes', 'materials.shared']
    assert {p.name for p in producer.products} == {'treehouse.meshes','treehouse.runtime'}
    assert {p.name for p in native.products} == {'treehouse.native_assets','treehouse.native_report'}


def test_declared_native_transfer_covers_every_saved_package_and_optional_sidecar(tmp_path):
    out, content = tmp_path/'out', tmp_path/'Content'
    sources(out)
    roots, optional = P.native_outputs(content)
    for asset in P.expected_assets(out):
        primary = content/(asset.removeprefix('/Game/')+'.uasset')
        assert any(primary == root or primary.is_relative_to(root) for root in roots)
        for suffix in P.SIDECARS[1:]:
            sidecar = content/(asset.removeprefix('/Game/')+suffix)
            assert sidecar in optional or any(sidecar.is_relative_to(root) for root in roots)


def test_export_refuses_existing_destination_link_before_capturing_or_writing(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import numpy as np
    import sys
    monkeypatch.setitem(sys.modules, 'bpy', SimpleNamespace())
    monkeypatch.syspath_prepend(str(GAME/'world'))
    script = GAME/'world/regions/treehouse/dressing.py'
    spec = importlib.util.spec_from_file_location('dressing_link_test', script)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    outside = tmp_path/'outside.fbx'; outside.write_bytes(b'preserve external bytes')
    folder = tmp_path/'assets/dressing'; folder.mkdir(parents=True)
    (folder/'TH_Dressing_cell_0_0.fbx').symlink_to(outside)
    obj = SimpleNamespace(name=P.PARENT, matrix_world=np.eye(4))  # no mesh data: preflight must run first
    with pytest.raises(ValueError, match='regular'):
        module.export(obj, folder.parent)
    assert outside.read_bytes() == b'preserve external bytes'
    assert not (tmp_path/'pieces.json').exists()


def test_importer_bootstraps_scripts_from_unrelated_working_directory(tmp_path, monkeypatch):
    import ast
    import sys
    from types import ModuleType
    class Stub:
        def __getattr__(self, name): return self
        def __call__(self, *args, **kwargs): return self
    unreal = ModuleType('unreal')
    unreal.__getattr__ = lambda name: Stub()
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    for name in ('treehouse_atomic_native','mesh_import','forest_native','see_through','atmosphere'):
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setattr(sys, 'path', [p for p in sys.path if p != str(GAME/'unreal/Scripts')])
    monkeypatch.chdir(tmp_path)
    script = GAME/'unreal/Scripts/import_treehouse.py'
    tree = ast.parse(script.read_text()); assert ast.unparse(tree.body[-1]) == 'main()'
    tree.body.pop()  # Test the actual entrypoint bootstrap without starting its native work.
    scope = {'__file__':str(script),'__name__':'treehouse_bootstrap_test'}
    exec(compile(tree,str(script),'exec'),scope)
    assert Path(sys.modules['treehouse_atomic_native'].__file__).parent == script.parent
