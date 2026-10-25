"""Nox for the game: his source scaled to his height, with smaller textures and without the 25 seat corrective shapes,
which nothing uses until he can sit on a bike or a horse."""
import tomllib
from pathlib import Path

from hakuba_tools import gltf

SRC = Path(__file__).resolve().parent

params = tomllib.loads((SRC / 'params.toml').read_text())
glb = gltf.read(SRC / 'Nox.glb')
gltf.remove_morph_targets(glb)
gltf.scale_to_height(glb, params['height_m'])
gltf.resize_images(glb, params['texture_size'])
gltf.write(glb, SRC.parent / 'nox.glb')
