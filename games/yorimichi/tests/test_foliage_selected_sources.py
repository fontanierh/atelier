"""Selected definitions, pre-export dependencies and complete immutable file assembly."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, build_batches, build_cache, build_deferred, build_inputs, build_products, export_manifest
from atelier.atomic_files import atomic_json

GAME = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('foliage_products_test', GAME / 'foliage_source_products.py')
products = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(products)


def test_selected_stride_and_screens_projection_is_byte_local():
    recipe = build.load_recipe('yorimichi')
    spec = json.loads((GAME / 'assets/foliage/Tree_Broad_A.json').read_text())
    materials = recipe.foliage_build.material_specs.MATERIALS
    before, policy = products.definition_rows('Tree_Broad_A', spec, materials)
    changed = copy.deepcopy(spec)
    changed['strides'][1] += 1
    after, later = products.definition_rows('Tree_Broad_A', changed, materials)
    # Compare the actual canonical JSON encoding used by the projection producer.
    encode = lambda value: json.dumps(value, sort_keys=True)
    assert {key for key in before if encode(before[key]) != encode(after[key])} == {'Tree_Broad_A_LOD2'}
    assert later == policy
    changed = copy.deepcopy(spec)
    changed['screen_sizes'][1] -= .01
    after, later = products.definition_rows('Tree_Broad_A', changed, materials)
    assert after == before and later != policy
    assert before['Tree_Broad_A']['material_order'] == spec['materials']
    assert before['Tree_Broad_A_LOD5']['mode'] == 'crown'
    assert 'arguments' not in before['Tree_Broad_A_LOD5']


def test_full_recipe_declares_every_selected_source_and_preserves_native_api(tmp_path):
    recipe = build.load_recipe('yorimichi')
    graph = build_products.Graph(recipe.steps(SimpleNamespace(game='yorimichi', out=tmp_path, uproject=None)))
    for step in graph.by_name.values():
        build_deferred.validate(step)
        if step.name.startswith('world.foliage.'):
            build_cache.roots(SimpleNamespace(out=tmp_path),step)
            build_inputs.validate_imports(step,build.required_inputs(step))
            build_batches.validate(step)
    sources = [s for n, s in graph.by_name.items() if n.startswith('world.foliage.source.')]
    exporters = [s for n, s in graph.by_name.items() if n.startswith('world.foliage.export.')]
    assert len(sources) == len(exporters) == 102  # 84 authored LODs, plus all 18 Seed FBXs.
    for step in [*sources, *exporters]:
        command, = step.commands
        assert step.cache and command.threads == 3 and command.factory_startup
        assert ('PYTHONHASHSEED', '0') in command.env
        assert not any(str(path).endswith('.fbx') for path in step.inputs)
        assert not any(name.startswith('world.foliage.export.') for name in step.reads)
    crown = graph.by_name['world.foliage.source.Tree_Broad_A_LOD5']
    assert set(crown.reads) == {'foliage.definition.Tree_Broad_A_LOD5', 'foliage.bounds.Tree_Broad_A',
                              'foliage.palette.Tree_Broad_A', 'foliage.payload.Tree_Broad_A_LOD4'}
    lower = graph.by_name['world.foliage.source.Tree_Broad_A_LOD2']
    assert set(lower.reads) == {'foliage.definition.Tree_Broad_A_LOD2', 'foliage.bounds.Tree_Broad_A',
                              'foliage.palette.Tree_Broad_A'}
    assembled = graph.by_name['world.foliage.Tree_Broad_A']
    assert assembled.products[0].name == 'foliage.Tree_Broad_A.source'
    expected = {'foliage.payload.'+step.name.removeprefix('world.foliage.source.')
                for step in sources if step.name == 'world.foliage.source.Tree_Broad_A'
                or step.name.startswith('world.foliage.source.Tree_Broad_A_')}
    assert expected <= set(assembled.reads)
    assert not any(type(command).__name__ == 'Blender' for command in assembled.commands)
    assert set(graph.by_name['unreal.foliage.Tree_Broad_A'].reads) == {
        'foliage.Tree_Broad_A.source', 'materials.foliage_interface'}


def fixture(out):
    kind = 'Fixture';keys = [kind, kind+'_LOD1', kind+'_Seed']
    policy = dict(schema=1, kind=kind, keys=keys, levels=keys[:-1], screen_sizes=[1, .1],
                  collision='default', import_trunk_collision=False, crown=False)
    source = out/'foliage-source'/kind
    source.mkdir(parents=True)
    base = dict(bounds=[[0, 0, 0], [1, 1, 1]], materials=['Bark'], trunk_collision=[1, 0, 0, 0, 0, 0, 1])
    atomic_json(source/(kind+'.base.json'), base)
    atomic_json(source/(kind+'.bounds.json'), base['bounds'])
    atomic_json(source/(kind+'.palette.json'), base['materials'])
    for key, count in zip(keys, [24, 12, 12]):
        (source/(key+'.npz')).write_bytes(key.encode())
        (source/(key+'.materials.json')).write_bytes(b'materials')
        metadata = dict(collision_hulls=1 if key != keys[-1] else 0, slots=['Bark'],
                        geometry_sha256=hashlib.sha256(key.encode()).hexdigest(),
                        materials_sha256=hashlib.sha256(b'materials').hexdigest())
        folder = out/'exports/world.foliage.export'/key
        folder.mkdir(parents=True)
        (folder/(key+'.fbx')).write_bytes(key.encode())
        export_manifest.publish_receipt(folder, key=key, primary=key+'.fbx', triangles=count,
                                       bounds=base['bounds'], metadata=metadata)
        report = dict(key=key, triangles=count, materials=['Bark'], **metadata)
        if key==kind:report['base_sha256']=export_manifest.sha(source/(kind+'.base.json'))
        atomic_json(source/(key+'.report.json'), report)
    return kind, policy, base


def test_assembly_preserves_serialized_collision_even_when_native_use_is_disabled(tmp_path):
    kind, policy, base = fixture(tmp_path)
    result = products.assemble(tmp_path, kind, policy)
    assert result == dict(triangles=[24, 12], screen_sizes=[1, .1], collision='default',
                          import_trunk_collision=False, **base)
    folder = tmp_path/'foliage'/kind
    assert {p.name for p in folder.iterdir()} == {'Fixture.fbx', 'Fixture_LOD1.fbx', 'Fixture_Seed.fbx', 'manifest.json'}
    assert (folder/'Fixture_Seed.fbx').read_bytes() == b'Fixture_Seed'


@pytest.mark.parametrize('corrupt', ['missing', 'identity', 'base', 'export', 'foreign', 'linked'])
def test_incomplete_or_altered_assembly_refuses_before_publication(tmp_path, corrupt):
    kind, policy, _ = fixture(tmp_path)
    folder = tmp_path/'foliage'/kind
    folder.mkdir(parents=True)
    sentinel = folder/'Fixture.fbx';sentinel.write_bytes(b'previous complete member')
    report = tmp_path/'foliage-source/Fixture/Fixture_LOD1.report.json'
    if corrupt=='missing':report.unlink()
    elif corrupt=='identity':
        value=json.loads(report.read_text());value['geometry_sha256']='0'*64;atomic_json(report,value)
    elif corrupt=='base':(tmp_path/'foliage-source/Fixture/Fixture.base.json').write_text('{}')
    elif corrupt=='export':(tmp_path/'exports/world.foliage.export/Fixture_LOD1/Fixture_LOD1.fbx').write_bytes(b'changed')
    elif corrupt=='foreign':(folder/'unowned.fbx').write_bytes(b'foreign')
    elif corrupt=='linked':
        report.unlink();report.symlink_to(tmp_path/'absent')
    with pytest.raises((ValueError, FileNotFoundError)):
        products.assemble(tmp_path,kind,policy)
    assert sentinel.read_bytes()==b'previous complete member'
    assert not (folder/'manifest.json').exists()


@pytest.mark.parametrize('key', ['Fixture', 'Fixture_LOD1', 'Fixture_Seed'])
@pytest.mark.parametrize('suffix', ['.npz', '.materials.json'])
@pytest.mark.parametrize('fault', ['missing', 'changed'])
def test_actual_selected_payloads_must_match_before_any_assembly_mutation(tmp_path, monkeypatch, key, suffix, fault):
    kind, policy, _ = fixture(tmp_path)
    products.assemble(tmp_path, kind, policy)
    folder = tmp_path/'foliage'/kind
    # This genuinely owned previous LOD must not retire on a failed admission.
    (folder/'Fixture_LOD2.fbx').write_bytes(b'previous owned LOD')
    previous = json.loads((folder/'manifest.json').read_text())
    previous.update(triangles=[24, 12, 6], screen_sizes=[1, .1, .01])
    atomic_json(folder/'manifest.json', previous)
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.iterdir()}
    payload = tmp_path/'foliage-source'/kind/(key+suffix)
    if fault == 'missing': payload.unlink()
    else: payload.write_bytes(b'changed selected bytes, reports and exports still agree')
    monkeypatch.setattr(products, 'copy_verified', lambda *a: pytest.fail('copied before payload admission'))
    monkeypatch.setattr(products, 'atomic_json', lambda *a: pytest.fail('published before payload admission'))
    with pytest.raises((ValueError, FileNotFoundError)):
        products.assemble(tmp_path, kind, policy)
    assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.iterdir()} == before


@pytest.mark.parametrize('fault', ['linked_payload', 'directory_payload', 'special_payload', 'empty_directory', 'nested_payload'])
def test_selected_source_member_types_refuse_before_destination_creation(tmp_path, fault):
    kind, policy, _ = fixture(tmp_path)
    source = tmp_path/'foliage-source'/kind; payload = source/'Fixture_LOD1.npz'
    if fault == 'linked_payload':
        external = tmp_path/'external.npz'; payload.rename(external); payload.symlink_to(external)
    elif fault == 'directory_payload': payload.unlink(); payload.mkdir()
    elif fault == 'special_payload':
        import os
        payload.unlink(); os.mkfifo(payload)
    elif fault == 'empty_directory': (source/'foreign').mkdir()
    else:
        (source/'nested').mkdir(); payload.rename(source/'nested'/payload.name)
    with pytest.raises((ValueError, FileNotFoundError)):
        products.assemble(tmp_path, kind, policy)
    assert not (tmp_path/'foliage'/kind).exists()


def test_policy_shrink_preserves_unused_regular_sources_without_admitting_them(tmp_path):
    kind, policy, _ = fixture(tmp_path)
    products.assemble(tmp_path, kind, policy)
    folder = tmp_path/'foliage'/kind; source = tmp_path/'foliage-source'/kind
    previous = json.loads((folder/'manifest.json').read_text())
    previous.update(triangles=[24, 12, 6], screen_sizes=[1, .1, .01])
    atomic_json(folder/'manifest.json', previous)
    obsolete = folder/'Fixture_LOD2.fbx'; obsolete.write_bytes(b'previous owned LOD')
    unused = {source/('Fixture_LOD2'+suffix): b'unused prior source, not admitted or decoded'
              for suffix in ('.npz', '.materials.json', '.report.json')}
    for path, data in unused.items(): path.write_bytes(data)
    result = products.assemble(tmp_path, kind, policy)
    assert result['triangles'] == [24, 12]
    assert not obsolete.exists()
    assert {path.name for path in folder.iterdir()} == {'Fixture.fbx', 'Fixture_LOD1.fbx', 'Fixture_Seed.fbx', 'manifest.json'}
    assert all(path.read_bytes() == data for path, data in unused.items())
