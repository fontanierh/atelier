"""Logical city metadata over independent geometry plans; never exports a mesh."""
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent/'world'))

from atelier.atomic_files import atomic_json
from atelier.export_manifest import real_directory
from regions.hidamari.logical_catalogue import ASSETS


def assemble(out, log=print):
    """@cc [owner:fontanierh,label:correctness;performance] city-logical-metadata-only
    Preserve the original city placement keys and complete logical slot inventory.
    Read complete current plans without constructing or exporting geometry. Native
    material cutoffs MUST project only consumed material fields, not sibling export
    identities; actual pieces retain their independent receiving authority.
    """
    out = Path(out)
    city = out/'hidamari'
    real_directory(city)
    layout = city/'layout-data.json'
    if layout.is_symlink() or not layout.is_file(): raise ValueError('Missing independent city layout')
    manifests = {}
    for key in ASSETS:
        source = out/'planned_exports/hidamari'/key/'plan.json'
        real_directory(source.parent)
        if source.is_symlink() or not source.is_file(): raise ValueError('Missing logical city plan')
        value = json.loads(source.read_text())
        if (value.get('schema')!=1 or value.get('complete') is not True or value.get('parent')!=key
                or not value.get('pieces') or value.get('source_triangles',0)<=0
                or sum(row['triangles'] for row in value['pieces'])!=value['source_triangles']):
            raise ValueError('Incomplete logical city plan')
        slots = value['slots']
        if not slots or len(set(slots))!=len(slots): raise ValueError('Invalid logical material inventory')
        entry = dict(triangles=value['source_triangles'], collision_boxes=value['source_collision_hulls'],
            materials=len(slots), min=[min(row['min'][i] for row in value['pieces']) for i in range(3)],
            max=[max(row['max'][i] for row in value['pieces']) for i in range(3)])
        if all(slot.startswith('HDS_') for slot in slots): entry['slots'] = [slot.removeprefix('HDS_') for slot in slots]
        elif len(slots)!=1: raise ValueError('Unknown city palette policy')
        manifests[key] = entry
    writes = ((city/'city.json',json.loads(layout.read_text())),(city/'manifest.json',manifests))
    for destination,_ in writes:
        if destination.is_symlink() or (destination.exists() and not destination.is_file()):
            raise ValueError('City metadata destination must be regular')
    city.mkdir(parents=True,exist_ok=True)
    for destination,value in writes:
        if not destination.exists() or json.loads(destination.read_text())!=value: atomic_json(destination,value)
    log('HIDAMARI LOGICAL METADATA COMPLETE '+str(len(manifests)))


def material_inputs(out,north):
    """Only import_hidamari's material/props preparation reads this projection."""
    root = Path(out)/'hidamari'
    manifest = json.loads((root/'manifest.json').read_text())
    if set(manifest)!=set(ASSETS): raise ValueError('Incomplete logical city metadata')
    result = {key:dict(slots=value.get('slots')) for key,value in manifest.items() if key.startswith('HD_North')==north}
    return dict(manifest=result,south_join_m=json.loads((root/'north_snow.json').read_text())['south_join_m'])


if __name__=='__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    assemble(parser.parse_args().out)
