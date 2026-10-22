"""Brinecove face-role transport around the shared model exporter."""
from atelier import model_export
from atelier.gltf import glb_parts
import foliage_roles

glb_info = model_export.glb_info


def mesh_object(builder, materials):
    obj = model_export.mesh_object(builder, materials)
    foliage_roles.export_roles(obj, builder)
    return obj


def export(obj, path):
    model_export.export(obj, path)
    if len(obj.data.uv_layers) > foliage_roles.CHANNEL:
        doc, _ = glb_parts(path.read_bytes())
        assert all('TEXCOORD_5' in primitive['attributes']
                   for mesh in doc['meshes'] for primitive in mesh['primitives']), \
            ('Foliage UV5 lost in GLB export', obj.name)
