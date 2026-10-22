"""Validate the committed racing courses before publishing their runtime copy."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path

import numpy as np

GAME = Path(__file__).resolve().parents[2]
DATA = GAME / 'world/racing/belmonte_courses.json'
SCENE = GAME / 'assets/belmonte/source.json'
SOURCE_READER = GAME / 'world/regions/belmonte/source.py'
_spec = importlib.util.spec_from_file_location('racing_venue_source', SOURCE_READER)
source = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(source)
FRAME = 'Belmonte region plan metres (+X east, +Y north, Z up); world = region origin + point'


def number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


from functools import lru_cache


@lru_cache(maxsize=4)
def _scene_manifest(path, mtime_ns, size):
    return json.loads(Path(path).read_text())


def venue(scene):
    scene_path = Path(scene)
    st = scene_path.stat()
    manifest = _scene_manifest(scene_path, st.st_mtime_ns, st.st_size)
    models = [m for m in manifest['meshes'] if m['name'] == 'SM_BM_BHip_Course']
    if len(models) != 1:
        raise ValueError('Racing venue must contain exactly one course mesh')
    model = models[0]
    placements = [p for p in manifest['placements'] if p['asset'] == model['source_asset']]
    if len(placements) != 1:
        raise ValueError('Racing venue must contain exactly one course placement')
    return model, placements[0]['transform'], Path(scene).parent / model['path']


def surface_inputs(scene=SCENE):
    """Actual committed geometry consumed by staging, without parsing meshes during planning."""
    return [venue(scene)[2]]


def validate_surface(data, scene):
    model, transform, path = venue(scene)
    if hashlib.sha256(path.read_bytes()).hexdigest() != model['sha256']:
        raise ValueError('Racing venue mesh differs from its committed checksum')
    faces = source.triangles(path) * [100., -100., 100.] * transform['scale']
    axis = np.asarray(transform['rotation_xyzw'][:3])
    faces += 2 * np.cross(axis, np.cross(axis, faces) + transform['rotation_xyzw'][3] * faces)
    faces = (faces + transform['translation_cm']) / [100., -100., 100.]
    surface = source.Surface(faces)
    low, high = faces.reshape(-1, 3).min(axis=0), faces.reshape(-1, 3).max(axis=0)
    for name, track in data['tracks'].items():
        points = np.asarray(track['points'], float)
        if not ((points >= low - .05) & (points <= high + .05)).all():
            raise ValueError(f'{name}: course points lie outside the placed venue surface')
        ends = np.roll(points, -1, axis=0)
        lengths = np.linalg.norm(ends[:, :2] - points[:, :2], axis=1)
        cumulative = np.r_[0., np.cumsum(lengths)]
        # Six runners: half a metre inside the outer rail, then authored lane spacing.
        samples = np.arange(0., cumulative[-1], 2.)
        segment = np.searchsorted(cumulative, samples, side='right') - 1
        fraction = (samples - cumulative[segment]) / lengths[segment]
        centres = points[segment] + (ends[segment] - points[segment]) * fraction[:, None]
        tangent = (ends[segment, :2] - points[segment, :2]) / lengths[segment, None]
        outward = np.c_[tangent[:, 1], -tangent[:, 0]]
        for lane in range(6):
            offset = -.5 + track['lane_width_m'] * lane
            if not number(offset):
                raise ValueError(f'{name}: lane offset is not finite')
            xy = centres[:, :2] + outward * offset
            if not ((xy >= low[:2] - .05) & (xy <= high[:2] + .05)).all():
                raise ValueError(f'{name}: lane {lane} leaves the placed venue bounds')
            height = surface.height(xy[:, 0], xy[:, 1])
            if not np.isfinite(height).all() or not (np.abs(height - centres[:, 2]) <= .05).all():
                raise ValueError(f'{name}: lane {offset:g} leaves the committed venue surface')


def load(path=DATA, scene=SCENE):
    """@cc [owner:fontanierh,label:correctness] racing-course-source
    Published courses MUST match the committed venue scene, declare their frame and version,
    and have finite nondegenerate closed tracks with measured lap lengths and valid finish
    offsets. All six lanes MUST have actual committed surface support within 5cm at 2m samples.
    Invalid data MUST fail before staging writes any runtime file.
    """
    data = json.loads(Path(path).read_text())
    if not isinstance(data, dict) or type(data.get('version')) is not int or data['version'] != 1 or data.get('frame') != FRAME:
        raise ValueError('Unsupported racing course version or coordinate frame')
    provenance = data.get('source')
    if not isinstance(provenance, dict) or provenance.get('venue_scene_sha256') != hashlib.sha256(Path(scene).read_bytes()).hexdigest():
        raise ValueError('Racing courses differ from their committed venue scene; revalidate them')
    tracks = data.get('tracks')
    if not isinstance(tracks, dict) or set(tracks) != {'turf', 'sand'}:
        raise ValueError('Racing courses must contain turf and sand tracks')
    for name, track in tracks.items():
        if not isinstance(track, dict) or track.get('closed') is not True:
            raise ValueError(f'{name}: the racing course must be closed')
        points = track.get('points')
        if not isinstance(points, list) or not 3 <= len(points) <= 4096 or any(
                not isinstance(p, list) or len(p) != 3 or not all(number(x) for x in p) for p in points):
            raise ValueError(f'{name}: expected 3–4096 finite XYZ course points')
        lengths = [math.dist(a[:2], b[:2]) for a, b in zip(points, points[1:] + points[:1])]
        lap = sum(lengths)
        if not number(lap) or min(lengths) <= 1e-6 or lap <= 1.:
            raise ValueError(f'{name}: degenerate racing course segment')
        measured = track.get('length_m')
        if not number(measured) or abs(lap - measured) > .01:
            raise ValueError(f'{name}: racing course lap length differs from its geometry')
        finish = track.get('finish_s')
        if not number(finish) or not 0. <= finish < lap:
            raise ValueError(f'{name}: finish offset must lie inside the racing course lap')
        width = track.get('lane_width_m')
        if not number(width) or width >= 0.:
            raise ValueError(f'{name}: lanes must step inward from the outer course line')
        area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(points, points[1:] + points[:1]))
        if area <= 0.:
            raise ValueError(f'{name}: racing course must run counter-clockwise')
    validate_surface(data, scene)
    return data
