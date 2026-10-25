"""Foliage finish/crown native bodies against a fake editor; no Unreal launch."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('foliage_finish_v2', ROOT / 'games/yorimichi/world/foliage_finish_v2.py')
body = importlib.util.module_from_spec(spec); spec.loader.exec_module(body)
OWNER = 'Tree_Test'
FOLDER = '/Game/Japan/FoliageLODs/' + OWNER
BASE = '/Game/Japan/Assets/' + OWNER
RAWS = [f'/Game/_Raw/Foliage/{OWNER}/{key}' for key in (OWNER, OWNER + '_LOD1', OWNER + '_LOD2')]
CROWN = FOLDER + '/MI_' + OWNER + '_Crown'


class Props:
    def __init__(self, **values): self.values = values
    def get_editor_property(self, name): return self.values[name]
    def set_editor_property(self, name, value): self.values[name] = value


class Asset:
    def __init__(self, path): self.path = path
    def get_path_name(self): return self.path + '.' + self.path.rpartition('/')[2]


class MaterialInterface(Asset):
    pass


class Material(MaterialInterface):
    def __init__(self, path, blend=True): super().__init__(path); self.blend = blend
    def get_editor_property(self, name): assert name == 'dithered_lod_transition'; return self.blend


class Instance(MaterialInterface):
    def __init__(self, path):
        super().__init__(path); self.parent = None; self.params = {}
        self.overrides = Props(override_dithered_lod_transition=False, dithered_lod_transition=False)
    def get_editor_property(self, name):
        return {'parent': self.parent, 'base_property_overrides': self.overrides}[name]
    def set_editor_property(self, name, value): assert name == 'base_property_overrides'; self.overrides = value


class Mesh(Asset):
    def __init__(self, path, triangles, slots, scale=1.):
        super().__init__(path)
        self.lods = [(triangles, list(range(len(slots))))]
        self.static_materials = [Props(imported_material_slot_name=name, material_interface=None) for name in slots]
        self.props = {'allow_cpu_access': True, 'light_map_resolution': 64, 'light_map_coordinate_index': 1}
        self.body = Props(collision_trace_flag='default_unset')
        self.simple, self.convex, self.sizes = 1, 1, [1.]
        self.minimum, self.maximum = [0., -200. * scale, 0.], [100. * scale, 0., 300. * scale]
    def get_editor_property(self, name):
        if name == 'static_materials': return self.static_materials
        if name == 'body_setup': return self.body
        return self.props[name]
    def set_editor_property(self, name, value): self.props[name] = value
    def get_material(self, index): return self.static_materials[index].values['material_interface']
    def set_material(self, index, value): self.static_materials[index].values['material_interface'] = value
    def get_num_lods(self): return len(self.lods)
    def get_num_triangles(self, level): return self.lods[level][0]
    def get_num_sections(self, level): return len(self.lods[level][1])
    def get_name(self): return self.path.rpartition('/')[2]
    def get_bounding_box(self): return NS(min=NS(**dict(zip('xyz', self.minimum))), max=NS(**dict(zip('xyz', self.maximum))))


def manifest(tmp_path, **change):
    root = tmp_path / 'inputs/.unreal-runtime/item-0' / OWNER; root.mkdir(parents=True)
    data = {'triangles': [100, 50, 10], 'screen_sizes': [1, .5, .1], 'materials': ['Bark', 'Leaf'],
            'bounds': [[0, 0, 0], [1, 2, 3]], 'collision': 'default', 'import_trunk_collision': False,
            'trunk_collision': None, 'crown': {'slot': OWNER + '_Crown', 'colour': [.1, .2, .3], 'scale': 1.}}
    data.update(change)
    (root / 'manifest.json').write_text(json.dumps(data))
    (root / (OWNER + '.fbx')).write_bytes(b'staged copy')
    return root


@pytest.fixture
def case(tmp_path, monkeypatch):
    helpers = tmp_path / body.HELPERS; helpers.parent.mkdir(parents=True)
    shutil.copy(ROOT / body.HELPERS, helpers)
    assets = {RAWS[0]: Mesh(RAWS[0], 100, ['Bark', 'Leaf']), RAWS[1]: Mesh(RAWS[1], 50, ['Leaf', 'Bark'], .95),
              RAWS[2]: Mesh(RAWS[2], 10, [OWNER + '_Crown'], .9),
              '/Game/Japan/Materials/MI_Bark': Material('/Game/Japan/Materials/MI_Bark'),
              '/Game/Japan/Materials/MI_Leaf': Material('/Game/Japan/Materials/MI_Leaf'),
              '/Game/Japan/Materials/M_Painted': Material('/Game/Japan/Materials/M_Painted', blend=False),
              '/Game/Japan/Textures/T_white': Asset('/Game/Japan/Textures/T_white')}
    events = []
    state = NS(assets=assets, events=events, save_ok=True)
    def duplicate(source, destination):
        events.append(('duplicate', destination)); copy = deepcopy(assets[source]); copy.path = destination
        assets[destination] = copy; return copy
    def save(asset, only_dirty):
        events.append(('save', asset.path)); assert only_dirty is False; return state.save_ok
    def lod(target, level, source, source_level, reuse):
        assert source_level == 0 and reuse is True and level == len(target.lods)
        names = [str(slot.get_editor_property('imported_material_slot_name')) for slot in target.static_materials]
        sections = []
        for index, slot in enumerate(source.static_materials):
            name = slot.get_editor_property('imported_material_slot_name')
            if name not in names:
                target.static_materials.append(deepcopy(slot)); names.append(name)
            sections.append(names.index(name))
        target.lods.append((source.lods[0][0], sections)); return level
    def remove(mesh):
        mesh.simple = mesh.convex = 0; return True
    editor = NS(set_lod_from_static_mesh=lod, set_lod_screen_sizes=lambda mesh, sizes: setattr(mesh, 'sizes', list(sizes)) or True,
                get_lod_screen_sizes=lambda mesh: mesh.sizes, get_number_verts=lambda mesh, level: 7,
                get_lod_material_slot=lambda mesh, level, section: mesh.lods[level][1][section],
                remove_collisions=remove, get_simple_collision_count=lambda mesh: mesh.simple,
                get_convex_collision_count=lambda mesh: mesh.convex,
                get_collision_complexity=lambda mesh: mesh.body.values['collision_trace_flag'])
    def create(name, folder, cls, factory):
        events.append(('create', folder + '/' + name)); asset = Instance(folder + '/' + name)
        assets[asset.path] = asset; return asset
    def parent(material, value): material.parent = value
    def vector(material, name, value): material.params[name] = value
    library = NS(load_asset=lambda path: assets.get(path), does_asset_exist=lambda path: path in assets,
                 duplicate_asset=duplicate, save_loaded_asset=save)
    edit = NS(set_material_instance_parent=parent, set_material_instance_vector_parameter_value=vector,
              set_material_instance_texture_parameter_value=vector,
              get_material_instance_vector_parameter_value=lambda m, name: m.params.get(name),
              get_material_instance_texture_parameter_value=lambda m, name: m.params.get(name),
              update_material_instance=lambda m: events.append(('update', m.path)))
    unreal = NS(StaticMesh=Mesh, MaterialInterface=MaterialInterface, Material=Material, EditorAssetLibrary=library,
                StaticMeshEditorSubsystem=object(), get_editor_subsystem=lambda _: editor,
                load_module=lambda name: None, MaterialEditingLibrary=edit,
                CollisionTraceFlag=NS(CTF_USE_COMPLEX_AS_SIMPLE='complex', CTF_USE_DEFAULT='default'),
                AssetToolsHelpers=NS(get_asset_tools=lambda: NS(create_asset=create)),
                MaterialInstanceConstant=Instance, MaterialInstanceConstantFactoryNew=lambda: 'factory',
                LinearColor=lambda *values: tuple(values))
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    root = manifest(tmp_path)
    packages = {f'lod{i}': [raw] for i, raw in enumerate(RAWS)}
    packages.update({'manifest': [], 'material_Bark': ['/Game/Japan/Materials/MI_Bark'],
                     'material_Leaf': ['/Game/Japan/Materials/MI_Leaf'], 'crown': [CROWN]})
    finish = NS(job_dir=str(tmp_path), inputs={name: str(root) if name == 'manifest' else 'item' for name in packages},
                packages=packages, outputs=sorted([BASE, FOLDER + f'/{OWNER}_LOD1', FOLDER + f'/{OWNER}_LOD2']),
                params={'op': 'finish', 'kind': 'static_mesh', 'source': 'lod0', 'destination': BASE,
                        'input_roots': {'manifest': {'archive_member': 'products/0-0.tree.tar', 'name': OWNER}},
                        'args': {'owner': OWNER, 'manifest': 'manifest', 'levels': ['lod0', 'lod1', 'lod2'],
                                 'materials': {'Bark': 'material_Bark', 'Leaf': 'material_Leaf'}, 'crown': 'crown'}})
    crown = NS(job_dir=str(tmp_path), inputs={'manifest': str(root), 'parent': 'item', 'white': 'item'},
               packages={'manifest': [], 'parent': ['/Game/Japan/Materials/M_Painted'], 'white': ['/Game/Japan/Textures/T_white']},
               outputs=[CROWN], params={'settings': [], 'args': {'action': 'crown', 'owner': OWNER, 'manifest': 'manifest',
                                                                                'parent': 'parent', 'white': 'white'}})
    return state, finish, crown


def test_crown_then_finish_assemble_the_original_lod_chain(case):
    state, finish, crown = case
    material = body.run(crown)
    assert material.path == CROWN and material.parent.path == '/Game/Japan/Materials/M_Painted'
    assert material.params == {'Tint': (.1, .2, .3, 1.), 'Tex': state.assets['/Game/Japan/Textures/T_white']}
    assert material.overrides.values == {'override_dithered_lod_transition': True, 'dithered_lod_transition': True}
    raw = deepcopy(state.assets[RAWS[0]].__dict__)
    mesh = body.run(finish)
    assert state.assets[RAWS[0]].__dict__.keys() == raw.keys() and state.assets[RAWS[0]].lods == raw['lods']
    assert mesh.path == BASE and [lod[0] for lod in mesh.lods] == [100, 50, 10] and mesh.sizes == [1, .5, .1]
    assert mesh.props == {'allow_cpu_access': False, 'light_map_resolution': 4, 'light_map_coordinate_index': 0}
    assert mesh.simple == mesh.convex == 0 and mesh.body.values['collision_trace_flag'] == 'default'
    assert mesh.get_material(2).path == CROWN
    lod1 = state.assets[FOLDER + f'/{OWNER}_LOD1']
    assert [lod1.get_material(i).path for i in range(2)] == ['/Game/Japan/Materials/MI_Leaf', '/Game/Japan/Materials/MI_Bark']
    assert [event for event in state.events if event[0] == 'save'][-3:] == [
        ('save', FOLDER + f'/{OWNER}_LOD1'), ('save', FOLDER + f'/{OWNER}_LOD2'), ('save', BASE)]


@pytest.mark.parametrize('failure', ['triangles', 'bounds', 'lod_bounds', 'palette', 'outputs', 'fresh', 'crown_input',
                                     'material_package', 'save', 'unknown_slot', 'trunk'])
def test_invalid_state_cannot_finish(case, failure, tmp_path):
    state, finish, crown = case
    body.run(crown)
    if failure == 'triangles': state.assets[RAWS[1]].lods[0] = (60, [0, 1])
    elif failure == 'bounds': state.assets[RAWS[0]].maximum[0] += 5
    elif failure == 'lod_bounds': state.assets[RAWS[1]].maximum[2] += 300
    elif failure == 'palette': finish.params['args']['materials'].pop('Leaf')
    elif failure == 'outputs': finish.outputs = [BASE]
    elif failure == 'fresh': state.assets[BASE] = Mesh(BASE, 1, ['Bark'])
    elif failure == 'crown_input': finish.params['args']['crown'] = None
    elif failure == 'material_package': finish.packages['material_Bark'] = ['/Game/Japan/Materials/MI_Leaf']
    elif failure == 'save': state.save_ok = False
    elif failure == 'unknown_slot': state.assets[RAWS[1]].static_materials[0].values['imported_material_slot_name'] = 'Other'
    elif failure == 'trunk':
        shutil.rmtree(tmp_path / 'inputs'); finish.inputs['manifest'] = str(manifest(tmp_path, import_trunk_collision=True))
    with pytest.raises(ValueError):
        body.run(finish)
    if failure not in ('save', 'lod_bounds', 'unknown_slot', 'triangles'):
        assert not any(event == ('save', BASE) for event in state.events)


def test_crown_refuses_foreign_inputs_and_existing_destination(case):
    state, _, crown = case
    crown.packages['parent'] = ['/Game/Japan/Materials/MI_Bark']
    with pytest.raises(ValueError, match='M_Painted'):
        body.run(crown)
    crown.packages['parent'] = ['/Game/Japan/Materials/M_Painted']; state.assets[CROWN] = Instance(CROWN)
    with pytest.raises(ValueError, match='fresh'):
        body.run(crown)
    for params in ({'op': 'other'}, {'op': 'crown', 'args': {'action': 'crown'}}, {'args': {'action': 'other'}}):
        with pytest.raises(ValueError, match='Unsupported'):
            body.run(NS(params=params))
