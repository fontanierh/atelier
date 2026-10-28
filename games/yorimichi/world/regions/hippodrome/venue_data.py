"""Explicit venue placements/course metadata and independent deterministic textures."""
import sys
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[i]) for i in (2,1)]
import numpy as np
from hippodrome import layout as L
from hippodrome.query_context import height

def tiling_noise(size, seed, falloff):
    """Tileable noise: white noise filtered in the frequency domain, normalised to 0..1."""
    rng = np.random.default_rng(seed)
    f = np.fft.fftfreq(size)
    radius = np.sqrt(f[None, :] ** 2 + f[:, None] ** 2) + 1. / size
    field = np.real(np.fft.ifft2(np.fft.fft2(rng.standard_normal((size, size))) / radius ** falloff))
    return (field - field.min()) / (field.max() - field.min())

def textures(destination):
    from PIL import Image
    folder = Path(destination)
    folder.mkdir(parents=True, exist_ok=True)
    size = 512
    soft, fine = tiling_noise(size, 11, 1.4), tiling_noise(size, 12, .6)
    # Raked dirt: warm ochre with darker worn patches and pale grit.
    dirt0, dirt1, grit = np.array([.62, .46, .30]), np.array([.47, .33, .21]), np.array([.78, .66, .50])
    mix = np.clip((soft - .35) * 2.2, 0, 1)[..., None]
    dirt = dirt0 * (1 - mix) + dirt1 * mix
    speck = (fine > .78)[..., None]
    dirt = np.where(speck, dirt * .6 + grit * .4, dirt) * (.92 + .16 * fine[..., None])
    rake = .04 * np.sin(np.arange(size) / size * 2 * np.pi * 24)[:, None, None]   # furrows along the track (v)
    dirt = np.clip(dirt + rake, 0, 1)
    Image.fromarray((dirt * 255).astype(np.uint8)).save(folder / 'T_HD_Dirt.png')
    # Turf: the island's soft greens, mown in broad stripes.
    g0, g1 = np.array([.42, .58, .30]), np.array([.33, .50, .24])
    mix = np.clip((soft - .3) * 1.8, 0, 1)[..., None]
    stripes = (np.sin(np.arange(size) / size * 2 * np.pi * 2)[None, :, None] > 0) * .05
    grass = np.clip((g0 * (1 - mix) + g1 * mix) * (.9 + .2 * fine[..., None]) + stripes, 0, 1)
    Image.fromarray((grass * 255).astype(np.uint8)).save(folder / 'T_HD_Grass.png')
    return {'HD_Dirt': 'T_HD_Dirt.png', 'HD_Grass': 'T_HD_Grass.png'}

def metadata():
    z0=height();ox,oy=L.ORIGIN
    meshes=[dict(name="SM_HD_"+suffix,at=[0.,0.,0.],yaw=0.,blocks=True) for suffix in ("Ground","Skirt","Track","Rails","Lane","LaneSkirt")]
    for slug,spec in L.STRUCTURES.items():
        x,y=spec["at"];name="SM_HD_"+"".join(part.title() for part in slug.split("_"))
        meshes.append(dict(name=name,slug=slug,at=[x-ox,y-oy,0.],yaw=spec["yaw"],blocks=True))
    data = {
        'key': 'hippodrome', 'asset_root': '/Game/Hippodrome', 'origin': [ox, oy, z0], 'yaw_deg': 0.,
        'meshes': meshes, 'textures': {'HD_Dirt':'T_HD_Dirt.png','HD_Grass':'T_HD_Grass.png'},
        'course': {'origin': [ox, oy], 'half': L.HALF, 'radius': L.RADIUS, 'width': L.WIDTH, 'lap': round(L.LAP, 3),
                   'finish_x': L.FINISH_X, 'direction': 'counter-clockwise', 'z': z0},
        'return': {'at': [L.RETURN['at'][0] - ox, L.RETURN['at'][1] - oy, 0.], 'yaw': L.RETURN['yaw']},
        'clearance': L.clearance(),
    }
    return data

if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument("--textures",required=True)
    textures(parser.parse_args().textures)
