"""Plan one committed hero model and its separately owned material/texture data."""
import argparse
import json
from pathlib import Path
import re
import sys

sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory, sha  # noqa: E402
from atelier.model_files import member, regular_files, retain_files  # noqa: E402


def key(slug):
    if not re.fullmatch(r'[a-z]+(?:-[a-z]+)*', slug):
        raise ValueError('Invalid committed coastal hero name')
    return 'SM_BC_Hero_' + ''.join(part.title() for part in slug.split('-'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--slug', required=True)
    parser.add_argument('--metadata-output', required=True, type=Path)
    parser.add_argument('--query-output', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    name = key(args.slug)
    from brinecove.paths import MODELS
    source, provenance = MODELS / (args.slug + '.glb'), MODELS / (args.slug + '.provenance.json')
    for path in (source, provenance):
        real_directory(path.parent)
        if path.is_symlink() or not path.is_file(): raise ValueError('Missing committed hero source/provenance')
    digest = sha(source)
    if json.loads(provenance.read_text()).get('output_sha256') != digest:
        raise ValueError('Committed hero source differs from its provenance')
    root = real_directory(args.metadata_output)
    real_directory(args.output)
    import bpy
    from brinecove.hero_model import _import
    from region_mesh_parts import plan
    bpy.ops.wm.read_factory_settings(use_empty=True)
    obj = _import(args.slug)
    if obj is None: raise ValueError('Committed hero has no mesh')
    obj.name = name
    entries, images = {}, {}
    for index, material in enumerate(obj.data.materials):
        if material is None: raise ValueError('Hero material slot is unbound')
        label = f'hero_{args.slug}_{index}'
        image = next((node.image for node in material.node_tree.nodes if node.type == 'TEX_IMAGE' and node.image), None)
        file, colour = None, [1., 1., 1.]
        if image is not None:
            file = f'T_BC_{label}.png'; images[file] = image
        else:
            bsdf = next((n for n in material.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
            if bsdf is not None: colour = [float(c) for c in bsdf.inputs['Base Color'].default_value[:3]]
        entries[label] = dict(name='MI_BC_' + label, colour=colour, texture=file, kind='opaque',
                              pan=0., roughness=.8, metal=False)
        material.name = 'BC_' + label
    expected = {'materials.json', *images}
    if root.exists():
        actual = regular_files(root)
        previous = root / 'materials.json'
        owned = set(expected)
        if previous.exists():
            value = json.loads(previous.read_text())
            if value.get('schema') != 1 or value.get('slug') != args.slug or value.get('complete') is not True:
                raise ValueError('Foreign hero material inventory')
            for filename in value['files']:
                if member(filename) != filename or Path(filename).name != filename or not filename.startswith(f'T_BC_hero_{args.slug}_'):
                    raise ValueError('Foreign hero texture ownership')
                owned.add(filename)
        if actual - owned or any(p.is_dir() for p in root.iterdir()):
            raise ValueError('Foreign hero material files')
    root.mkdir(parents=True, exist_ok=True)
    for filename, image in images.items():
        image.file_format = 'PNG'; image.save(filepath=str(root / filename))
    plan(obj, args.output, partition='spatial' if obj.name in ('SM_BC_Hero_GalleonHull', 'SM_BC_Hero_PirateQueenStatue') else 'whole', options=dict(export_apply=True, export_image_format='NONE'))
    if args.query_output is not None:
        import region_query
        region_query.save(args.query_output, [region_query.capture(obj)], owner=name, stage='final')
    if sha(source) != digest: raise ValueError('Committed hero changed while planning')
    atomic_json(root / 'materials.json', dict(schema=1, complete=True, slug=args.slug,
        source_sha256=digest, materials=entries, files={filename: sha(root / filename) for filename in images}))
    retain_files(root, expected)
    print('COASTAL HERO PLAN COMPLETE', name, flush=True)


if __name__ == '__main__': main()
