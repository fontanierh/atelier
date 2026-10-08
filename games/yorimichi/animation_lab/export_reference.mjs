// Sample the owned Run clip into UniMate's canonical rest-relative space.
// No textures, renders, or third-party motion data are involved.
import fs from "node:fs";
import path from "node:path";
import * as THREE from "three";
import { closeLoop } from "../../../platform/web/motion/loop.js";
import { glbNodes } from "../../../platform/web/motion/rest.js";
const root = process.argv[2] || "build/yorimichi/unimate";
const bytes = fs.readFileSync(path.join(root, "assets/fox.glb"));
const jsonSize = bytes.readUInt32LE(12);
const gltf = JSON.parse(bytes.subarray(20, 20 + jsonSize).toString());
function accessor(index) {
  const a = gltf.accessors[index],
    v = gltf.bufferViews[a.bufferView];
  if (a.componentType !== 5126)
    throw new Error("Expected float animation data");
  const width = { SCALAR: 1, VEC3: 3, VEC4: 4 }[a.type];
  const offset = v.byteOffset + (a.byteOffset || 0);
  return Array.from({ length: a.count * width }, (_, i) =>
    bytes.readFloatLE(28 + jsonSize + offset + i * 4),
  );
}
const { nodes, scene } = glbNodes(THREE, gltf);
const restWorld = nodes.map((o) =>
  o.getWorldQuaternion(new THREE.Quaternion()),
);
const a = gltf.animations.find((a) => a.name === "Fox_Run");
const tracks = a.channels.map((channel) => {
  const sampler = a.samplers[channel.sampler];
  if (![undefined, "LINEAR", "STEP"].includes(sampler.interpolation))
    throw new Error("Unsupported animation interpolation");
  const property = {
    translation: "position",
    rotation: "quaternion",
    scale: "scale",
  }[channel.target.path];
  const Track =
    property === "quaternion"
      ? THREE.QuaternionKeyframeTrack
      : THREE.VectorKeyframeTrack;
  return new Track(
    `${nodes[channel.target.node].name}.${property}`,
    accessor(sampler.input),
    accessor(sampler.output),
    sampler.interpolation === "STEP"
      ? THREE.InterpolateDiscrete
      : THREE.InterpolateLinear,
  );
});
const manifest = JSON.parse(
  fs.readFileSync("games/yorimichi/assets/characters/fox-hunter/manifest.json"),
);
const period = manifest.clips.Run.seconds;
const clip = closeLoop(THREE, new THREE.AnimationClip("Fox_Run", -1, tracks), period);
const mixer = new THREE.AnimationMixer(scene);
mixer.clipAction(clip).play();
const rig = JSON.parse(fs.readFileSync(path.join(root, "assets/rig.json")));
const ids = rig.names.map((name) =>
  gltf.nodes.findIndex((n) => n.name === name),
);
const axis = new THREE.Quaternion(0, Math.SQRT1_2, 0, Math.SQRT1_2);
const inverse = axis.clone().invert();
const center = new THREE.Vector3().fromArray(rig.canonical_center);
const detailIds = gltf.nodes
  .map((n, i) => (/mixamorig:(Left|Right)Hand/.test(n.name) ? i : -1))
  .filter((i) => i >= 0);
const positions = [],
  rotations = [],
  details = Object.fromEntries(detailIds.map((i) => [gltf.nodes[i].name, []]));
for (let f = 0; f < 61; f++) {
  mixer.setTime(f / 30);
  scene.updateMatrixWorld(true);
  const world = ids.map((i) =>
    nodes[i]
      .getWorldQuaternion(new THREE.Quaternion())
      .multiply(restWorld[i].clone().invert()),
  );
  rotations.push(
    world.map((q, j) => {
      const p = rig.parents[j];
      const local = p < 0 ? q.clone() : world[p].clone().invert().multiply(q);
      return inverse
        .clone()
        .multiply(local)
        .multiply(axis)
        .normalize()
        .toArray();
    }),
  );
  positions.push(
    ids.map((i) =>
      nodes[i]
        .getWorldPosition(new THREE.Vector3())
        .applyQuaternion(inverse)
        .sub(center)
        .toArray(),
    ),
  );
  for (const i of detailIds)
    details[gltf.nodes[i].name].push(nodes[i].quaternion.toArray());
}
const output = {
  reference_clip: "Fox_Run",
  names: rig.names,
  positions,
  rotations,
  detail_tracks: details,
  fps: 30,
  cycle_frames: Math.round(period * 30),
  period,
  travel_speed: manifest.clips.Run.travel_speed_units_per_s,
  source_sha256: rig.source_sha256,
};
fs.writeFileSync(
  path.join(root, "assets/run-reference.json"),
  JSON.stringify(output),
);
console.log(
  `Sampled ${clip.name}: ${output.cycle_frames}-frame cycle, ${positions.length} reference poses, ${detailIds.length} hand detail tracks`,
);
