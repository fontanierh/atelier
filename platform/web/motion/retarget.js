// Capture the exported rig's rest transforms before display scaling. UniMate
// rotations are deltas in canonical world axes; conjugate into each bone frame.
export function retargetMotion(THREE, motion, name, rest) {
  const times = Array.from({ length: motion.frames }, (_, i) => i / motion.fps);
  const axis = new THREE.Quaternion().fromArray(motion.canonical_to_gltf);
  const invAxis = axis.clone().invert();
  const tracks = [];
  for (let j = 0; j < motion.names.length; j++) {
    const original = motion.names[j];
    const r = rest.get(original);
    if (!r) throw new Error(`Missing skin bone: ${original}`);
    const values = [];
    let previous;
    for (let f = 0; f < motion.frames; f++) {
      const delta = new THREE.Quaternion().fromArray(motion.rotations[f][j]);
      const q = r.localQ
        .clone()
        .multiply(r.worldQ.clone().invert())
        .multiply(axis)
        .multiply(delta)
        .multiply(invAxis)
        .multiply(r.worldQ)
        .normalize();
      // Enforce quaternion continuity for linear glTF interpolation.
      if (previous && previous.dot(q) < 0) q.set(-q.x, -q.y, -q.z, -q.w);
      q.toArray(values, values.length);
      previous = q;
    }
    tracks.push(
      new THREE.QuaternionKeyframeTrack(`${r.name}.quaternion`, times, values),
    );
  }
  const r = rest.get(motion.names[0]);
  const values = [];
  const initial = new THREE.Vector3().fromArray(motion.rest_root);
  for (const pos of motion.root_positions) {
    const delta = new THREE.Vector3()
      .fromArray(pos)
      .sub(initial)
      .applyQuaternion(axis);
    r.worldPos
      .clone()
      .add(delta)
      .applyMatrix4(r.parentInverse)
      .toArray(values, values.length);
  }
  tracks.push(
    new THREE.VectorKeyframeTrack(`${r.name}.position`, times, values),
  );
  // Explicit local-space detail tracks may replace or supplement body tracks.
  // The caller is responsible for their source and provenance.
  for (const [name, quaternions] of Object.entries(motion.local_tracks || {})) {
    const r = rest.get(name);
    if (!r) throw new Error(`Missing reference-detail bone: ${name}`);
    const key = `${r.name}.quaternion`;
    const index = tracks.findIndex((t) => t.name === key);
    const values = quaternions.flat();
    for (let f = 1; f < quaternions.length; f++) {
      if (
        values
          .slice((f - 1) * 4, f * 4)
          .reduce((sum, x, i) => sum + x * values[f * 4 + i], 0) < 0
      )
        for (let i = 0; i < 4; i++) values[f * 4 + i] *= -1;
    }
    const track = new THREE.QuaternionKeyframeTrack(key, times, values);
    if (index >= 0) tracks[index] = track;
    else tracks.push(track);
  }
  return new THREE.AnimationClip(
    name,
    (motion.frames - 1) / motion.fps,
    tracks,
  );
}
