import copy
import hashlib
import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('fixed_review', Path(__file__).resolve().parents[1] / 'tools/network_fixed_collision_review.py')
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def receipts():
    entries = sorted(f'{owner}:Mesh:/Game/Test.Mesh:0,0,0:q1:v1:g1:n1' for owner in
                     ('JapanWorld', 'SkatePark', 'MegaRamp', 'SuperUltraMegaPark', 'Hippodrome'))
    probes = [dict(key=f'zone-{i}', complex=c, visibility_hit=True, fixed_hit=True, matches=True,
                   unclassified_visibility_hit=False, component='ground', owner_class='JapanWorld', mesh_asset='/Game/Ground.Ground', instanced=False, item=0, z=100., normal_z=1.)
              for i in range(20) for c in (False, True)]
    value = dict(components=entries, inventory_digest=hashlib.sha1('\n'.join(entries).encode()).hexdigest(),
                 response_errors=[], excluded_stationary=[], probes=probes, visibility_hits=40)
    return dict(fixed_gameplay_collision=value)


def test_fixed_geometry_and_real_trace_agreement():
    a = receipts()
    assert all(review.compare_fixed_collision(a, copy.deepcopy(a)).values())


@pytest.mark.parametrize('edit', [
    lambda r: r.update(components=[]),
    lambda r: r.update(inventory_digest='bad'),
    lambda r: r['components'].pop(),
    lambda r: r['components'].append(r['components'][0]),
    lambda r: r.update(response_errors=['missing ramp']),
    lambda r: r.update(excluded_stationary=['unknown station']),
    lambda r: r.update(probes=[]),
    lambda r: r['probes'][0].update(unclassified_visibility_hit=True),
    lambda r: r['probes'][0].update(matches=False),
    lambda r: r['probes'][0].update(fixed_hit=False),
    lambda r: r['probes'][0].update(z=float('nan')),
    lambda r: r['probes'][0].update(z=99.),
    lambda r: r['probes'][0].update(component='other-ground'),
    lambda r: r.update(visibility_hits=0),
])
def test_missing_geometry_cannot_false_pass(edit):
    a = receipts(); b = copy.deepcopy(a)
    edit(b['fixed_gameplay_collision'])
    assert not all(review.compare_fixed_collision(a, b).values())


def test_instanced_allocation_names_are_not_geometry_identity():
    a = receipts(); b = copy.deepcopy(a)
    a['fixed_gameplay_collision']['probes'][0].update(instanced=True, component='HISM_15')
    b['fixed_gameplay_collision']['probes'][0].update(instanced=True, component='HISM_3')
    assert all(review.compare_fixed_collision(a, b).values())
    b['fixed_gameplay_collision']['probes'][0]['mesh_asset'] = '/Game/Other.Other'
    assert not all(review.compare_fixed_collision(a, b).values())
