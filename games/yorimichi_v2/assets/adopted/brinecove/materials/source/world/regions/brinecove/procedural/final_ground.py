"""One Brinecove constructor or shared geometry primitive; no sibling generation."""
from brinecove import rocks


def final_ground(x, y):
    """The ground the game builds (rocks.ground): foam must meet the real shoreline, which the collar moves."""
    return rocks.ground(x, y)
