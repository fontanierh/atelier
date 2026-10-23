"""One Brinecove constructor or shared geometry primitive; no sibling generation."""



def paving_grid(x0, x1, y0, y1, tile=6.5):
    """The slab grid paving() lays over a rectangle: (nx, ny, slab width, slab depth)."""
    nx, ny = max(1, round((x1 - x0) / tile)), max(1, round((y1 - y0) / tile))
    return nx, ny, (x1 - x0) / nx, (y1 - y0) / ny
