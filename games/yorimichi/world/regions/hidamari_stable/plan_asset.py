"""Construct one original Stable semantic part/LOD before one bounded atomic export."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori  # noqa: E402,F401
import bpy  # noqa: E402
from atelier.export_manifest import TRIANGLE_LIMIT, real_directory  # noqa: E402
from atelier.mesh_materials import capture_slots  # noqa: E402
from region_mesh_parts import plan  # noqa: E402
from village.atomic_sources import restore, current_palette  # noqa: E402
from hidamari_stable.catalogue import SOURCES, PARTS, selected  # noqa: E402
from hidamari_stable.query_samples import Lookup  # noqa: E402


def construct(key, source, *, queries=None):
    parent, _ = selected(key)
    if (parent in ('SM_HS_Road', 'SM_HS_RoadSign')) != (queries is not None):
        raise ValueError('Stable selected canonical query ownership differs')
    prior_out = yori.OUT
    strict_root = Path(__file__).parent / '.no-ambient-generated-world'
    yori.OUT = strict_root
    from hidamari_stable import build
    prior_sample, prior_h_out = build.H.north_height, build.H.OUT
    lookup = None
    def unavailable(*args, **kwargs): raise ValueError('Stable logical source has no declared north-height queries')
    try:
        build.H.OUT = strict_root
        build.H.north_height = unavailable
        build.H.H = build.H.BACKDROP = build.H.CITY_WEST = build.H.CITY_NORTH = None
        if hasattr(build.H.street_height, 'start'): del build.H.street_height.start
        if queries is not None:
            real_directory(queries.parent)
            if queries.is_symlink() or not queries.is_file(): raise ValueError('Missing selected canonical Stable samples')
            lookup = Lookup(json.loads(queries.read_text())); build.H.north_height = lookup
            # Even an accidental new broad query cannot silently read an old world.
            yori.OUT = build.H.OUT = queries.parent / '.no-ambient-world-fallback'
            build.H.H = build.H.BACKDROP = build.H.CITY_WEST = build.H.CITY_NORTH = None
            if hasattr(build.H.street_height, 'start'): del build.H.street_height.start
        obj = _construct(build, key, source)
        if lookup is not None: lookup.complete()
        return obj
    finally:
        build.H.north_height, yori.OUT, build.H.OUT = prior_sample, prior_out, prior_h_out


def _construct(build, key, source):
    """Use the original function and exact RNG state without constructing any sibling."""
    if source.get('schema') != 1 or source.get('asset') != key: raise ValueError('Foreign Stable construction input')
    parent, lod = selected(key)
    # A factory scene reset does not reload Python module caches in normal batches.
    # Reproduce the fresh original palette and drop deleted Blender material pointers.
    build.v.PALETTE.clear(); build.v.PALETTE.update(current_palette())
    build.surfaces._materials.clear(); build.CITY_SLOTS.clear()
    build.palette(); restore(build.v.R, source['random_state'])
    part = parent.removeprefix('SM_HS_')
    if part in PARTS:
        # Name-dependent source policies see the original name until object capture.
        m = build.v.Mesh('SM_HS_Stable_LOD' + str(lod))
        getattr(build, 'barn_shell' if part == 'Barn' else 'roof' if part == 'BarnRoof' else part.lower())(m, lod)
    elif part in ('StallDoor', 'RoomDoor'):
        m = getattr(build, 'stall_door' if part == 'StallDoor' else 'room_door')(lod)
    else:
        value = getattr(build, dict(Ground='ground', Road='road', RoadSign='road_sign')[part])(build.L.PAD_Z)
        m = value[0] if part == 'Road' else value
    collection = bpy.context.scene.collection
    obj = (build.city_object(m, collection) if part in ('Ground', 'Road')
           else build.make(m, build.material(), collection))
    obj.name = key
    if build.tris(m) > TRIANGLE_LIMIT:
        raise ValueError('Stable semantic source still exceeds the atomic limit; decompose its constructor before export')
    return obj


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset', choices=SOURCES, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--queries', type=Path)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--')+1:])
    real_directory(args.source.parent)
    if args.source.is_symlink() or not args.source.is_file(): raise ValueError('Missing regular Stable constructor data')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    obj = construct(args.asset, json.loads(args.source.read_text()), queries=args.queries)
    plan(obj, args.output, options=dict(export_apply=True), material_specs=capture_slots(obj),
         face_groups=[(args.asset, tuple(range(len(obj.data.polygons))))])
    print('STABLE LOGICAL PLAN COMPLETE ' + args.asset, flush=True)


if __name__ == '__main__': main()
