// Rest transforms for retargetMotion. Capture them before display scaling.
// One Object3D per glTF node, without meshes or a loader: enough to sample a rig.
// Names drop colons as GLTFLoader's track names do; userData.name keeps the original.
export function glbNodes(THREE, gltf) {
  const nodes = gltf.nodes.map((n) => {
    const o = new THREE.Object3D();
    o.name = n.name.replaceAll(":", "");
    o.userData.name = n.name;
    if (n.matrix) {
      o.matrix.fromArray(n.matrix);
      o.matrix.decompose(o.position, o.quaternion, o.scale);
    } else {
      if (n.translation) o.position.fromArray(n.translation);
      if (n.rotation) o.quaternion.fromArray(n.rotation);
      if (n.scale) o.scale.fromArray(n.scale);
    }
    return o;
  });
  gltf.nodes.forEach((n, i) =>
    n.children?.forEach((j) => nodes[i].add(nodes[j])),
  );
  const scene = new THREE.Group();
  gltf.scenes[gltf.scene || 0].nodes.forEach((i) => scene.add(nodes[i]));
  scene.updateMatrixWorld(true);
  return { nodes, scene };
}

// The rest Map retargetMotion reads, for objects whose world matrices are current.
// keys(o) lists the source names each record answers to (default: the original name).
export function captureRest(
  THREE,
  objects,
  keys = (o) => [o.userData.name || o.name],
) {
  const rest = new Map();
  for (const o of objects) {
    const record = {
      name: o.name,
      localQ: o.quaternion.clone(),
      worldQ: o.getWorldQuaternion(new THREE.Quaternion()),
      worldPos: o.getWorldPosition(new THREE.Vector3()),
      parentInverse: o.parent.matrixWorld.clone().invert(),
    };
    for (const key of keys(o)) rest.set(key, record);
  }
  return rest;
}
