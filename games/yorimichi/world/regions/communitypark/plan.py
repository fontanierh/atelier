"""Draw the actual park and its approach on either generated or painted maps."""
import numpy as np
from communitypark import layout as L
from communitypark.source import scene


def draw(draw, project, scale):
    source = scene()
    triangles = L.place(source.triangles())
    normal = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
    triangles = triangles[normal[:, 2] > np.linalg.norm(normal, axis=1)*1e-4]
    triangles = triangles[np.argsort(triangles[..., 2].mean(1))]
    for triangle in triangles:
        shade = int(np.clip((triangle[:, 2].mean()-42)*2, 0, 25))
        draw.polygon([project(x, y) for x, y, _ in triangle], fill=(187+shade, 184+shade, 175+shade))
    draw.line([project(x, y) for x, y, _ in L.access()], fill=(205, 193, 167), width=max(2, round(L.WIDTH*scale)))
