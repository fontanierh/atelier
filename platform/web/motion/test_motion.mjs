// Pass the installed three.module.js path; the helper uses the caller's Three.js.
import assert from "node:assert/strict";
import path from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";
import { retargetMotion } from "./retarget.js";
import { closeLoop } from "./loop.js";
import { glbNodes, captureRest } from "./rest.js";

if (!process.argv[2]) throw new Error("Pass the path to an installed three.module.js");
const THREE = await import(pathToFileURL(path.resolve(process.argv[2])).href);

test("retargets a differently named rig under a rotated, scaled parent", () => {
  const scene = new THREE.Group();
  scene.position.set(3, 2, -1);
  scene.rotation.set(.2, .3, .4);
  scene.scale.setScalar(2);
  const root = new THREE.Bone(), tip = new THREE.Bone();
  root.name = "pelvis";
  tip.name = "limb";
  root.position.set(0, 1, 0);
  root.rotation.set(.1, -.2, .3);
  tip.position.set(0, 1, 0);
  tip.rotation.set(.2, .5, -.1);
  scene.add(root);
  root.add(tip);
  scene.updateMatrixWorld(true);
  const rest = new Map([root, tip].map((bone) => [bone.name, {
    name: bone.name, localQ: bone.quaternion.clone(),
    worldQ: bone.getWorldQuaternion(new THREE.Quaternion()),
    worldPos: bone.getWorldPosition(new THREE.Vector3()),
    parentInverse: bone.parent.matrixWorld.clone().invert(),
  }]));
  const axis = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), Math.PI / 2);
  const delta = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), .6);
  const expectedRotation = axis.clone().multiply(delta).multiply(axis.clone().invert()).multiply(rest.get("limb").worldQ);
  const expectedPosition = rest.get("pelvis").worldPos.clone().add(new THREE.Vector3(1, 0, 0).applyQuaternion(axis));
  const motion = { names: ["pelvis", "limb"], frames: 2, fps: 30,
    rotations: [[[0, 0, 0, 1], delta.toArray()], [[0, 0, 0, -1], delta.toArray().map((v) => -v)]],
    root_positions: [[1, 0, 0], [1, 0, 0]], rest_root: [0, 0, 0], canonical_to_gltf: axis.toArray() };
  const clip = retargetMotion(THREE, motion, "synthetic", rest);
  assert.equal(clip.tracks.length, 3);
  const mixer = new THREE.AnimationMixer(scene);
  mixer.clipAction(clip).play();
  mixer.setTime(0);
  scene.updateMatrixWorld(true);
  assert.ok(tip.getWorldQuaternion(new THREE.Quaternion()).angleTo(expectedRotation) < 1e-6);
  assert.ok(root.getWorldPosition(new THREE.Vector3()).distanceTo(expectedPosition) < 1e-6);
  for (const track of clip.tracks.filter((t) => t.ValueTypeName === "quaternion")) {
    assert.ok(new THREE.Quaternion().fromArray(track.values).dot(new THREE.Quaternion().fromArray(track.values, 4)) > .999);
  }
  const local = [0, 0, 0, 1];
  motion.local_tracks = { limb: [local, local] };
  const override = retargetMotion(THREE, motion, "detail", rest);
  assert.equal(override.tracks.length, 3);
  assert.deepEqual(Array.from(override.tracks.find((t) => t.name === "limb.quaternion").values), [...local, ...local]);
});

test("builds glTF nodes and captures rest records under every key the caller names", () => {
  const gltf = { scene: 0, scenes: [{ nodes: [0] }], nodes: [
    { name: "rig:hips", translation: [0, 1, 0], rotation: [0, Math.SQRT1_2, 0, Math.SQRT1_2], scale: [2, 2, 2], children: [1] },
    { name: "rig:spine", matrix: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, .5, 0, 1] },
  ] };
  const { nodes, scene } = glbNodes(THREE, gltf);
  assert.deepEqual(nodes.map((o) => [o.name, o.userData.name]), [["righips", "rig:hips"], ["rigspine", "rig:spine"]]);
  assert.equal(nodes[1].parent, nodes[0]);
  assert.equal(nodes[0].parent, scene);
  assert.ok(nodes[1].getWorldPosition(new THREE.Vector3()).distanceTo(new THREE.Vector3(0, 2, 0)) < 1e-6);
  const rest = captureRest(THREE, nodes);
  assert.deepEqual([...rest.keys()], ["rig:hips", "rig:spine"]);
  const spine = rest.get("rig:spine");
  assert.equal(spine.name, "rigspine");
  assert.ok(spine.worldQ.angleTo(nodes[0].quaternion) < 1e-6);
  assert.ok(spine.parentInverse.clone().multiply(nodes[0].matrixWorld).equals(new THREE.Matrix4()));
  const aliased = captureRest(THREE, nodes, (o) => [o.userData.name, o.name]);
  assert.equal(aliased.size, 4);
  assert.equal(aliased.get("rigspine"), aliased.get("rig:spine"));
});

test("restores a loop endpoint at its supplied period without changing the source", () => {
  const source = new THREE.AnimationClip("stride", -1, [
    new THREE.VectorKeyframeTrack("pelvis.position", [0, .1], [0, 0, 0, 0, 1, 0]),
  ]);
  const closed = closeLoop(THREE, source, .2);
  assert.equal(closed.duration, .2);
  assert.equal(closed.tracks[0].times.length, 3);
  assert.deepEqual(Array.from(closed.tracks[0].values), [0, 0, 0, 0, 1, 0, 0, 0, 0]);
  assert.equal(source.tracks[0].times.length, 2);
});
