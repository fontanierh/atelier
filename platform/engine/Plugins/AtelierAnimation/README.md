# AtelierAnimation

Animation nodes for a C++ animation graph (a game's `FAnimInstanceProxy` evaluates them), for characters that follow
the humanoid bone contract (`platform/conventions/rigs/humanoid.toml`). Header-only; experimental.

| Node | What it does | Bones |
|---|---|---|
| `FGroundContactNode` | Plants the feet on uneven ground: keeps the authored swing clearance, changes only support height and sole angle | pelvis, thigh/shin/foot L and R |
| `FSkateRiderNode` | Carries feet and hands with a moving deck (board pitch and lean), two-bone IK per limb | feet, hands and their chains |
| `FSailboatStanceNode` | Seated at a helm with one hand wrapped on a tiller | legs, the tiller arm and fingers |

Extension point: a game's animation proxy fills each node's targets every frame (ground points and normals, the deck
transform, the tiller grip) and evaluates it after its pose blend.
