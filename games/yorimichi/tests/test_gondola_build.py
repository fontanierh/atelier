"""Production preparation keeps diagnostic overrides out of shipped kit data."""
from types import SimpleNamespace
from pathlib import Path

from atelier import build
from atelier.build_inputs import validate_imports
from atelier.build_source import environment


def test_normal_kit_preparation_cannot_inherit_partial_or_soft_failure_modes(monkeypatch, tmp_path):
    monkeypatch.setenv('GONDOLA_PIECES','cabin')
    monkeypatch.setenv('GONDOLA_SOFT_FAIL','1')
    monkeypatch.setenv('GONDOLA_PARAMS','diagnostic-parameters.json')
    recipe = build.load_recipe('yorimichi')
    step = next(s for s in recipe.gondola_steps(SimpleNamespace(out=tmp_path)) if s.name=='world.gondola_kit')
    command, = step.commands
    env = environment(command.env)
    assert set(env['GONDOLA_PIECES'].split(',')) == {'cabin','towers','valley','rim','crater'}
    assert not env['GONDOLA_SOFT_FAIL'] and not env['GONDOLA_PARAMS']
    assert step.heavy and command.threads == 3 and command.factory_startup
    products = {p.name:p for p in step.products}
    assert 'gondola.kit' in products and step.cache
    validate_imports(step, step.inputs)


def test_ground_query_is_narrow_and_keeps_region_layout_edits_out_of_exporters(tmp_path):
    recipe=build.load_recipe('yorimichi')
    rows={s.name:s for s in recipe.steps(SimpleNamespace(out=tmp_path,uproject=None))}
    query=rows['world.gondola_ground_inputs']
    assert 'world.gondola_ground' in {s.name for s in build.order(list(rows.values()),['world.gondola_ground'])}
    assert query.cutoff
    assert set(query.needs)=={'world.hidamari','world.terrain.meshes','world.belmonte'}
    assert rows['world.gondola_ground'].needs==['world.gondola_ground_inputs']
    for name in ('world.hidamari','world.belmonte'):
        assert all(Path(p).name!='gondola.py' for p in rows[name].inputs)
    assert all(c.threads==3 and c.factory_startup for c in rows['world.gondola_ground'].commands)


def test_fitted_world_declares_its_complete_code_and_mesh_closure(tmp_path):
    recipe=build.load_recipe('yorimichi')
    rows={s.name:s for s in recipe.gondola_steps(SimpleNamespace(out=tmp_path))}
    site=rows['world.gondola_site']
    validate_imports(site,site.inputs)
    assert set(site.needs)=={'world.gondola_kit','world.gondola_ground','world.craterpark_geometry'}
    assert len(site.outputs)==32
    assert all(c.threads==3 and c.factory_startup for c in site.commands)


def test_runtime_import_and_staging_are_normal_closed_dependencies(tmp_path):
    recipe=build.load_recipe('yorimichi')
    rows=recipe.steps(SimpleNamespace(out=tmp_path,uproject=None))
    names=[s.name for s in rows]
    assert len(names)==len(set(names))
    by_name={s.name:s for s in rows}
    ordered={s.name for s in build.order(rows,['data.network'])}
    assert {'world.gondola_kit','world.gondola_ground','world.gondola_site','world.gondola_service','unreal.gondola'}<=ordered
    assert 'world.gondola_service' in by_name['data.stage'].needs
    for name in ('world.gondola_service','unreal.gondola'):
        validate_imports(by_name[name],by_name[name].inputs)
    assert not by_name['unreal.gondola'].explicit


def test_missing_native_mesh_material_texture_or_receipt_invalidates_import(tmp_path,monkeypatch):
    recipe=build.load_recipe('yorimichi')
    monkeypatch.setattr(recipe,'GAME',tmp_path/'source-game')
    step=next(row for row in recipe.gondola_steps(SimpleNamespace(out=tmp_path/'build')) if row.name=='unreal.gondola')
    assert step.outputs and not build.outputs_present(step)
    for path in step.outputs:
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'asset')
    assert build.outputs_present(step)
    for suffix in ('Kit/GD_Cabin_Collision.uasset','World/GD_L3_Rope_LOD0.uasset',
                   'Materials/GD_Timber.uasset','Textures/GD_wood_panel_color.uasset','import-report.json'):
        path=next(path for path in step.outputs if str(path).endswith(suffix))
        path.unlink()
        assert not build.outputs_present(step),suffix
        path.write_bytes(b'asset')
