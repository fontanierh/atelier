"""Written-output inventories for representative-output steps; real files, no native work."""
import json
import os

from atelier import build, output_inventory
from test_checkpoints import fixture  # noqa: F401


def digest(path):
    return 'd' * 64


def step(ctx, name, folder):
    return build.Step(name, [build.Call(name, lambda *_: None)], outputs=[ctx.out / folder / 'report.json'])


def write(path, data, mtime):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.utime(path, ns=(int(mtime * 1e9), int(mtime * 1e9)))


def test_batch_actions_are_credited_with_their_own_writes(fixture):
    ctx, _ = fixture.checkout('producer')
    first, second = step(ctx, 'first', 'kit'), step(ctx, 'second', 'kit')
    write(ctx.out / 'kit/old.bin', b'before the batch', 100)
    tracker = output_inventory.Tracker(ctx, [first, second])
    write(ctx.out / 'kit/report.json', b'shared report', 250)
    write(ctx.out / 'kit/a.bin', b'first action', 150)
    write(ctx.out / 'kit/b.bin', b'second action', 250)
    result = tracker.batch([(second, 300.), (first, 200.)], digest)
    assert set(result['first']) == {'generated/kit/a.bin', 'generated/kit/report.json'}
    assert set(result['second']) == {'generated/kit/b.bin', 'generated/kit/report.json'}


def test_drift_is_stale_unless_a_newer_step_rewrote_the_file(fixture):
    ctx, _ = fixture.checkout('producer')
    first, later = step(ctx, 'first', 'kit'), step(ctx, 'later', 'kit')
    write(ctx.out / 'kit/report.json', b'report', 100)
    write(ctx.out / 'kit/mesh.bin', b'mesh', 100)
    stamp = dict(time=110, output_inventory=output_inventory.Tracker(ctx, [])._record(first, {str(ctx.out / 'kit/mesh.bin')}, digest))
    assert output_inventory.stale(ctx, first, stamp) == []
    write(ctx.out / 'kit/mesh.bin', b'mesh from another producer', 120)
    assert output_inventory.stale(ctx, first, stamp) == ['generated/kit/mesh.bin']
    ctx.stamps.mkdir(parents=True, exist_ok=True)
    (ctx.stamps / 'later.json').write_text(json.dumps(dict(time=130, output_inventory={'generated/kit/mesh.bin': [0, 0, '']})))
    del ctx.output_claims
    assert output_inventory.stale(ctx, first, stamp) == []
