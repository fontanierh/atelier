# Bounded static model pieces

The shared `atelier.gltf_partition` operation partitions identity-node static GLBs through
the same fixed-cell complete-face mechanism used by the regional Blender exporters. It
preserves every encoded corner position, normal, tangent, colour, custom attribute and UV
channel, triangle winding and material identity. It compacts referenced attribute rows and
keeps image bytes and texture/material references. Unsupported transformed, skinned, animated,
morph, sparse or compressed geometry refuses rather than silently losing semantics.

The ordinary Belmonte builder applies this mechanism to oversized committed model sources,
with a limit of 32,768 triangles per rendered piece. All ten currently oversized committed
models are covered. Small models retain their exact original bytes and names. Piece pivots
stay unchanged; repeated instances share the same models and retain authored transforms.
Material bindings follow the original source slot names. Culling retains the parent model's
span and original full-material instance groups, even when a child omits the differing slot;
shadow/water policy remains inherited. A separately authored whole-model collision
hull belongs to one piece and other rendered pieces disable component collision; without a
separate hull, collision is the union of the unchanged piece faces. Current source membership
retires the old generated parent GLB only after all current members are complete.
Runtime query metadata retains the collidable logical parent's ownership. Gondola clearance
continues to read every visual child while reading the whole authored collision hull only from
its actual collision-enabled owner. Turning collision off on the other rendering children must
not make their visible geometry disappear from route/headroom checks.

Native adoption requires the independently reviewed native-membership retirement change
first: otherwise an obsolete native parent can remain visible to all-content preparation.
The ordinary importer must validate/save all current pieces before retiring those old packages.
Native geometry, material slots, hull references, collision traces and runtime culling/draw-call
effects still require receiving validation. Python source tests do not establish those results
or a frame/build speedup. The current foliage-first receiver must remain unchanged until its
first measured capture and a positive whole-caller/game-free boundary.

This slice does not complete all-region ownership or geometry bounds. In particular, generated
Belmonte NorthApron (162,890 triangles in the observed producer) and NorthCountry (1,114,667)
remain large canonical ground/query surfaces. Map, gondola and planting readers use those
identities. They need published final-surface query products separated from bounded native
render/collision pieces, rather than a blind rename or an unreported exemption. Other static
FBX/GLB producers and ground owners must be audited and migrated through the same normal graph.
Natural/final terrain, authored road/pad constraints, independent model/material generation and
placement/footprint consumers remain explicit follow-up work.
