"""Publish coastal instance data without generating, importing or exporting meshes."""
import argparse
import json
from pathlib import Path
import random
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402


def project(rim_path, library):
    from brinecove import foliage_placements as flora, hero_sources, layout, region
    from brinecove.geometry_finish import settle
    from brinecove.hero_placements import placements as heroes
    from brinecove.rim_schema import read
    from brinecove.runtime_data import transform
    for path in (rim_path, library):
        real_directory(path.parent)
        if path.is_symlink() or not path.is_file(): raise ValueError('Missing coastal placement input')
    verified = hero_sources.verify(library)
    if 'galleon-hull' not in verified: raise ValueError('Production coastal hull is required')
    provenance = verified['galleon-hull'].with_suffix('.provenance.json')
    hull = json.loads(provenance.read_text())['processing']
    hero_rows = heroes(hull)
    if set(hero_rows) - verified.keys(): raise ValueError('Unverified coastal hero placement')
    rim, _ = read(json.loads(rim_path.read_text()))
    settled = settle(rim)
    def final_ground(x, y):
        value = settled(x, y)[1]
        return layout.ground(x, y) if value is None else value
    plants, scrub = {}, {}
    for proto, x, y, z, yaw, scale in flora.groundcover(final_ground):
        (scrub if scale > 1.5 else plants).setdefault(proto, []).append(transform(x, y, z, yaw, scale))
    for proto, x, y, z, yaw, scale in flora.scatter() + flora.bloom_spots(random.Random(5)):
        dz, g = settled(x, y)
        if g is not None and g < .4: continue
        plants.setdefault(proto, []).append(transform(x, y, z + dz, yaw, scale))
    quay_z = float(layout.ground(region.QUAY_STOP[0] - region.ORIGIN[0], region.QUAY_STOP[1] - region.ORIGIN[1])) + 1.
    return dict(schema=1, heroes={slug: [transform(*row) for row in rows] for slug, rows in hero_rows.items()},
                plants=plants, scrub=scrub, quay_z=quay_z)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rim', required=True, type=Path)
    parser.add_argument('--source-library', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    real_directory(args.output.parent)
    if args.output.is_symlink(): raise ValueError('Linked coastal placement output')
    done = threading.Event(); started = time.monotonic()
    def heartbeat():
        while not done.wait(25):
            print(f'Coastal instance placement after {time.monotonic()-started:.0f}s; no complete product yet', flush=True)
    thread = threading.Thread(target=heartbeat, daemon=True); thread.start()
    try: atomic_json(args.output, project(args.rim, args.source_library))
    finally: done.set(); thread.join(timeout=1)
    print('COASTAL PLACEMENT DATA COMPLETE', flush=True)


if __name__ == '__main__': main()
