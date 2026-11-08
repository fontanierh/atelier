"""Publish the existing mountain triangles during their normal city export."""
import json
from pathlib import Path

from terrain_product import Mesh, save


OWNER = 'HD_NorthMountains'


def generate(base_sampler, directory):
    """@cc [owner:fontanierh,label:correctness] north-mountain-product-publication
    Generate the existing attributed mountain/apron sheets exactly once. Publish
    independent ordered geometry copies for this owner and both stages, then
    return the original final dictionary to the unchanged export adapter.
    Publication MUST NOT modify attributes or infer a shared-border agreement.
    These products describe the normal city build only; gate/trail/city sheets
    remain distinct owners. Recipe verification, not this writer, owns freshness.
    """
    from hidamari import mountains
    natural, final = mountains.sheets(base_sampler)
    directory = Path(directory)
    for stage, sheet in [('natural', natural), ('final', final)]:
        mesh = Mesh.from_polygons(sheet['vertices'], sheet['faces'])
        save(directory/(stage+'.npz'), mesh, owner=OWNER, stage=stage, city=True)
    manifest = {'schema': 1, 'owner': OWNER, 'city': True,
                'units': 'metres, x east, y north, z up',
                'includes': 'existing mountain grid and apron parts in original order',
                'excludes': ['HD_NorthGate', 'HD_NorthTrail', 'HD_NorthApproach', 'HD_NorthParkTrail', 'HD_Terrain'],
                'stages': ['natural', 'final']}
    (directory/'manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2)+'\n')
    return final
