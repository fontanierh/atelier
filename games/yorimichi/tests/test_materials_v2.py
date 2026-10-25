"""Portable author-body checks; native shader/package acceptance stays with C3."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

GAME = Path(__file__).resolve().parents[1]


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


body = module(GAME / 'world/materials_v2.py', 'yorimichi_material_body_test')
declarations = module(GAME / 'v2_material_units.py', 'yorimichi_material_declarations_test')
catalog = module(GAME / 'world/asset_catalog.py', 'yorimichi_catalog_body_test')
TEXTURES = {Path(name).stem: {'unit': Path(name).stem, 'item': 'texture'} for name in catalog.TEXTURES}
UNITS = declarations.author_units(TEXTURES)['units']


class Asset:
    def __init__(self, package):
        self.package = package
    def get_path_name(self):
        return self.package + '.' + self.package.rsplit('/', 1)[-1]


def environment(monkeypatch, unit):
    args = deepcopy(unit['params']['args'])
    events, created, loads, saves = [], [], [], []
    def create(factory, name, *values, **kwargs):
        asset = Asset(args['package'])
        created.append(asset)
        events.append((factory, name, values, kwargs))
        return asset
    def load(package):
        loads.append(package)
        return Asset(package)
    def save(asset, *unused):
        saves.append(asset)
        return True
    eal = SimpleNamespace(load_asset=load, save_loaded_asset=save)
    monkeypatch.setitem(sys.modules, 'unreal', SimpleNamespace(EditorAssetLibrary=eal))
    shared = SimpleNamespace(make_mpc=lambda: create('wind', 'MPC_Wind'),
        master=lambda name, **kw: create('master', name, **kw),
        grass_material=lambda *values: create('grass', 'M_Grass', *values),
        cloud_shadow_material=lambda *values: create('cloud', 'M_CloudShadow', *values),
        painterly_material=lambda: create('painterly', 'M_Painterly'))
    assets = SimpleNamespace(instance=lambda name, *values: create('instance', name, *values))
    foliage = SimpleNamespace(enable_bark_lod_blend=lambda asset: events.append(('bark', asset)))
    see = SimpleNamespace(collection=lambda **kw: create('collection', 'MPC_SeeThrough', **kw),
        add_mask=lambda asset, **kw: events.append(('overlay', asset, kw)) or True,
        save=lambda asset: save(asset),
        mask_instance=lambda asset: events.append(('mask', asset)),
        cut_scale=lambda asset, value: events.append(('scale', asset, value)) or True)
    monkeypatch.setattr(body, '_helpers', lambda: (shared, assets, foliage, see))
    context = SimpleNamespace(params={'args': args, 'settings': []}, inputs={slot: '/staged/' + slot for slot in args['inputs']},
        packages={slot: [package] for slot, package in args['inputs'].items()}, outputs=[args['package']])
    return context, events, created, loads, saves, eal


@pytest.mark.parametrize('unit', UNITS, ids=lambda row: row['params']['args']['asset'])
def test_every_authored_factory_creates_only_one_package_and_loads_only_declared_inputs(monkeypatch, unit):
    context, events, created, loads, saves, _ = environment(monkeypatch, unit)
    body.run(context)
    assert len(created) == 1
    assert saves and all(asset is created[0] for asset in saves)
    assert loads == list(context.params['args']['inputs'].values())
    assert events[0][0] == context.params['args']['factory']
    assert created[0].package == context.outputs[0]


def test_sky_factory_uses_fixed_sky_texture_without_spurious_white_dependency(monkeypatch):
    unit = next(row for row in UNITS if row['params']['args']['asset'] == 'M_Sky')
    context, events, *_ = environment(monkeypatch, unit)
    body.run(context)
    values = events[0][3]
    assert values['white'] is None and values['mpc'] is None and values['unlit'] is True
    assert values['fixed_tex'].package == declarations.TEXTURES + 'T_sky'


def test_authored_instance_tint_lod_and_see_through_overrides_use_original_helpers(monkeypatch):
    unit = next(row for row in UNITS if row['params']['args']['asset'] == 'MI_Bark')
    context, events, *_ = environment(monkeypatch, unit)
    body.run(context)
    assert [event[0] for event in events] == ['instance', 'bark', 'mask']
    assert events[0][2][0].package == declarations.MATERIALS + 'M_Painted'
    assert events[0][2][1].package == declarations.TEXTURES + 'T_bark'
    assert events[0][2][2] is None


@pytest.mark.parametrize('defect', ['extra_output', 'wrong_package', 'undeclared_slot', 'extra_argument'])
def test_wrong_ownership_or_inputs_refuse_before_factory_execution(monkeypatch, defect):
    context, _, created, loads, _, _ = environment(monkeypatch, UNITS[2])
    if defect == 'extra_output':
        context.outputs.append('/Game/Other')
    elif defect == 'wrong_package':
        context.packages['T_white'] = ['/Game/Other']
    elif defect == 'undeclared_slot':
        context.inputs['unknown'] = '/staged/unknown'
    else:
        context.params['args']['silent_override'] = True
    with pytest.raises(ValueError):
        body.run(context)
    assert created == loads == []


def test_failed_save_prevents_completion(monkeypatch):
    context, _, _, _, _, eal = environment(monkeypatch, UNITS[0])
    eal.save_loaded_asset = lambda *args: False
    with pytest.raises(ValueError, match='could not save'):
        body.run(context)
