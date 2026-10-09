// Ski lab terrain: a heightfield park. x runs down the fall line, y to the left, z up, metres.
// Jumps are designed from the speeds they must work for: the table is long enough that the slowest rider clears the
// knuckle, and the landing long enough that the fastest still lands on it. Where the landing ends below the slope,
// the whole hill steps down there, as parks do: gentle decks between features, the drop taken on the landings.

const rad = (deg) => deg * Math.PI / 180;
const smoothstep = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
const softplus = (x, width) => x / width > 30 ? x : width * Math.log1p(Math.exp(x / width));
const GRAVITY = 9.81;

export const PARK = {
  slopeDeg: 9,
  startX: -30,
  finishX: 380,
  halfWidth: 32,
  jumps: [
    { name: 'Small', x: 60, y: 0, height: 0.9, lipDeg: 22, landingDeg: 28, speeds: [7, 11], width: 8 },
    { name: 'Medium', x: 150, y: 0, height: 1.4, lipDeg: 25, landingDeg: 31, speeds: [9, 13], width: 9 },
    { name: 'Large', x: 260, y: 0, height: 1.9, lipDeg: 28, landingDeg: 34, speeds: [11, 15], width: 10 },
  ],
  rollers: { y: -16, from: 40, to: 300, spacing: 14, height: 0.9, width: 7 },
};

// Where a rider leaving the lip at `speed` comes down, as u along the profile (point mass, no drag).
export function touchdown(profile, speed) {
  const { lipU, tableEnd, lipRad, landingRad } = profile;
  const table = tableEnd - lipU, tl = Math.tan(landingRad);
  const b = speed * (Math.sin(lipRad) + tl * Math.cos(lipRad));
  // Over the table (level with the lip) or onto the landing line, whichever it meets first.
  const overTable = lipU + speed * Math.cos(lipRad) * 2 * speed * Math.sin(lipRad) / GRAVITY;
  if (overTable <= tableEnd) return overTable;
  const t = (b + Math.sqrt(b * b - 2 * GRAVITY * tl * table)) / GRAVITY;
  return lipU + speed * Math.cos(lipRad) * t;
}

// Offsets above the base plane along u (metres from the in-run start), sampled every 5 cm.
export function jumpProfile(jump, slopeDeg) {
  const tb = Math.tan(rad(slopeDeg));
  const lipRad = rad(jump.lipDeg), landingRad = rad(jump.landingDeg);
  const [slow, fast] = jump.speeds;
  const lipU = 2 * jump.height / (Math.tan(lipRad) + tb);
  const tableEnd = lipU + Math.max(2, slow * slow * Math.sin(2 * lipRad) / GRAVITY);
  const knuckle = jump.height + (tableEnd - lipU) * tb;
  const drop = Math.tan(landingRad) - tb;
  const profile = { lipU, tableEnd, knuckle, lipRad, landingRad };
  const landingEnd = touchdown(profile, fast) + 4;
  const bottom = knuckle - (landingEnd - tableEnd) * drop;
  const runout = 12;
  const length = landingEnd + runout;
  const knuckleRound = 1.2;
  const table = (u) => jump.height + (u - lipU) * tb;
  const landing = (u) => knuckle - (u - tableEnd) * drop;
  const at = (u) => {
    if (u <= 0 || u >= length) return 0;
    if (u <= lipU) return jump.height * (u / lipU) ** 2;
    if (Math.abs(u - tableEnd) < knuckleRound) {
      // Quadratic Bezier over the knuckle's corner; evenly spaced control points keep t linear in u.
      const t = (u - (tableEnd - knuckleRound)) / (2 * knuckleRound);
      return (1 - t) ** 2 * table(tableEnd - knuckleRound) + 2 * (1 - t) * t * knuckle + t * t * landing(tableEnd + knuckleRound);
    }
    if (u <= tableEnd) return table(u);
    if (u <= landingEnd) return landing(u);
    // Run-out: the slope eases steadily from the landing's back to the base slope.
    const d = u - landingEnd;
    return bottom - drop * d + drop * d * d / (2 * runout);
  };
  // The step the hill takes around the landing, at every y; the profile is drawn relative to it.
  const step = Math.min(0, bottom - drop * runout / 2);
  const stepFrom = tableEnd, stepTo = length;
  const stepAt = (u) => step * smoothstep(stepFrom, stepTo, u);
  const samples = new Float64Array(Math.ceil(length / 0.05) + 2);
  for (let i = 0; i < samples.length; i++) samples[i] = at(i * 0.05) - stepAt(i * 0.05);
  return { ...profile, samples, length, landingEnd, bottom, step, stepAt };
}

function sampled(profile, u) {
  if (u <= 0 || u >= profile.length - 0.1) return 0;
  const i = u / 0.05, j = Math.floor(i);
  return profile.samples[j] + (profile.samples[j + 1] - profile.samples[j]) * (i - j);
}

export function makePark(park = PARK) {
  const tb = Math.tan(rad(park.slopeDeg));
  const jumps = park.jumps.map((jump) => ({ ...jump, profile: jumpProfile(jump, park.slopeDeg) }));
  const r = park.rollers;
  const base = (x) => {
    let z = -tb * (softplus(x, 8) - softplus(x - park.finishX, 10));
    for (const jump of jumps) z += jump.profile.stepAt(Math.min(x - jump.x, jump.profile.length));
    return z;
  };
  const height = (x, y) => {
    let z = base(x);
    for (const jump of jumps) {
      const across = 1 - smoothstep(jump.width / 2, jump.width / 2 + 3, Math.abs(y - jump.y));
      if (across > 0) z += across * sampled(jump.profile, x - jump.x);
    }
    const lane = 1 - smoothstep(r.width / 2, r.width / 2 + 2, Math.abs(y - r.y));
    if (lane > 0 && x > r.from && x < r.to) {
      z += lane * r.height * 0.5 * (1 - Math.cos(2 * Math.PI * (x - r.from) / r.spacing));
    }
    // Banks at the edges keep riders in the park.
    const edge = Math.abs(y) - park.halfWidth;
    if (edge > 0) z += 0.04 * edge * edge;
    if (x < park.startX) z += 0.2 * (park.startX - x) ** 2;
    return z;
  };
  const e = 0.03;
  const normal = (x, y) => {
    const dx = (height(x + e, y) - height(x - e, y)) / (2 * e);
    const dy = (height(x, y + e) - height(x, y - e)) / (2 * e);
    const l = Math.hypot(dx, dy, 1);
    return [-dx / l, -dy / l, 1 / l];
  };
  return { height, normal, base, jumps, park, start: [park.startX + 18, 0] };
}

// A plain slope for tests: constant angle along x, flat across.
export function makeSlope(slopeDeg = 15) {
  const t = Math.tan(rad(slopeDeg));
  const l = Math.hypot(t, 1);
  return { height: (x) => -t * x, normal: () => [t / l, 0, 1 / l] };
}
