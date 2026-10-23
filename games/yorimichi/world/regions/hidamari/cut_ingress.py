"""The existing Harbor cut's explicit colour/normal storage, without an FBX round trip."""
import numpy as np

from mesh_pieces import values


def prepare(obj):
    """@cc [owner:fontanierh,label:correctness] harbor-cut-ingress-parity
    Preserve the former cut stage's actual FBX ingress semantics: ordered corner
    sRGB BYTE_COLOR and Blender's imported custom-normal storage. Apply only to
    the reconstructed raw Harbor, never to its immutable source data or another
    owner. Positions, polygons, UVs, materials and winding MUST remain unchanged.
    Actual whole-export/import controls MUST establish this boundary; no tolerance
    change or global exporter/importer patch may substitute for parity.
    """
    if obj.name != 'HD_Harbor' or obj.type != 'MESH' or obj.modifiers:
        raise ValueError('Harbor cut ingress requires its explicit static raw source')
    mesh = obj.data
    if len(mesh.color_attributes) != 1 or mesh.color_attributes[0].name != 'Color':
        raise ValueError('Unsupported Harbor cut colour inventory')
    colour = mesh.color_attributes[0]
    if colour.domain not in ('POINT', 'CORNER') or colour.data_type not in ('FLOAT_COLOR', 'BYTE_COLOR'):
        raise ValueError('Unsupported Harbor cut colour representation')
    normals = values(mesh.corner_normals, 'vector', 3)
    colours = values(colour.data, 'color_srgb', 4)
    if colour.domain == 'POINT':
        colours = colours[values(mesh.loops, 'vertex_index', 1, np.int32)]
    mesh.color_attributes.remove(colour)
    layer = mesh.color_attributes.new(name='Color', type='BYTE_COLOR', domain='CORNER')
    layer.data.foreach_set('color_srgb', colours.ravel())
    exact = mesh.attributes.get('custom_normal')
    if exact is None or exact.data_type != 'FLOAT_VECTOR' or exact.domain != 'CORNER':
        raise ValueError('Harbor raw reconstruction lacks exact captured normals')
    mesh.attributes.remove(exact)
    # The former io_scene_fbx reader uses this same setter after mesh.validate.
    if mesh.validate(clean_customdata=False):
        raise ValueError('Harbor source topology required an undeclared repair')
    mesh.normals_split_custom_set(normals.tolist())
