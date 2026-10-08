// Compare all rendered body-joint transforms against independently evaluated FK.
import fs from "node:fs";
import path from "node:path";
import * as THREE from "three";
import { retargetMotion } from "../../../platform/web/motion/retarget.js";
import { glbNodes, captureRest } from "../../../platform/web/motion/rest.js";
const root = process.argv[2] || "build/yorimichi/unimate";
const buffer = fs.readFileSync(path.join(root, "assets/fox.glb"));
const gltf = JSON.parse(
  buffer.subarray(20, 20 + buffer.readUInt32LE(12)).toString(),
);
const { nodes, scene } = glbNodes(THREE, gltf);
const rest = captureRest(THREE, nodes);
let worst = 0,
  count = 0;
for (const id of fs.readdirSync(path.join(root, "results"))) {
  const folder = path.join(root, "results", id);
  if (!fs.existsSync(path.join(folder, "expected-joints.json"))) continue;
  const motion = JSON.parse(fs.readFileSync(path.join(folder, "motion.json")));
  const expected = JSON.parse(
    fs.readFileSync(path.join(folder, "expected-joints.json")),
  );
  const clip = retargetMotion(THREE, motion, "QA", rest);
  const mixer = new THREE.AnimationMixer(scene);
  const action = mixer.clipAction(clip).play();
  for (let f = 0; f < motion.frames; f++) {
    mixer.setTime(f / motion.fps);
    scene.updateMatrixWorld(true);
    // Looping at exactly duration resets to frame zero; test the last frame just before its endpoint.
    if (f === motion.frames - 1) {
      action.setLoop(THREE.LoopOnce, 1);
      action.clampWhenFinished = true;
      mixer.setTime(f / motion.fps);
      scene.updateMatrixWorld(true);
    }
    for (let j = 0; j < motion.names.length; j++) {
      const n = nodes[gltf.nodes.findIndex((n) => n.name === motion.names[j])];
      const actual = n.getWorldPosition(new THREE.Vector3());
      const error = actual.distanceTo(
        new THREE.Vector3().fromArray(expected[f][j]),
      );
      worst = Math.max(worst, error);
      count++;
      if (error > 0.0001)
        throw new Error(
          `${id}, frame ${f}, ${motion.names[j]}: retarget error ${error} m`,
        );
    }
  }
  mixer.stopAllAction();
  mixer.uncacheRoot(scene);
}
if (!count) throw new Error("No expected joint samples found; run the generator verifier first");
console.log(
  `Verified ${count} body-joint samples; max retarget error ${(worst * 1000).toFixed(5)} mm`,
);
