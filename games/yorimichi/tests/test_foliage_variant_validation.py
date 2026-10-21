"""Saved geometry must not bypass current render settings and material validation."""
from copy import deepcopy
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1]/'unreal/Scripts/foliage_variant_validation.py'
SPEC = importlib.util.spec_from_file_location('foliage_variant_validation', SCRIPT)
validation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validation)


class Properties(dict):
    def get_editor_property(self, key):
        return self[key]


def fixture(tmp_path):
    slot = Properties(material_slot_name='FoliageRoles_Body', imported_material_slot_name='Body',
                      uv_channel_data=Properties(override_densities=False, local_uv_densities=[1., 2., 0., 0.]))
    originals = [deepcopy(slot)]
    slots = [deepcopy(slot), Properties(material_slot_name='CanopyNear'), Properties(material_slot_name='CanopyFar')]
    props = Properties(static_materials=slots, auto_compute_lod_screen_size=False,
                       generate_mesh_distance_field=False, light_map_coordinate_index=0)
    bindings = ['wrapped', 'near', 'far']
    build = Properties(recompute_normals=False, recompute_tangents=True, remove_degenerates=False,
                       generate_lightmap_u_vs=False, use_full_precision_u_vs=True,
                       distance_field_resolution_scale=0., max_lumen_mesh_cards=0)
    reduction = Properties(base_lod_model=0, percent_triangles=1., percent_vertices=1., max_deviation=0.)
    counts = [2]
    screens = [1.]
    calls = []
    source = Properties(static_materials=originals)
    mesh = SimpleNamespace(get_editor_property=props.get_editor_property, get_num_lods=lambda: len(counts),
                           get_num_triangles=lambda i: counts[i], get_material=lambda i: bindings[i])
    editor = SimpleNamespace(get_lod_screen_sizes=lambda _: screens,
                             get_lod_build_settings=lambda _, i: build,
                             get_lod_reduction_settings=lambda _, i: reduction)
    path = tmp_path/'snapshot'

    def snapshot(mesh, name):
        calls.append('snapshot')
        Path(name).write_bytes(b'current native snapshot')
        return True

    def digest(name):
        calls.append('digest')
        assert Path(name).read_bytes() == b'current native snapshot'
        return 'expected'

    args = dict(mesh=mesh, source=source, replacements=['wrapped'], canopies=['near', 'far'],
                triangles=[2], screens=[1.], geometry='expected', path=path,
                editor=editor, snapshot=snapshot, digest=digest)
    return args, props, originals, slots, bindings, build, reduction, counts, screens, calls


def test_matching_saved_candidate_is_read_and_never_saved(tmp_path):
    args, props, originals, slots, bindings, build, reduction, counts, screens, calls = fixture(tmp_path)
    before = deepcopy((props, originals, bindings, build, reduction))
    assert validation.matches(**args)
    assert calls == ['snapshot', 'digest']
    assert (props, originals, bindings, build, reduction) == before
    assert not args['path'].exists()


@pytest.mark.parametrize('mutation', ['count', 'screen', 'source_binding', 'near_binding', 'far_binding',
                                     'slot_name', 'imported_name', 'uv_metadata', 'automatic_lod',
                                     'distance_fields', 'lightmap_channel', 'normal_recompute',
                                     'tangent_recompute', 'remove_degenerates', 'lightmap_uv',
                                     'uv_precision', 'distance_field_scale', 'mesh_cards',
                                     'reduction_base', 'triangle_reduction', 'vertex_reduction', 'deviation'])
def test_changed_render_semantics_refuse_before_snapshot(tmp_path, mutation):
    args, props, originals, slots, bindings, build, reduction, counts, screens, calls = fixture(tmp_path)
    changes = {
        'count': lambda: counts.__setitem__(0, 1),
        'screen': lambda: screens.__setitem__(0, .5),
        'source_binding': lambda: bindings.__setitem__(0, 'old'),
        'near_binding': lambda: bindings.__setitem__(1, 'old'),
        'far_binding': lambda: bindings.__setitem__(2, 'old'),
        'slot_name': lambda: slots[0].__setitem__('material_slot_name', 'lost_role'),
        'imported_name': lambda: slots[0].__setitem__('imported_material_slot_name', 'other'),
        'uv_metadata': lambda: slots[0]['uv_channel_data'].__setitem__('override_densities', True),
        'automatic_lod': lambda: props.__setitem__('auto_compute_lod_screen_size', True),
        'distance_fields': lambda: props.__setitem__('generate_mesh_distance_field', True),
        'lightmap_channel': lambda: props.__setitem__('light_map_coordinate_index', 1),
        'normal_recompute': lambda: build.__setitem__('recompute_normals', True),
        'tangent_recompute': lambda: build.__setitem__('recompute_tangents', False),
        'remove_degenerates': lambda: build.__setitem__('remove_degenerates', True),
        'lightmap_uv': lambda: build.__setitem__('generate_lightmap_u_vs', True),
        'uv_precision': lambda: build.__setitem__('use_full_precision_u_vs', False),
        'distance_field_scale': lambda: build.__setitem__('distance_field_resolution_scale', 1.),
        'mesh_cards': lambda: build.__setitem__('max_lumen_mesh_cards', 12),
        'reduction_base': lambda: reduction.__setitem__('base_lod_model', 1),
        'triangle_reduction': lambda: reduction.__setitem__('percent_triangles', .5),
        'vertex_reduction': lambda: reduction.__setitem__('percent_vertices', .5),
        'deviation': lambda: reduction.__setitem__('max_deviation', 1.),
    }
    changes[mutation]()
    reasons = []
    assert not validation.matches(**args, refusal=reasons.append)
    assert reasons and not calls


def test_failed_native_export_cannot_hash_a_stale_file(tmp_path):
    args, *rest = fixture(tmp_path)
    calls = rest[-1]
    args['path'].write_bytes(b'stale output')
    args['snapshot'] = lambda *a: False
    assert not validation.matches(**args)
    assert calls == []
    assert not args['path'].exists()


def test_geometry_change_and_unavailable_readback_are_misses(tmp_path):
    args, *rest = fixture(tmp_path)
    args['digest'] = lambda _: 'changed'
    assert not validation.matches(**args)
    args['editor'].get_lod_build_settings = lambda *a: Properties()
    reasons = []
    assert not validation.matches(**args, refusal=reasons.append)
    assert 'KeyError' in reasons[0]


def test_generated_uv_densities_follow_variant_geometry(tmp_path):
    args, _, _, slots, *_ = fixture(tmp_path)
    slots[0]['uv_channel_data']['local_uv_densities'] = [3., 4., 0., 0.]
    assert validation.matches(**args)


@pytest.mark.parametrize('densities', [[-1., 0., 0., 0.], [float('nan'), 0., 0., 0.], [float('inf'), 0., 0., 0.], []])
def test_invalid_generated_uv_densities_refuse(tmp_path, densities):
    args, _, _, slots, *_ = fixture(tmp_path)
    slots[0]['uv_channel_data']['local_uv_densities'] = densities
    assert not validation.matches(**args)


def test_explicit_uv_density_overrides_are_preserved(tmp_path):
    args, _, originals, slots, *_ = fixture(tmp_path)
    originals[0]['uv_channel_data']['override_densities'] = True
    slots[0]['uv_channel_data']['override_densities'] = True
    assert validation.matches(**args)
    slots[0]['uv_channel_data']['local_uv_densities'][0] = 8.
    assert not validation.matches(**args)
