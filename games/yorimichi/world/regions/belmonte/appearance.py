"""Carry the valley's actual ground colours across the physical island join."""
import numpy as np

from atelier.gltf import glb_pack, glb_parts
from . import layout as L, source, terrain


def far_palette(x, y):
    from hidamari.mountains import smooth
    north = smooth((np.asarray(y)-L.SOUTH_JOIN)/300.)[..., None]
    return np.array([.055,.11,.035])*(1.-north)+np.array([.105,.145,.055])*north


def forest_weight(x, y):
    low = np.array(L.BOUNDS[:2]); high = np.array(L.BOUNDS[2:])
    outer_low = np.array(terrain.OUTER[:2]); outer_high = np.array(terrain.OUTER[2:])
    p = np.stack(np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float)), -1)
    outside = np.maximum((low-p)/(low-outer_low), (p-high)/(outer_high-high)).max(-1)
    t = np.clip(outside, 0., 1.)
    # Broad irregular ecotones soften the rectangular acquisition footprint.
    # Both exact rims still retain their prescribed palette.
    from hidamari.mountains import noise
    t = np.clip(t + t*(1.-t)*noise(p[..., 0], p[..., 1], 140., 82)*.7, 0., 1.)
    return t*t*(3.-2.*t)


def paint_join(path, mesh):
    points = np.asarray(mesh.p) + L.ORIGIN
    # The inner rim keeps the four-layer palette at the actual terrain triangles.
    x = np.clip(points[:, 0], L.BOUNDS[0], L.BOUNDS[2]) - L.ORIGIN[0]
    y = np.clip(points[:, 1], L.BOUNDS[1], L.BOUNDS[3]) - L.ORIGIN[1]
    colours = source.terrain_colours().colour(x, y)
    assert np.isfinite(colours).all(), 'Missing valley colour at the terrain join'
    weight = forest_weight(points[:, 0], points[:, 1])
    # All exterior edges share the forest-floor palette. The mountain material
    # reaches this same palette along its northern edge, including the corners.
    ox = np.clip(points[:, 0], terrain.OUTER[0], terrain.OUTER[2])
    oy = np.clip(points[:, 1], terrain.OUTER[1], terrain.OUTER[3])
    outer = far_palette(ox, oy)
    colours = colours*(1.-weight[:, None]) + outer*weight[:, None]
    if path.stem == 'SM_BM_NorthCountry':
        colours = far_palette(points[:,0],points[:,1])
    rgba = np.c_[source.srgb(colours), weight].astype('<f4')
    doc, binary = glb_parts(path.read_bytes())
    assert doc['accessors'][doc['meshes'][0]['primitives'][0]['attributes']['POSITION']]['count'] == len(rgba)
    doc['bufferViews'].append({'buffer': 0, 'byteOffset': len(binary), 'byteLength': rgba.nbytes, 'target': 34962})
    doc['accessors'].append({'bufferView': len(doc['bufferViews'])-1, 'componentType': 5126, 'count': len(rgba), 'type': 'VEC4'})
    doc['meshes'][0]['primitives'][0]['attributes']['COLOR_0'] = len(doc['accessors'])-1
    binary += rgba.tobytes(); doc['buffers'][0]['byteLength'] = len(binary)
    path.write_bytes(glb_pack(doc, binary))
