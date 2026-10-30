# skatepark

Sunset Pier, the 170 by 132 m skate plaza on the sea south of Hidamari: its deck, terraces and bowl, its pilings, the
path in from the coast, its rails, ledges, stairs, banks and transitions, its benches, pavilion and lamps, its stone
gardens and its floor paint and mural. Each piece draws the pier's own concrete, ceramic, steel, timber, basalt or
mural map times its vertex colour, which carries the palette and the baked shading. The deck, pilings, features, path
and furniture are solid with their own triangles; the gardens and the floor paint are not. The trees in the gardens are
in the `forest` region.

Each piece is cut along the tile grid, one prop per tile it reaches, so it streams with its own tile, and `placements.json`
stands each where it was cut from. The path in from the coast road runs over the ground, so the ground owns its
walking surface: `layout.rs` lays the source's own triangles from `path-source.json` as authored surfaces, the paving
and its joints, each drawing the pier's concrete map tinted as its source face is, and the path's props keep only its
skirts, edges and railings.
