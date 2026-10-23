"""Convert completed coastal components into separate bounded mesh inputs, never exports."""


def finish_parts(builder, asset, rim, root, *, paving=None, seam=None):
    import bpy
    from atelier.model_export import mesh_object
    from brinecove import geometry_finish as finish, layout
    from region_mesh_set import plan
    settled = finish.settle(rim)
    parts, outside, drowned, degenerate = finish.split(builder, asset, None if asset == 'Ground' else settled,
        finish.GROUND_REMAP if asset == 'Ground' else None,
        ceiling=finish.paving_limit(paving) if asset == 'Ground' and paving is not None else None)
    objects, metadata = [], {}
    for (_, _, soft, _), part in sorted(parts.items()):
        materials = {}
        for label in sorted(set(part.mats)):
            if label not in layout.COLORS:
                raise ValueError('Unknown coastal material: ' + label)
            material = bpy.data.materials.get('BC_' + label) or bpy.data.materials.new('BC_' + label)
            material.use_nodes = True
            materials[label] = material
        obj = mesh_object(part, materials)
        expected = sum(len(face) - 2 for face in part.faces)
        if sum(len(poly.vertices) - 2 for poly in obj.data.polygons) != expected:
            raise ValueError('Completed coastal part changed while creating its mesh')
        objects.append(obj)
        water = getattr(part, 'parent_water', all(s.startswith(
            ('water', 'mist', 'spray', 'foam', 'waterfall')) for s in part.mats))
        metadata[obj.name] = dict(component=asset, collision=not soft, shadow=not water,
                                  cull_cm=0 if asset in ('Ground', 'Rocks') else 120000)
    counts = dict(outside=outside, drowned=drowned, degenerate=degenerate,
                  raw_triangles=sum(len(face) - 2 for face in builder.faces))
    if seam is not None: counts['seam'] = seam
    value = plan(objects, root, parent='SM_BC_' + asset, metadata=metadata, diagnostics=counts,
                 options=dict(export_apply=True, export_image_format='NONE'))
    return value, counts, parts
