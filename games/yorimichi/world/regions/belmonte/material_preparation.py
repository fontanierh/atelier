"""Material and image preparation, independent of geometry constructors."""
import hashlib
import json

import numpy as np
from PIL import Image
from atelier.export_manifest import real_directory,sha
from atelier.model_files import member
from belmonte.terrain_palette import TERRAIN_LAYERS


def finish(data,output,assets,library):
    """Current scenery and a Tuscan ground palette with neutral texture grain."""
    materials, images = {}, {}
    for path, entry in data['materials'].items():
        if path.endswith('MI_B_foliage'):
            continue
        scalars, vectors = entry['scalars'], entry['vectors']
        atlas = 'SalonPosters' in path or '/Atelier/' in path
        texture = entry['textures'].get('BaseColor') or entry['textures'].get('DryColor')
        name = 'MI_BM_' + hashlib.sha256(path.encode()).hexdigest()[:12]
        terrain = 'terrain_' in path
        colour = vectors.get('Target', vectors.get('Color', [1., 1., 1., 1.]))
        tint = np.array(vectors.get('Tint', [1., 1., 1., 1.])) * vectors.get('StableColor', [1., 1., 1., 1.])
        layers = {}
        if terrain:
            layers={layer:list(colour) for layer,colour in TERRAIN_LAYERS.items()}
        materials[path] = {'name': name, 'colour': colour, 'tint': tint.tolist(), 'terrain': terrain,
                           'layers': layers, 'tile_m': 9. if terrain else 1. if atlas else 1. / max(scalars.get('Scale', .25), .001),
                           'white_vertex': 'Target' in vectors or 'Color' in vectors,
                           'brightness': scalars.get('Brightness', 1.), 'atlas': atlas,
                           'water': 'water' in path.lower(), 'texture': None}
        if not texture:
            continue
        key = ('tuscan-ground' if terrain else texture) + (':atlas' if atlas else ':detail')
        if key not in images:
            if terrain:
                image_path=assets/'environment/textures/tuscan-ground.jpg'
                provenance_path=image_path.with_suffix('.provenance.json');real_directory(provenance_path.parent)
                if provenance_path.is_symlink() or not provenance_path.is_file():raise ValueError('Terrain provenance must be regular')
                provenance=json.loads(provenance_path.read_text())
                wanted=provenance['source_sha256']
            else:
                image_info = data['textures'][texture]
                image_path = library / member(image_info['file'])
                wanted=image_info['sha256']
            real_directory(image_path.parent)
            if image_path.is_symlink() or not image_path.is_file():raise ValueError('Material source image must be regular')
            assert sha(image_path)==wanted,image_path
            image = Image.open(image_path).convert('RGB')
            image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            if not atlas:
                from surface_textures import neutral_detail
                image = neutral_detail(image)
            file = 'T_BM_' + hashlib.sha256(key.encode()).hexdigest()[:12] + '.png'
            image.save(output / 'textures' / file)
            images[key] = file
        materials[path]['texture'] = images[key]
    return materials

