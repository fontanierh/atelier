"""Publish the city emitter's existing ordered ground and paving geometry."""
import json
from pathlib import Path

from terrain_product import Mesh, save


OWNER = 'HD_Terrain'


def generate(producer, directory):
    """@cc [owner:fontanierh,label:correctness] city-terrain-product-publication
    Call the paired city producer once and publish independent ordered geometry
    copies, then return its original final Mesh to the existing export adapter.
    Natural means before the local coarse-grid railway carve and the air-station
    apron levelling: upstream shaping, existing uncarved fine patches and paving
    remain. Preserve final attributes
    and duplicate corners; do not weld, select new diagonals or combine owners.
    Recipe verification owns freshness. No shared-border guarantee is inferred.
    """
    natural, final = producer()
    if natural.name != OWNER or final.name != OWNER:
        raise ValueError('City terrain publication requires the explicit HD_Terrain owner')
    directory = Path(directory)
    for stage, surface in [('natural', natural), ('final', final)]:
        mesh = Mesh.from_polygons(surface.vertices, surface.faces)
        save(directory/(stage+'.npz'), mesh, owner=OWNER, stage=stage, city=True)
    manifest = {'schema': 1, 'owner': OWNER, 'city': True,
                'units': 'metres, x east, y north, z up',
                'includes': 'existing city ground cells, fine terrace patches and inset paving in emission order',
                'natural_scope': 'before the local coarse-grid railway carve and air-station apron levelling; upstream shaping and uncarved fine patches/paving retained',
                'excludes': ['HD_Streets', 'HD_Square', 'HD_Arrival', 'HD_ParkGrounds', 'HD_NorthMountains', 'water'],
                'stages': ['natural', 'final']}
    (directory/'manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2)+'\n')
    return final
