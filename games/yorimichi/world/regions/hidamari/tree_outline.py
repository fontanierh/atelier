"""Existing leaf-outline reduction, independent of exports or region assembly."""
from village import mesh as village

from hidamari.tree_policy import CORNERS


def simplified(source, level):
    target = village.Mesh(source.name + f'_LOD{level}')
    leaf_faces = 0
    for face in source.faces:
        selected = face
        if len(face) == 11:
            # The generator emits front then reversed back faces. Select matching
            # physical corners on both sides, so the two outlines remain closed.
            corners = CORNERS[level]
            if leaf_faces % 2:
                corners = tuple(10-i for i in reversed(corners))
            selected = tuple(face[i] for i in corners)
            leaf_faces += 1
        first = len(target.vertices)
        target.vertices.extend(source.vertices[i] for i in selected)
        target.colors.extend(source.colors[i] for i in selected)
        target.faces.append(tuple(range(first, len(target.vertices))))
    expected = 15 * (310 if source.name == 'HD_ArcadeTree' else 210) * 2
    assert leaf_faces == expected, (source.name, 'unexpected leaf topology', leaf_faces)
    assert len(target.faces) == len(source.faces)
    # Front/back pairs must share exactly the same positions in reverse order.
    # Other scene polygons can have this corner count; select source leaf slots.
    leaves = [target.faces[i] for i, f in enumerate(source.faces) if len(f) == 11]
    for a, b in zip(leaves[::2], leaves[1::2]):
        assert [target.vertices[i] for i in a] == [target.vertices[i] for i in reversed(b)]
    return target, leaf_faces // 2
