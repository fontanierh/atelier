"""The `character` exporter: the source model scaled to its height, textures resized, morph targets removed
(its settings are listed in tools/README.md)."""
from hakuba_tools import gltf


def export(folder, config):
    output = folder / f'{folder.name}.glb'
    glb = gltf.read(folder / config['source'])
    gltf.remove_morph_targets(glb)
    gltf.scale_to_height(glb, config['height_m'])
    gltf.resize_images(glb, config['texture_size'])
    gltf.write(glb, output)
    return [output]
