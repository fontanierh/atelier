"""Foliage identity shared by procedural authors, the build owner and runtime registry.

UV channel 5 carries per-face roles without changing the source's visible material.
Channels 0–4 remain available for texture and camera visibility maps. The cooked
slot prefix makes the role discoverable without retaining CPU mesh buffers.
"""
from contextlib import contextmanager
from functools import lru_cache
import re

WORDS = ('tree', 'bush', 'grass', 'foliage', 'leaf', 'leaves', 'palm', 'shrub', 'fern',
         'hedge', 'niwaki', 'azalea', 'flower', 'groundcover', 'plant', 'frond',
         'litter', 'reed', 'vine', 'bamboo', 'bloom', 'cover_grass', 'cover_fern',
         'cover_leaf', 'covergrass', 'coverfern', 'coverleaf', 'pine', 'maple', 'ginkgo')
CHANNEL = 5
MARKER = 73.125
SLOT_PREFIX = 'FoliageRoles_'
AUTHORED_PREFIX = 'FoliageAuthored_'
RIGID_PREFIX = 'FoliageRigid_'
AUTHORED_BUDGET = 12288


class PaletteColour(tuple):
    """An ordinary RGB tuple that retains its author's semantic palette key."""
    def __new__(cls, values, key):
        colour = super().__new__(cls, values)
        colour.foliage_key = key
        return colour


class SurfaceKey(str):
    """An unchanged material-selection key with an explicit per-face semantic role."""
    def __new__(cls, value, role):
        key=super().__new__(cls,value);key.foliage_key=role;return key


@lru_cache(maxsize=4096)
def semantic_tokens(name):
    """Recognize delimited/camel-case words, never substrings such as tree in streets.

    Treehouse and planter name containers rather than plant surfaces. Numbered
    variants and regular plurals retain their plant identity. Runtime uses the
    same token boundaries and plural rule in FoliageSystem.cpp.
    """
    name = re.sub('treehouse|planter', '_', name.rsplit('/', 1)[-1], flags=re.I)
    name = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', name)
    name = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name)
    return frozenset(re.findall('[a-z]+', name.lower()))


@lru_cache(maxsize=4096)
def plant_words(name):
    tokens = semantic_tokens(name)
    return frozenset(word for word in WORDS if any(form in tokens for form in (word, word+'s', word+'es'))
                     or ('_' in word and set(word.split('_')) <= tokens))


def vegetation(name):
    return bool(plant_words(name))


def material_vegetation(name, *, masked=False, foliage=False):
    """Opaque grass paint and rigid plant parts are not leaf surfaces."""
    if foliage:
        return True
    if semantic_tokens(name) & {'bark', 'trunk', 'cane', 'stem', 'wood'}:
        return False
    words = plant_words(name)
    return bool(words and (masked or words-{'grass', 'litter'}))


def category(name):
    words = plant_words(name)
    if words & {'grass', 'groundcover', 'cover_leaf', 'coverleaf', 'coverfern', 'covergrass', 'fern', 'litter', 'reed', 'vine'}:
        return 'groundcover'
    if words & {'bush', 'shrub', 'hedge', 'azalea', 'niwaki', 'bloom'}:
        return 'shrub'
    if 'flower' in words and not words & {'tree', 'palm'}:
        return 'groundcover'
    return 'tree'


def face_role(uv):
    # Legacy FBX import flips V. Values are exact with half precision UVs.
    # 0 rigid, 1 solid canopy, 2 thin groundcover/frond surfaces.
    if len(uv) != 2 or min(abs(uv[1]-MARKER), abs(uv[1]-(1-MARKER))) > .01 or uv[0] not in (0., 1., 2.):
        raise ValueError('Missing or invalid foliage face role')
    return int(uv[0])


def marked_leaf(uv):
    return face_role(uv)>0


def key_role(key):
    if not material_vegetation(key or ''):
        return 0
    return 2 if category(key)=='groundcover' or any(word in key.lower() for word in ('frond','palm_leaf','bamboo_leaf')) else 1


def export_roles(obj, source):
    """Call after all visible UV baking, immediately before FBX export."""
    leaves = [key_role(key) for key in face_keys(source)]
    # An explicit rigid use of a vegetation material (e.g. fruit painted with
    # leaf_sun) also needs certification, even when no plant shares this mesh.
    explicit=getattr(source,'foliage_roles',{})
    keys=getattr(source,'keys',())
    rigid_override=any(i<len(keys) and key_role(keys[i])>0 and key_role(key)==0 for i,key in explicit.items())
    if not any(leaves) and not rigid_override:
        return
    if len(leaves) != len(source.faces) or len(leaves) != len(obj.data.polygons):
        raise ValueError('Foliage face roles lost during geometry assembly: '+source.name)
    layers = obj.data.uv_layers
    if len(layers) > CHANNEL:
        raise ValueError('UV channel 5 is reserved for foliage roles: '+source.name)
    while len(layers) <= CHANNEL:
        layers.new(name='FoliageRoles' if len(layers) == CHANNEL else 'ReservedUV'+str(len(layers)))
    for face, leaf in zip(obj.data.polygons, leaves):
        for index in face.loop_indices:
            layers[CHANNEL].data[index].uv = (float(leaf), MARKER)


@contextmanager
def surfaces(source, key='leaf'):
    """Preserve an explicit role for a group of faces authored with literal colours."""
    start = len(source.faces)
    yield
    if not hasattr(source,'foliage_roles'):
        source.foliage_roles={}
    source.foliage_roles.update({i:key for i in range(start,len(source.faces))})


def face_keys(source):
    """Material selection keys and foliage roles are independent authoring channels."""
    explicit=getattr(source,'foliage_roles',{})
    keys=getattr(source,'keys',())
    return [explicit.get(i,keys[i] if i<len(keys) else None) for i in range(len(source.faces))]


def export_authored(obj):
    """Certify a small, indivisible textured plant prop without guessing at its paint.

    The complete source must fit the shared authored-prop budget. This is an explicit
    source policy, never a missing-classification fallback or a runtime exemption.
    """
    triangles=sum(len(face.vertices)-2 for face in obj.data.polygons)
    if triangles>AUTHORED_BUDGET:
        raise ValueError('Authored foliage prop exceeds triangle budget: '+obj.name)
    layers=obj.data.uv_layers
    if len(layers)>CHANNEL:
        raise ValueError('UV channel 5 is reserved for foliage roles: '+obj.name)
    while len(layers)<=CHANNEL:
        layers.new(name='FoliageAuthored' if len(layers)==CHANNEL else 'ReservedUV'+str(len(layers)))
    for face in obj.data.polygons:
        for index in face.loop_indices:layers[CHANNEL].data[index].uv=(3.,MARKER)
