# Independent coastal constructor parameters

Each JSON file owns one procedural component's random seed and position in that
seed's 32-bit generator stream. A component restores its own position after module
imports; it never executes earlier components to recover ambient state.

These positions were measured against the complete original production order at
`099b747ed`. The guarded nine-component comparison checked every Builder field,
including positions, ordered faces, UVs, material names, normals, anchors and role
flags. All nine comparisons passed, totalling 3,709,092 raw procedural triangles.
That comparison does not certify the new final finishing, exports or native imports.

These are explicit source authoring parameters, not saved build stamps or reusable
artifact certificates. Deliberate constructor edits keep their own parameters
unless the author deliberately changes that component's random context. Changes
to one component must not shift another component's stream position.

| Component | Seed | Prefix words |
|---|---:|---:|
| Rocks | 49157 | 0 |
| Harbor | 49157 | 56721 |
| TownLower | 49157 | 57795 |
| Market | 49157 | 187100 |
| TownUpper | 49157 | 231322 |
| Landmarks | 49157 | 363336 |
| Ships | 49157 | 369795 |
| Props | 49157 | 369795 |
| Understory | 49157 | 370595 |
