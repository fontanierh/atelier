// Source loop exports omit their duplicate final frame. Restore that endpoint
// at the manifest period so playback uses the intended cadence and closes.
export function closeLoop(THREE, clip, period) {
  const tracks = clip.tracks.map((track) => {
    const size = track.getValueSize();
    const count = Array.from(track.times).filter(
      (t) => t < period - 1e-5,
    ).length;
    return new track.constructor(
      track.name,
      [...track.times.slice(0, count), period],
      [...track.values.slice(0, count * size), ...track.values.slice(0, size)],
      THREE.InterpolateLinear,
    );
  });
  return new THREE.AnimationClip(clip.name, period, tracks);
}
