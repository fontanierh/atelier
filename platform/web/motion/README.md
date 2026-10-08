# Motion conversion helpers (experimental)

Small browser/Node helpers for applying canonical world-axis rotation deltas to an existing skin and restoring
an authored loop's duplicate endpoint. They accept the caller's Three.js namespace so they use the same classes
as its viewer/exporter, with no dependency on a character or a game package. The
[local UniMate runner](../../studio/atelier/ai/unimate/README.md) and the
[Kimodo adapter](../../studio/atelier/ai/kimodo/README.md) publish the motion representation they read.

## Use

```js
import * as THREE from 'three';
import { retargetMotion } from './retarget.js';
import { closeLoop } from './loop.js';
import { glbNodes, captureRest } from './rest.js';

const { nodes, scene } = glbNodes(THREE, gltfJson); // or a GLTFLoader scene
const rest = captureRest(THREE, nodes);
const clip = retargetMotion(THREE, motion, 'generated-take', rest);
const originalLoop = closeLoop(THREE, originalClip, sourcePeriodSeconds);
```

Capture `rest` before display scaling. It is a Map keyed by original source bone name:

| Field | Three.js value |
| --- | --- |
| `name` | Target track/bone name, sanitized consistently with the target scene |
| `localQ` | Rest local quaternion |
| `worldQ` | Rest world quaternion |
| `worldPos` | Rest world position |
| `parentInverse` | Inverse parent rest world matrix |

`captureRest(THREE, objects, keys)` builds it from objects whose world matrices are current; `keys(o)` lists the
source names each record answers to (default `[o.userData.name || o.name]`, the unsanitized glTF name), so a caller can
add another spelling of the same bone. `glbNodes(THREE, gltfJson)` builds one `Object3D` per node of a parsed GLB's
JSON chunk, without meshes or a loader, and returns `{nodes, scene}` with world matrices updated: enough to sample a rig
in Node. Node names lose their colons, as GLTFLoader's do, and keep the original in `userData.name`.

`motion` supplies source `names` (root first), `frames`, `fps`, per-frame/per-joint xyzw canonical world-axis rotation
deltas, `root_positions`, `rest_root`, and a unit xyzw `canonical_to_gltf` rotation. The helper conjugates deltas into
each bone's rest frame, translates the root through its parent matrix, and enforces quaternion sign continuity.
Optional `local_tracks` maps bone names to per-frame local xyzw quaternions, replacing or supplementing body tracks.
The caller owns their source/provenance. Missing target bones fail explicitly.

`closeLoop` returns a new clip, retaining samples before the supplied period and copying the first transform to the
endpoint. It does not synthesize velocity continuity or improve contacts. Applying it to generated motion is a
caller policy; a successful conversion does not establish motion quality.

## Tests

To run the synthetic-rig tests, pass an installed Three.js module path:

```sh
node platform/web/motion/test_motion.mjs "$THREE_MODULE_PATH"
```

Tests exercise rest capture from glTF nodes (matrix and TRS nodes, sanitized names, caller keys), a differently named
rig under a rotated/scaled parent, non-identity rest rotations and canonical axes, root translation, antipodal
quaternion continuity, local detail overrides, and loop endpoint/source preservation.
