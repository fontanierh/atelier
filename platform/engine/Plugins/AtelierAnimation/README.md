# AtelierAnimation

Animation nodes for a C++ animation graph (a game's `FAnimInstanceProxy` evaluates them), for characters that follow
the humanoid bone contract (`platform/conventions/rigs/humanoid.toml`). Header-only; experimental (version 0.1). It
depends on AtelierCore.

| Node | What it does | Bones |
|---|---|---|
| `FGroundContactNode` (`GroundContactNode.h`) | Plants the feet on uneven ground: keeps the authored swing clearance, changes only support height and sole angle. Not meant for a character standing on a board. | pelvis, thigh/shin/foot L and R |
| `FSailboatStanceNode` (`SailboatStanceNode.h`) | Seated at a helm with one hand wrapped overhand on a tiller: moves the pelvis to its seat (the spine, chest, neck and head go with it), solves both legs and both arms by two-bone IK to their targets, and wraps the right hand's fingers and thumb around the 3.2 cm handle | pelvis, spine, chest, neck, head, both arms, both legs, right-hand fingers and thumb |

Extension point: a game's animation proxy fills each node's targets every frame and evaluates the node after its pose
blend. The ground contact node takes a ground point and normal per foot and the facing; the sailboat node takes the
pelvis target, a hand target, elbow pole, foot target and knee pole per side, and the tiller grip's axes.
