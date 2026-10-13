"""Nox's seat correctives (NoxSeatMorph.h) against the garment candidate's CPU interpolation, and the ride's skin gate
refusing frames whose skin could not be measured as it renders."""
from pathlib import Path
import re
import shutil
import subprocess
import sys

import numpy as np
import pytest

GAME = Path(__file__).resolve().parents[1]
HEADER = GAME / 'unreal' / 'Source' / 'Yorimichi' / 'NoxSeatMorph.h'
sys.path.insert(0, str(GAME / 'scenarios'))
import skate_ride  # noqa: E402

GRID = np.array([-25., 0., 35., 70., 105.])
LABELS = ['m25', '0', '35', '70', '105']


def candidate(flex):
    """The candidate's weights (verify_sparse_morph.py): bilinear on the grid, clamped at its ends, times
    smoothstep(35, 60, the deeper hip); index L * 5 + R."""
    flex = np.asarray(flex, float)
    cells = np.clip(np.searchsorted(GRID, flex) - 1, 0, len(GRID) - 2)
    t = np.clip((flex - GRID[cells]) / (GRID[cells + 1] - GRID[cells]), 0, 1)
    r = np.clip((flex.max() - 35) / 25, 0, 1)
    gate = r * r * (3 - 2 * r)
    out = np.zeros(25)
    for dx in (0, 1):
        for dy in (0, 1):
            out[(cells[0] + dx) * 5 + cells[1] + dy] = gate * (t[0] if dx else 1 - t[0]) * (t[1] if dy else 1 - t[1])
    return out, gate


@pytest.fixture(scope='module')
def probe(tmp_path_factory):
    compiler = shutil.which('clang++')
    if not compiler:
        pytest.skip('clang++ is needed to build the seat-weight probe')
    folder = tmp_path_factory.mktemp('seat')
    (folder / 'probe.cpp').write_text(
        f'#include "{HEADER}"\n#include <cstdio>\n'
        'int main(){float l,r,w[NoxSeat::Count];while(scanf("%f %f",&l,&r)==2){int on=NoxSeat::Weights(l,r,w);'
        'printf("%d",on);for(int i=0;i<NoxSeat::Count;++i)printf(" %.9g",w[i]);printf("\\n");}'
        'for(int l=0;l<NoxSeat::Size;++l)for(int r=0;r<NoxSeat::Size;++r)'
        'printf("NoxSeat_L%s_R%s %d\\n",NoxSeat::Labels[l],NoxSeat::Labels[r],(int)NoxSeat::Moves(l,r));}\n')
    subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-O1', str(folder / 'probe.cpp'), '-o', str(folder / 'probe')],
                   check=True)
    return folder / 'probe'


def run(probe, points):
    text = subprocess.run([str(probe)], input='\n'.join(f'{float(a)!r} {float(b)!r}' for a, b in points), capture_output=True, text=True,
                          check=True).stdout.splitlines()
    return [np.array(line.split()[1:], float) for line in text[:len(points)]], [line.split() for line in text[len(points):]]


def test_weights_match_the_candidate_and_sum_to_the_gate(probe):
    rng = np.random.default_rng(3)
    # Random hips, every grid node and the real-push frames 8 and 40 (sparse-morph-verification.json).
    points = [tuple(p) for p in rng.uniform(-60, 140, (4000, 2))] + [(a, b) for a in GRID for b in GRID] + [
        (-8.170866213410806, 88.74372357660094), (61.048054876849356, -1.2094791185800693), (200., -200.)]
    weights, _ = run(probe, points)
    for point, got in zip(points, weights):
        want, gate = candidate(point)
        assert np.abs(got - want).max() < 1e-5, point
        assert got.min() >= 0 and abs(got.sum() - gate) < 1e-5, point
    assert abs(weights[-3].sum() - 1) < 1e-6 and abs(weights[-2].sum() - 1) < 1e-6


def test_standing_walking_and_gliding_are_exact_no_ops(probe):
    weights, _ = run(probe, [(35., 35.), (34.9, -25.), (0., 0.), (-25., 35.), (float('nan'), 90.)])
    assert all(not w.any() for w in weights)


def test_names_and_moving_cells(probe):
    _, names = run(probe, [])
    assert [n for n, _ in names] == [f'NoxSeat_L{a}_R{b}' for a in LABELS for b in LABELS]
    # The candidate moves vertices only where a hip reaches 70 degrees (garment-candidate.json morph_changed_vertices).
    assert [int(m) for _, m in names] == [int(max(a, b) >= 70) for a in GRID for b in GRID]


def test_skin_gate_fails_on_a_frame_not_measured_as_rendered():
    rows = [{'skin': '1.0', 'skin_bone': 'pelvis', 'skin_groups': 'torso:1.0,feet:0.5'},
            {'skin_error': 'morph_NoxSeat_L70_R0_keeps_no_CPU_deltas'}]
    depth, bone, measured, _ = skate_ride.skin(rows)
    assert np.isnan(depth) and measured == 0 and bone.startswith('skin_error:')
    assert not (depth <= skate_ride.SKIN_DEPTH)
    worst = skate_ride.skin_groups(rows)
    assert max(worst.values()) > skate_ride.SKIN_DEPTH and 'feet' not in worst
    assert skate_ride.skin(rows[:1])[:3] == (1.0, 'pelvis', 1)
    assert skate_ride.skin_groups(rows[:1]) == {'torso': 1.0, 'feet': 0.5}


def test_skin_gate_fails_when_render_and_contact_morphs_differ():
    agree = {'skin': '1.0', 'skin_bone': 'pelvis', 'skin_groups': 'torso:1.0,feet:0.5', 'morph_lag': '0.0000'}
    assert skate_ride.skin([agree])[:3] == (1.0, 'pelvis', 1) and skate_ride.skin_groups([agree]) == {'torso': 1.0, 'feet': 0.5}
    # A shallow, otherwise passing frame whose drawn seat weights differ from those its contact was measured with.
    lagging = dict(agree, morph_lag='0.0125')
    depth, bone, measured, failed = skate_ride.skin([agree, lagging])
    assert np.isnan(depth) and measured == 0 and failed == 1 and bone == 'skin_error:morph_lag_0.0125'
    assert not (depth <= skate_ride.SKIN_DEPTH)
    assert max(skate_ride.skin_groups([agree, lagging]).values()) > skate_ride.SKIN_DEPTH
    # At the tolerance it still counts as agreeing.
    assert skate_ride.skin([dict(agree, morph_lag='0.0001')])[:3] == (1.0, 'pelvis', 1)
    assert skate_ride.morph_lag([{'skin': '1.0'}]) == ''
    assert skate_ride.morph_lag([agree, lagging]) == '; morph lag 0.0125'


def test_native_lag_receipt_preserves_the_gate_boundary(tmp_path):
    compiler = shutil.which('clang++')
    if not compiler:
        pytest.skip('clang++ is needed to check the native receipt formatting')
    source = GAME.parents[1] / 'platform/engine/Plugins/Activities/Skate/Source/AtelierSkate/Private/Ride/RidePhysicalRider.cpp'
    # Use the actual native printf field so low-precision serialization cannot
    # turn a failing rendered/contact comparison into a passing receipt.
    field = re.search(r'morph_lag=(%[^"\s]+)', source.read_text()).group(0)
    (tmp_path / 'receipt.cpp').write_text(
        '#include <cstdio>\nint main(){float lag;while(scanf("%f",&lag)==1)'
        '{printf("' + field + '\\n",lag);}}\n')
    executable = tmp_path / 'receipt'
    subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', str(tmp_path / 'receipt.cpp'), '-o', str(executable)],
                   check=True)
    limit = np.float32(skate_ride.MORPH_LAG)
    above = np.nextafter(limit, np.float32(float('inf')))
    values = [0., np.nextafter(limit, np.float32(0)), limit, above, .00014, .0125,
              float('nan'), float('inf'), -float('inf')]
    receipts = subprocess.run([str(executable)], input='\n'.join(str(v) for v in values), capture_output=True, text=True,
                             check=True).stdout.splitlines()
    assert skate_ride.MORPH_LAG == 1e-4 and skate_ride.SKIN_DEPTH == 2
    for value, receipt in zip(values, receipts, strict=True):
        row = dict(skin='1.0', skin_bone='pelvis', skin_groups='torso:1.0,feet:0.5', **dict([receipt.split('=', 1)]))
        native_value = float(np.float32(value))
        fails = not np.isfinite(native_value) or native_value > skate_ride.MORPH_LAG
        assert bool(skate_ride.unmeasured(row)) == fails
        depth, _, measured, _ = skate_ride.skin([row])
        assert (np.isnan(depth) and measured == 0) if fails else (depth == 1 and measured == 1)
        assert ('skin_error' in skate_ride.skin_groups([row])) == fails
