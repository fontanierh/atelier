"""Production preparation keeps diagnostic overrides out of shipped kit data."""
from types import SimpleNamespace
from pathlib import Path
import ast

from atelier import build
from atelier.build_inputs import validate_imports


def test_normal_kit_preparation_cannot_inherit_partial_or_soft_failure_modes(monkeypatch, tmp_path):
    monkeypatch.setenv('GONDOLA_PIECES','cabin')
    monkeypatch.setenv('GONDOLA_SOFT_FAIL','1')
    monkeypatch.setenv('GONDOLA_PARAMS','diagnostic-parameters.json')
    recipe = build.load_recipe('yorimichi')
    rows = {s.name:s for s in recipe.gondola_steps(SimpleNamespace(out=tmp_path))}
    sources, audit, assembled = (rows['world.gondola_kit.sources'],
        rows['world.gondola_kit.audit'], rows['world.gondola_kit'])
    for step in (sources, audit):
        command, = step.commands
        assert step.cache and step.heavy and command.threads == 3 and command.factory_startup
        validate_imports(step, step.inputs)
    assert isinstance(assembled.commands[0],build.Call)
    assert 'gondola.kit' in {p.name for p in assembled.products}
    assert len([p for p in sources.products if p.name!='gondola_kit.source.audit']) == 33
    # Source construction selects committed canonical defaults, independently of
    # diagnostic P.load/environment and with a complete fixed roster.
    source = ast.parse(sources.commands[0].script.read_text())
    project = next(node for node in source.body if isinstance(node,ast.FunctionDef) and node.name=='project')
    assert any(isinstance(node,ast.Assign) and ast.unparse(node)=='p = dict(P.DEFAULTS)' for node in project.body)
    assert not any(isinstance(node,ast.Call) and ast.unparse(node.func) in ('P.load','os.getenv') for node in ast.walk(project))
    assert 'gondola_kit.audit' in assembled.reads
    assert len(audit.reads) == 23 and all(key.startswith('gondola_kit.query.') for key in audit.reads)


def test_ground_query_is_narrow_and_keeps_region_layout_edits_out_of_exporters(tmp_path):
    recipe=build.load_recipe('yorimichi')
    rows={s.name:s for s in recipe.steps(SimpleNamespace(out=tmp_path,uproject=None))}
    query=rows['world.gondola_ground_inputs']
    assert 'world.gondola_ground' in {s.name for s in build.order(list(rows.values()),['world.gondola_ground'])}
    assert query.cutoff
    assert set(query.needs)=={'world.hidamari','world.terrain.meshes','world.belmonte.ground'}
    assert rows['world.gondola_ground'].needs==['world.gondola_ground_inputs']
    for name in ('world.hidamari','world.belmonte'):
        assert all(Path(p).name!='gondola.py' for p in rows[name].inputs)
    assert all(c.threads==3 and c.factory_startup for c in rows['world.gondola_ground'].commands)


def test_fitted_world_declares_its_complete_code_and_mesh_closure(tmp_path):
    recipe=build.load_recipe('yorimichi')
    rows={s.name:s for s in recipe.gondola_steps(SimpleNamespace(out=tmp_path))}
    site=rows['world.gondola_site']
    validate_imports(site,site.inputs)
    structures=rows['world.gondola_structures']
    validate_imports(structures,structures.inputs)
    assert structures.needs==['world.gondola_structure_inputs']
    assert rows['world.gondola_structure_inputs'].cutoff
    assert set(site.needs)=={'world.gondola_kit','world.gondola_ground','world.gondola_structures','world.craterpark_geometry','world.zeppelin'}
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
    step=next(row for row in recipe.gondola_steps(SimpleNamespace(out=tmp_path/'build')) if row.name=='unreal.gondola')
    # Isolate only the native destination, leaving real recipe helper/code loading intact.
    step.outputs=[tmp_path/'source-game'/path.relative_to(recipe.GAME) if path.is_relative_to(recipe.GAME) else path
                  for path in step.outputs]
    assert step.outputs and not build.outputs_present(step)
    for path in step.outputs:
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'asset')
    assert build.outputs_present(step)
    for suffix in ('Kit/GD_Cabin_Collision.uasset','World/GD_L3_Rope_LOD0.uasset',
                   'Materials/GD_Timber.uasset','Materials/GD_WindowPane.uasset','Textures/GD_wood_panel_color.uasset','import-report.json'):
        path=next(path for path in step.outputs if str(path).endswith(suffix))
        path.unlink()
        assert not build.outputs_present(step),suffix
        path.write_bytes(b'asset')


def test_station_import_keeps_the_complete_plain_canonical_material_roster():
    import importlib
    from gondola_kit_fixture import gondola_modules
    with gondola_modules('params','solid',pure=False) as kit:
        before=dict(kit.params.MATERIALS)
        assert kit.params.WINDOW=='GD_WindowPane'
        assert before[kit.params.WINDOW]==((96,110,120),.2,0.)
        stations=importlib.import_module('stations')
        assert stations.WINDOW==kit.params.WINDOW
        assert kit.solid.MATERIALS is kit.params.MATERIALS
        assert kit.solid.MATERIALS==before


def test_shared_walking_core_is_a_narrow_declared_production_input(tmp_path):
    recipe=build.load_recipe('yorimichi')
    rows={s.name:s for s in recipe.steps(SimpleNamespace(out=tmp_path,uproject=None))}
    core=recipe.WORLD/'walk_raster.py'
    for name in ('world.gondola_kit.audit','world.gondola_site','world.gondola_service','unreal.gondola',
                 'world.ferry_ship','world.ferry_service','unreal.ferry'):
        assert core in rows[name].inputs,name
    assert core not in rows['world.ferry_probes'].inputs
    assert core not in rows['world.ferry_site'].inputs
