# Superseded native model membership

Belmonte and Brinecove reserve their respective `Meshes` folders and `SM_BM_` /
`SM_BC_` model-name prefixes for generated region models and collision companions.
The importer inventories this exact generated membership before work. After every
current model has imported or passed current reuse validation and saved successfully,
`atelier.native_membership` retires only prior generated packages absent from the
complete current model list. Belmonte includes its separately imported collision hulls.
Other folders, prefixes and current pieces are excluded. External package references
refuse retirement before any deletion; editor deletion failures prevent task success.

This matters when a large parent is replaced by bounded pieces: leaving its old native
package would let whole-content foliage discovery prepare the obsolete monolith again.
The same membership protocol applies to future generated native collections. It does
not collect cache blobs or unrelated checkout files. Pure/fake-editor regression checks
cover complete membership and late import failures; actual native retirement remains
an adoption check at a stopped producer boundary, after the current first-game run.
