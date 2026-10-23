"""Canonical original north queries before independently cached Stable rendering."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from village.atomic_sources import current_palette, restore  # noqa: E402
from hidamari_stable.query_samples import Recorder  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--road-context', type=Path, required=True)
    parser.add_argument('--sign-context', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--')+1:])
    yori.OUT = real_directory(args.source_root)
    # The original H/Tree module reads tree dimensions on import. Load it only
    # after binding the complete independently copied canonical input closure.
    from hidamari_stable import build
    output = real_directory(args.output, create=True)
    expected = {'SM_HS_Road.json', 'SM_HS_RoadSign.json', 'site.json'}
    for path in output.iterdir():
        if path.name not in expected or path.is_symlink() or not path.is_file(): raise ValueError('Foreign Stable sampled query output')
    build.H.H = build.H.BACKDROP = build.H.CITY_WEST = build.H.CITY_NORTH = None
    if hasattr(build.H.street_height, 'start'): del build.H.street_height.start
    build.v.PALETTE.clear(); build.v.PALETTE.update(current_palette()); build.palette()
    # This is the explicit shared query-data producer, never an export or missing sibling fallback.
    # The immutable source's exact functions generate the requested coordinate sequence.
    original = build.H.north_height
    result = {}
    for key, path, constructor in (('SM_HS_Road', args.road_context, build.road),
                                   ('SM_HS_RoadSign', args.sign_context, build.road_sign)):
        real_directory(path.parent)
        if path.is_symlink() or not path.is_file(): raise ValueError('Missing selected Stable query context')
        source = json.loads(path.read_text())
        if source.get('asset') != key or source.get('schema') != 1: raise ValueError('Foreign selected query context')
        restore(build.v.R, source['random_state'])
        recorder = Recorder(original); build.H.north_height = recorder
        try: value = constructor(build.L.PAD_Z)
        finally: build.H.north_height = original
        result[key] = recorder.value()
        if key == 'SM_HS_Road': road_heights = value[1]
    site = dict(schema=1, platform_height=build.HL.platform_height(original), road_heights=road_heights)
    for key, value in result.items(): atomic_json(output / (key + '.json'), value)
    atomic_json(output / 'site.json', site)
    print('STABLE CANONICAL SELECTED QUERIES COMPLETE', flush=True)


if __name__ == '__main__': main()
