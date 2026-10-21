"""Current native readback for a saved foliage geometry candidate; never saves assets."""
import math


def matches(mesh, source, replacements, canopies, triangles, screens, geometry, path,
            *, editor, snapshot, digest, refusal=None):
    """@cc [owner:fontanierh,label:correctness] foliage-saved-geometry-admission
    Saved variants MUST match current expected geometry, source-slot names/manual UV density overrides, material
    bindings, prepared LOD settings and screens. Missing readback MUST be a miss. This
    check MUST NOT save a candidate or publish a complete foliage registry.
    """
    def miss(reason):
        if refusal:
            refusal(reason)
        return False

    try:
        if not mesh or mesh.get_num_lods() != len(triangles):
            return miss("LOD count")
        if [mesh.get_num_triangles(i) for i in range(len(triangles))] != triangles:
            return miss("triangle counts")
        actual = list(editor.get_lod_screen_sizes(mesh))
        if len(actual) != len(screens) or any(not math.isfinite(a) or abs(a-b) > 1.e-6
                                            for a, b in zip(actual, screens)):
            return miss("LOD screens")
        originals = source.get_editor_property('static_materials')
        slots = mesh.get_editor_property('static_materials')
        if len(replacements) != len(originals) or len(slots) != len(originals)+2:
            return miss("material slot count")
        for index, original in enumerate(originals):
            if mesh.get_material(index) != replacements[index]:
                return miss("source material binding")
            for key in ('material_slot_name', 'imported_material_slot_name'):
                if slots[index].get_editor_property(key) != original.get_editor_property(key):
                    return miss("source slot metadata: " + key)
            # Editor material assignment rebuilds automatic streaming densities
            # from the variant's geometry. Explicit artist overrides must survive;
            # exact UV corner coordinates are checked by the native digest below.
            current_uv = slots[index].get_editor_property('uv_channel_data')
            source_uv = original.get_editor_property('uv_channel_data')
            override = source_uv.get_editor_property('override_densities')
            densities = list(current_uv.get_editor_property('local_uv_densities'))
            if (current_uv.get_editor_property('override_densities') != override or len(densities) != 4 or
                    any(not math.isfinite(value) or value < 0 for value in densities) or
                    (override and densities != list(source_uv.get_editor_property('local_uv_densities')))):
                return miss("source slot UV density override")
        for index, (name, material) in enumerate(zip(('CanopyNear', 'CanopyFar'), canopies), len(originals)):
            if str(slots[index].get_editor_property('material_slot_name')) != name or mesh.get_material(index) != material:
                return miss("canopy material binding")
        for key, value in (('bAutoComputeLODScreenSize', False), ('bGenerateMeshDistanceField', False),
                           ('LightMapCoordinateIndex', 0)):
            if mesh.get_editor_property(key) != value:
                return miss("mesh setting: " + key)
        expected_build = dict(recompute_normals=False, recompute_tangents=True, remove_degenerates=False,
                              generate_lightmap_u_vs=False, use_full_precision_u_vs=True,
                              distance_field_resolution_scale=0., max_lumen_mesh_cards=0)
        for index in range(len(triangles)):
            build = editor.get_lod_build_settings(mesh, index)
            if any(build.get_editor_property(key) != value for key, value in expected_build.items()):
                return miss("LOD build settings")
            reduction = editor.get_lod_reduction_settings(mesh, index)
            if any(reduction.get_editor_property(key) != value for key, value in
                   dict(base_lod_model=index, percent_triangles=1., percent_vertices=1., max_deviation=0.).items()):
                return miss("LOD reduction settings")
        if not snapshot(mesh, str(path)):
            return miss("native geometry snapshot")
        return True if digest(path) == geometry else miss("geometry digest")
    except Exception as error:  # Unreal reflection reports unavailable properties as plain Exception.
        return miss("readback: " + type(error).__name__ + ": " + str(error))
    finally:
        path.unlink(missing_ok=True)
