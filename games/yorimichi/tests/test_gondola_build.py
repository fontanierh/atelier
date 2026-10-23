"""Production preparation keeps diagnostic overrides out of shipped kit data."""
from types import SimpleNamespace
from pathlib import Path
import ast
import json

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
    assert query.needs==['world.gondola_ground_sources']
    projection=rows['world.gondola_ground_sources']
    assert not projection.needs
    assert {'hidamari.query.HD_NorthTrail','terrain.HD_Terrain.final','terrain.HD_NorthMountains.final'} <= set(projection.reads)
    assert any(key.startswith('belmonte.final_surface.') for key in projection.reads)
    assert 'gondola.ground_sources' in rows['world.gondola_ground'].reads
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
    audit=rows['world.gondola_site.audit']
    validate_imports(audit,audit.inputs)
    assert set(audit.needs)=={'world.gondola_ground','world.gondola_structures','world.craterpark_geometry','world.zeppelin'}
    assert {'gondola_site.atomic','gondola_site.source.fit','gondola.kit','gondola.ground','gondola.structures'} <= set(audit.reads)
    assert 'gondola_site.audit' in site.reads
    assert 'gondola_site.atomic' in site.reads
    assert isinstance(site.commands[0],build.Call)
    assert {p.name for p in site.products}=={'gondola.site'}
    sources=rows['world.gondola_site.sources']
    assert all(c.threads==3 and c.factory_startup for step in (sources,audit) for c in step.commands)
    source_keys={p.name.removeprefix('gondola_site.source.') for p in sources.products}-{'fit'}
    query_keys={key.removeprefix('gondola_site.query.') for key in audit.reads if key.startswith('gondola_site.query.')}
    assert source_keys==query_keys and source_keys
    for key in source_keys:
        owners=[step for step in rows.values() if 'gondola_site.source.'+key in step.reads]
        assert len(owners)==1 and owners[0].cache
        assert owners[0].reads==['gondola_site.source.'+key]


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
    # Exercise discovered bounded membership, including the runtime omission of far rope LODs.
    manifest=tmp_path/'build/gondola/world/site.json'
    manifest.parent.mkdir(parents=True)
    pieces=['GD_L3_Rope_LOD0_Piece00','GD_L3_Rope_LOD1_Piece00','GD_L3_Rope_LOD2_Piece00']
    manifest.write_text(json.dumps(dict(atomic=True,exports=[dict(pieces=[dict(name=name) for name in pieces])])))
    step=next(row for row in recipe.gondola_steps(SimpleNamespace(out=tmp_path/'build')) if row.name=='unreal.gondola')
    assert not any('_Rope_LOD1' in str(path) or '_Rope_LOD2' in str(path) for path in step.outputs)
    # Isolate only the native destination, leaving real recipe helper/code loading intact.
    step.outputs=[tmp_path/'source-game'/path.relative_to(recipe.GAME) if path.is_relative_to(recipe.GAME) else path
                  for path in step.outputs]
    assert step.outputs and not build.outputs_present(step)
    for path in step.outputs:
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'asset')
    assert build.outputs_present(step)
    for suffix in ('Kit/GD_Cabin_Collision.uasset','World/GD_L3_Rope_LOD0_Piece00.uasset',
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
    for name in ('world.gondola_kit.audit','world.gondola_site.audit','world.gondola_site','unreal.gondola',
                 'world.ferry_ship','world.ferry_service','unreal.ferry'):
        assert core in rows[name].inputs,name
    # Service consumes the audited assembled site rather than re-running walking validation.
    assert rows['world.gondola_service'].needs==['world.gondola_site']
    assert 'gondola_site.audit' in rows['world.gondola_site'].reads
    assert core not in rows['world.gondola_service'].inputs
    assert core not in rows['world.ferry_probes'].inputs
    assert core not in rows['world.ferry_site'].inputs
