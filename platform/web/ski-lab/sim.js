// Ski lab physics: one rigid skier (rider and skis together) on a heightfield. Metres, seconds, kilograms;
// z up. Body axes: x forward along the skis, y left, z up. README.md describes the model.

export const SETTINGS = {
  dt: 1 / 600,
  gravity: 9.81,
  mass: 75,
  // Skis
  skiLength: 1.75,
  sidecutRadius: 17,
  contactPoints: 7,
  // Snow: totals over the contact points
  snowStiffness: 150000,
  snowDamping: 4700,
  glideFriction: 0.05,
  slipSpeed: 0.15,
  flatGrip: 0.35,
  edgeGrip: 1.1,
  edgeFullDeg: 20,
  carveOnsetDeg: 15,
  // Air
  airDensity: 1.1,
  dragStand: 0.55,
  dragTuck: 0.25,
  // Body
  inertiaStand: [12, 12.5, 1.9],
  inertiaTuck: [4.5, 5, 1.3],
  standHeight: 0.92,
  crouchDrop: 0.38,
  rideCrouch: 0.25,
  legRate: 4.2,
  flexRate: 1.6,
  recoverRate: 0.8,
  legAccel: 45,
  legForceMax: 3.6,
  absorbStart: 2.0,
  absorbSoftness: 9,
  footShift: 0.12,
  hipRadius: 0.18,
  headRadius: 0.12,
  headHeight: 0.62,
  // Rider skill
  maxEdgeDeg: 58,
  maxAngulationDeg: 28,
  angulationRate: 5,
  balanceReach: 0.18,
  balanceGain: 5,
  balanceDamping: 16,
  maxRollRate: 1.6,
  edgeHold: 0.25,
  pivotRate: 1.6,
  spinRate: 8.5,
  pivotGrip: 0.25,
  coilRate: 3,
  brakeLeanDeg: 32,
  // Assists, 0 is honest physics
  balanceAssist: 0.85,
  airAssist: 0.35,
  spinAssist: 0.2,
};

export const GRABS = ['', 'Mute', 'Safety'];

// Vectors and quaternions ([w, x, y, z]).
const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const scale = (a, s) => [a[0] * s, a[1] * s, a[2] * s];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const length = (a) => Math.hypot(a[0], a[1], a[2]);
const normalize = (a) => { const l = length(a); return l > 1e-12 ? scale(a, 1 / l) : [0, 0, 0]; };
const clamp = (x, lo, hi) => Math.min(hi, Math.max(lo, x));
const lerp = (a, b, t) => a + (b - a) * t;
const smoothstep = (a, b, x) => { const t = clamp((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };
const approach = (x, target, rate) => x + clamp(target - x, -rate, rate);
const rad = (deg) => deg * Math.PI / 180;

export const vec = { add, sub, scale, dot, cross, length, normalize };

export function rotate(q, v) {
  const [w, x, y, z] = q;
  const t = scale(cross([x, y, z], v), 2);
  return add(add(v, scale(t, w)), cross([x, y, z], t));
}

function qmul(a, b) {
  return [
    a[0] * b[0] - a[1] * b[1] - a[2] * b[2] - a[3] * b[3],
    a[0] * b[1] + a[1] * b[0] + a[2] * b[3] - a[3] * b[2],
    a[0] * b[2] - a[1] * b[3] + a[2] * b[0] + a[3] * b[1],
    a[0] * b[3] + a[1] * b[2] - a[2] * b[1] + a[3] * b[0],
  ];
}

const conj = (q) => [q[0], -q[1], -q[2], -q[3]];

function qnormalize(q) {
  const l = Math.hypot(...q);
  return q.map((c) => c / l);
}

// Rotation whose columns are the body axes in world space.
export function fromBasis(f, l, u) {
  const [m00, m10, m20] = f, [m01, m11, m21] = l, [m02, m12, m22] = u;
  const trace = m00 + m11 + m22;
  let q;
  if (trace > 0) {
    const s = 0.5 / Math.sqrt(trace + 1);
    q = [0.25 / s, (m21 - m12) * s, (m02 - m20) * s, (m10 - m01) * s];
  } else if (m00 > m11 && m00 > m22) {
    const s = 2 * Math.sqrt(1 + m00 - m11 - m22);
    q = [(m21 - m12) / s, 0.25 * s, (m01 + m10) / s, (m02 + m20) / s];
  } else if (m11 > m22) {
    const s = 2 * Math.sqrt(1 + m11 - m00 - m22);
    q = [(m02 - m20) / s, (m01 + m10) / s, 0.25 * s, (m12 + m21) / s];
  } else {
    const s = 2 * Math.sqrt(1 + m22 - m00 - m11);
    q = [(m10 - m01) / s, (m02 + m20) / s, (m12 + m21) / s, 0.25 * s];
  }
  return qnormalize(q);
}

// Signed angle of `v` from `n` about `axis`.
function angleAbout(n, v, axis) {
  return Math.atan2(dot(cross(n, v), axis), dot(n, v));
}

function inertia(st, s) {
  return s.inertiaStand.map((stand, i) => lerp(stand, s.inertiaTuck[i], st.tuck));
}

export function angularVelocity(st, s = SETTINGS) {
  const I = inertia(st, s);
  const local = rotate(conj(st.q), st.L);
  return rotate(st.q, [local[0] / I[0], local[1] / I[1], local[2] / I[2]]);
}

// Carving curvature of an edged ski: sidecut radius times cos(edge), toward the edged side (negative = right).
export function curvature(edge, s = SETTINGS) {
  const onset = smoothstep(0, rad(s.carveOnsetDeg), Math.abs(edge));
  return Math.sign(edge) * onset / (s.sidecutRadius * Math.cos(Math.min(Math.abs(edge), rad(75))));
}

// The edge angle that carves curvature `kappa` (absolute value), within the rider's maximum edge.
export function edgeFor(kappa, s = SETTINGS) {
  let lo = 0, hi = rad(s.maxEdgeDeg);
  if (Math.abs(curvature(hi, s)) <= kappa) return hi;
  for (let i = 0; i < 14; i++) {
    const mid = (lo + hi) / 2;
    if (Math.abs(curvature(mid, s)) < kappa) lo = mid; else hi = mid;
  }
  return (lo + hi) / 2;
}

// The edge angle whose sideways grip is `grip` times the load.
function edgeForGrip(grip, s) {
  const t = clamp((grip - s.flatGrip) / (s.edgeGrip - s.flatGrip), 0, 1);
  // Invert smoothstep: t = x^2 (3 - 2x).
  const x = 0.5 - Math.sin(Math.asin(1 - 2 * t) / 3);
  return x * rad(s.edgeFullDeg);
}

export const INPUT = { steer: 0, lean: 0, crouch: false, spin: 0, grab: 0, brake: false };

export function createSkier(terrain, at, heading = 0, speed = 0, s = SETTINGS) {
  const [x, y] = at;
  const n = terrain.normal(x, y);
  const along = [Math.cos(heading), Math.sin(heading), 0];
  const f = normalize(sub(along, scale(n, dot(along, n))));
  const l = cross(n, f);
  const h = s.standHeight - s.crouchDrop * s.rideCrouch;
  const sink = s.mass * s.gravity / s.snowStiffness;
  return {
    p: add([x, y, terrain.height(x, y)], scale(n, h - sink)),
    v: scale(f, speed),
    q: fromBasis(f, l, n),
    L: [0, 0, 0],
    h, hRate: 0, footX: 0, footXRate: 0,
    angulation: 0, edge: 0, tuck: 0, coil: 0,
    switch: false, pivoting: false, popWindow: 0, crouchHeld: false,
    mode: 'ride', crashTime: 0, time: 0,
    grounded: true, groundForce: s.mass * s.gravity, contactForce: scale(n, s.mass * s.gravity), normal: n, slip: 0, unloaded: 0,
    air: null, landing: null, score: 0, events: [],
  };
}

function contacts(st, terrain, s, w) {
  const fB = rotate(st.q, [1, 0, 0]);
  const zB = rotate(st.q, [0, 0, 1]);
  const skiQ = qmul(st.q, [Math.cos(st.angulation / 2), Math.sin(st.angulation / 2), 0, 0]);
  const skiUp = rotate(skiQ, [0, 0, 1]);
  const count = s.contactPoints;
  const k = s.snowStiffness / count, c = s.snowDamping / count;
  let force = [0, 0, 0], torque = [0, 0, 0], total = 0, slip = 0, normalSum = [0, 0, 0], edgeSum = 0;
  for (let i = 0; i < count; i++) {
    const along = (i / (count - 1) - 0.5) * s.skiLength;
    const local = [st.footX + along, 0, -st.h];
    const r = rotate(st.q, local);
    const point = add(st.p, r);
    const ground = terrain.height(point[0], point[1]);
    if (point[2] >= ground) continue;
    const n = terrain.normal(point[0], point[1]);
    const depth = (ground - point[2]) * n[2];
    const pointV = add(add(st.v, cross(w, r)), rotate(st.q, [st.footXRate, 0, -st.hRate]));
    const into = -dot(pointV, n);
    const fn = Math.max(0, k * depth + c * into);
    if (fn <= 0) continue;
    const ft = normalize(sub(fB, scale(n, dot(fB, n))));
    const edge = angleAbout(n, skiUp, ft);
    // The edged ski's contact line bends into an arc: its local tangent turns with the distance from the boot.
    const yaw = -(along) * curvature(edge, s);
    const tangent = add(scale(ft, Math.cos(yaw)), scale(cross(n, ft), Math.sin(yaw)));
    const lateral = cross(n, tangent);
    const grip = lerp(s.flatGrip, s.edgeGrip, smoothstep(0, rad(s.edgeFullDeg), Math.abs(edge))) * (terrain.grip?.(point[0], point[1]) ?? 1)
      * ((st.popWindow > 0 && st.coil !== 0) || st.pivoting ? s.pivotGrip : 1);
    const vl = dot(pointV, lateral), vf = dot(pointV, tangent);
    const f = add(add(scale(n, fn), scale(lateral, -grip * fn * clamp(vl / s.slipSpeed, -1, 1))),
      scale(tangent, -s.glideFriction * fn * clamp(vf / 0.1, -1, 1)));
    force = add(force, f);
    torque = add(torque, cross(r, f));
    total += fn;
    slip += Math.abs(vl) * fn;
    normalSum = add(normalSum, scale(n, fn));
    edgeSum += edge * fn;
  }
  return { force, torque, total, slip: total > 0 ? slip / total : 0, normal: total > 0 ? normalize(normalSum) : terrain.normal(st.p[0], st.p[1]), edge: total > 0 ? edgeSum / total : st.edge, fB, zB };
}

// Hip and head spheres: touching the snow with either is a crash.
function bodyContacts(st, terrain, w) {
  const spheres = [[[0, 0, 0], SETTINGS.hipRadius], [[0, 0, SETTINGS.headHeight * (1 - 0.4 * st.tuck)], SETTINGS.headRadius]];
  let force = [0, 0, 0], torque = [0, 0, 0], hit = false;
  for (const [local, radius] of spheres) {
    const r = rotate(st.q, local);
    const centre = add(st.p, r);
    const ground = terrain.height(centre[0], centre[1]);
    const n = terrain.normal(centre[0], centre[1]);
    const depth = (ground - centre[2]) * n[2] + radius;
    if (depth <= 0) continue;
    hit = true;
    const pointV = add(st.v, cross(w, r));
    const fn = Math.max(0, 40000 * depth - 1500 * dot(pointV, n));
    const tangentV = sub(pointV, scale(n, dot(pointV, n)));
    const speed = length(tangentV);
    const friction = speed > 1e-6 ? scale(tangentV, -0.45 * fn * Math.min(1, speed / 0.2) / speed) : [0, 0, 0];
    const f = add(scale(n, fn), friction);
    force = add(force, f);
    torque = add(torque, cross(add(r, scale(n, -radius)), f));
  }
  return { force, torque, hit };
}

function crash(st, why) {
  if (st.mode === 'crash') return;
  st.mode = 'crash';
  st.crashTime = 0;
  st.events.push({ type: 'crash', why, time: st.time });
  if (st.landing) { st.events.push({ type: 'bail', trick: st.landing.name, time: st.time }); st.landing = null; }
}

function substep(st, input, terrain, s) {
  const dt = s.dt, m = s.mass, g = s.gravity;
  const riding = st.mode === 'ride';
  const n = st.normal;
  const fB = rotate(st.q, [1, 0, 0]), zB = rotate(st.q, [0, 0, 1]);
  const ft = normalize(sub(fB, scale(n, dot(fB, n))));
  const lt = cross(n, ft);
  const I = inertia(st, s);
  let w = angularVelocity(st, s);
  const vf = dot(st.v, ft), vl = dot(st.v, lt);
  if (Math.abs(vf) > 0.8) st.switch = vf < 0;
  const travel = st.switch ? -1 : 1;
  const grounded = st.grounded;
  const steer = clamp(input.steer, -1, 1) * travel;
  let torque = [0, 0, 0];

  if (riding && st.crouchHeld && !input.crouch && grounded) st.popWindow = 0.25;
  st.crouchHeld = input.crouch;
  st.popWindow = Math.max(0, st.popWindow - dt);

  // Legs: crouch to load, extend to pop. Extension only pushes while the skis are on the snow.
  const crouch = !riding ? 0.3 : input.crouch ? 1 : !grounded && input.grab ? 1 : s.rideCrouch;
  const target = s.standHeight - s.crouchDrop * crouch;
  // The legs are a servo with limited speed and acceleration: flexing is slower than extending, and extension
  // stops pushing once the snow pushes back harder than the legs can.
  // Only a pop extends at full speed; after soaking up a landing the legs stand back up slowly.
  const extend = !grounded || st.popWindow > 0 ? s.legRate : s.recoverRate;
  let hRate = approach(st.hRate, clamp((target - st.h) * 30, -s.flexRate, extend), s.legAccel * dt);
  if (grounded && hRate > 0 && st.groundForce > s.legForceMax * m * g) hRate = approach(hRate, 0, 2 * s.legAccel * dt);
  // Flexing lets the body sink onto bent knees; on the snow it never pulls the skis up off it.
  if (grounded && riding && hRate < 0 && st.groundForce < 0.45 * m * g) hRate = approach(hRate, 0, 2 * s.legAccel * dt);
  st.hRate = hRate;
  if (grounded && st.groundForce > s.absorbStart * m * g) hRate -= (st.groundForce - s.absorbStart * m * g) / (m * s.absorbSoftness);
  const h = clamp(st.h + hRate * dt, s.standHeight - s.crouchDrop - 0.08, s.standHeight);
  if (h !== st.h + hRate * dt) st.hRate = 0;
  st.h = h;
  const footTarget = riding ? -clamp(input.lean, -1, 1) * s.footShift * travel : 0;
  st.footXRate = clamp((footTarget - st.footX) * 10, -1, 1);
  st.footX += st.footXRate * dt;


  const tuckTarget = !riding ? 0.2 : grounded ? 0 : input.grab ? 1 : input.crouch ? 0.5 : 0.15;
  st.tuck = approach(st.tuck, tuckTarget, 6 * dt);

  if (riding && grounded) {
    // Edge: steering, braking or holding the line against a sideslip.
    // The stick asks for a turn and the rider leans into it. The edge follows the lean: the rider tips the skis
    // to carve the turn their inclination (from plumb) can stand on, never more.
    const roll = angleAbout(n, zB, ft);
    const lean = angleAbout([0, 0, 1], zB, ft);
    const speed2 = vf * vf + vl * vl;
    const wanted = Math.abs(steer) * Math.abs(curvature(rad(s.maxEdgeDeg), s));
    const standable = g * Math.tan(Math.min(Math.abs(lean), rad(80))) / Math.max(speed2, 0.5);
    // Sideslip of the boots, not the body: rolling over the edges swings the body sideways above held feet.
    const feet = add(st.v, cross(w, rotate(st.q, [st.footX, 0, -st.h])));
    const slide = dot(feet, lt);
    let edgeTarget = Math.sign(lean) * edgeFor(standable, s) + clamp(slide * s.edgeHold, -rad(15), rad(15));
    // Hockey stop: flatten and pivot the skis across the travel, lean back against the slide, then set the edges
    // as hard as that lean can stand on.
    const swing = Math.abs(Math.atan2(Math.abs(slide), Math.abs(dot(feet, ft))));
    const against = Math.sign(slide) * lean;
    st.pivoting = input.brake && speed2 > 1 && (swing < rad(55) || against < rad(s.brakeLeanDeg) * 0.6);
    if (input.brake) edgeTarget = st.pivoting || Math.abs(slide) < 0.3 ? 0 : Math.sign(slide) * edgeForGrip(Math.tan(Math.max(0, against)), s);
    // Balance: lean along the felt force of the turn the stick asks for.
    const felt = add(scale(lt, -speed2 * Math.sign(steer) * wanted), [0, 0, g]);
    const balanced = angleAbout(n, normalize(felt), ft);
    // The steepest lean the skis can hold at this speed: the full-edge carve. The assist keeps the lean inside it.
    const fullCarve = add(scale(lt, -speed2 * Math.sign(steer) * Math.abs(curvature(rad(s.maxEdgeDeg), s))), [0, 0, g]);
    const limit = Math.abs(angleAbout(n, normalize(fullCarve), ft));
    let rollTarget = lerp(steer * rad(s.maxEdgeDeg) * 0.75, balanced, s.balanceAssist);
    // Lean back against the slide once the skis are across, standing up again as the slide dies away.
    if (input.brake && speed2 > 0.04) rollTarget = Math.sign(slide) * rad(s.brakeLeanDeg) * smoothstep(rad(20), rad(50), swing) * smoothstep(0.5, 5, Math.sqrt(speed2));
    const most = input.brake ? rad(60) : lerp(rad(80), Math.max(0, limit - rad(5)), smoothstep(0, 0.5, s.balanceAssist));
    rollTarget = clamp(rollTarget, -most, most);
    const reach = st.groundForce * s.balanceReach;
    // Roll at a rate that can still be stopped: the centre of pressure only reaches so far across the skis.
    const error = rollTarget - roll;
    const stoppable = Math.sqrt(2 * 0.3 * reach / I[0] * Math.abs(error));
    const rollRate = Math.sign(error) * Math.min(s.maxRollRate, s.balanceGain * Math.abs(error), stoppable);
    const rollTorque = clamp(I[0] * s.balanceDamping * (rollRate - dot(w, ft)), -reach, reach);
    torque = add(torque, scale(ft, rollTorque));
    const angulationTarget = clamp(edgeTarget - roll, -rad(s.maxAngulationDeg), rad(s.maxAngulationDeg));
    st.angulation = approach(st.angulation, angulationTarget, s.angulationRate * dt);

    // Yaw: unwind the coil at the pop, pivot slow turns, or swing across the fall line to brake.
    const yawRate = dot(w, n);
    const edgeFrac = smoothstep(0, rad(s.edgeFullDeg), Math.abs(st.edge));
    let yawTarget = yawRate, yawLimit = 0;
    if (st.popWindow > 0 && st.coil !== 0) {
      yawTarget = st.coil * s.spinRate;
      yawLimit = s.edgeGrip * st.groundForce * 0.45;
    } else if (input.brake && speed2 > 1) {
      const velocity = normalize(add(scale(ft, vf), scale(lt, vl)));
      const across = cross(n, velocity);
      const side = dot(ft, across) >= 0 ? across : scale(across, -1);
      yawTarget = clamp(6 * angleAbout(ft, side, n), -5, 5);
      yawLimit = s.flatGrip * st.groundForce * 0.6;
    } else {
      const slow = 1 - smoothstep(2, 6, Math.sqrt(speed2));
      yawTarget = lerp(yawRate, -steer * s.pivotRate, slow * (1 - edgeFrac * 0.8));
      yawLimit = s.flatGrip * st.groundForce * 0.4;
    }
    torque = add(torque, scale(n, clamp(I[2] * 30 * (yawTarget - yawRate), -yawLimit, yawLimit)));

    st.coil = input.spin && st.popWindow === 0 ? approach(st.coil, clamp(input.spin, -1, 1), s.coilRate * dt)
      : st.popWindow > 0 ? st.coil : approach(st.coil, 0, 2 * dt);
  } else if (riding) {
    // Air: no external torque except the optional assists.
    const below = terrain.normal(st.p[0], st.p[1]);
    const axis = cross(zB, below);
    const level = add(scale(axis, 25), scale(sub(w, scale(zB, dot(w, zB))), -6));
    torque = add(torque, scale(level, s.airAssist * I[0]));
    torque = add(torque, scale(zB, s.spinAssist * I[2] * 10 * clamp(input.spin, -1, 1)));
    st.angulation = approach(st.angulation, 0, s.angulationRate * dt);
  } else {
    st.angulation = approach(st.angulation, 0, s.angulationRate * dt);
  }

  const contact = contacts(st, terrain, s, w);
  const body = bodyContacts(st, terrain, w);
  const drag = scale(st.v, -0.5 * s.airDensity * lerp(s.dragStand, s.dragTuck, Math.max(st.tuck, crouch > 0.5 ? 0.6 : 0)) * length(st.v));
  const force = add(add(add(contact.force, body.force), drag), [0, 0, -m * g]);
  torque = add(add(torque, contact.torque), body.torque);

  st.v = add(st.v, scale(force, dt / m));
  st.p = add(st.p, scale(st.v, dt));
  st.L = add(st.L, scale(torque, dt));
  w = angularVelocity(st, s);
  const angle = length(w) * dt;
  if (angle > 1e-12) {
    const axis = scale(w, 1 / length(w));
    st.q = qnormalize(qmul([Math.cos(angle / 2), ...scale(axis, Math.sin(angle / 2))], st.q));
  }

  st.groundForce = contact.total;
  st.contactForce = contact.force;
  st.normal = contact.normal;
  st.edge = contact.edge;
  st.slip = contact.slip;
  st.unloaded = contact.total > 0.05 * m * g ? 0 : st.unloaded + dt;
  const wasGrounded = st.grounded;
  st.grounded = st.unloaded < 0.08;
  st.time += dt;

  if (riding && body.hit) crash(st, 'body hit the snow');
  if (riding && st.grounded && Math.abs(angleAbout(st.normal, zB, ft)) > rad(78)) crash(st, 'fell over');
  if (!riding) st.crashTime += dt;
  track(st, wasGrounded, input, s, w);
}

function track(st, wasGrounded, input, s, w) {
  const zB = rotate(st.q, [0, 0, 1]);
  if (st.mode === 'ride' && wasGrounded && !st.grounded) {
    st.air = { time: 0, yaw: 0, flip: 0, grabs: {}, startZ: st.p[2], peak: st.p[2], switch: st.switch };
    st.coil = 0;
    st.events.push({ type: 'takeoff', time: st.time });
  }
  if (st.air && !st.grounded) {
    const a = st.air;
    a.time += s.dt;
    a.yaw += w[2] * s.dt;
    const side = normalize(cross([0, 0, 1], rotate(st.q, [1, 0, 0])));
    a.flip += dot(w, side) * s.dt;
    a.peak = Math.max(a.peak, st.p[2]);
    if (input.grab) a.grabs[GRABS[input.grab]] = (a.grabs[GRABS[input.grab]] ?? 0) + s.dt;
  }
  if (st.air && st.grounded) {
    const a = st.air;
    st.air = null;
    if (st.mode !== 'ride' || a.time < 0.3) return;
    const spin = Math.round(Math.abs(a.yaw) / Math.PI) * 180;
    const flips = Math.round(Math.abs(a.flip) / (2 * Math.PI));
    const grab = Object.entries(a.grabs).filter(([, t]) => t > 0.15).sort((x, y) => y[1] - x[1])[0];
    const parts = [];
    if (a.switch) parts.push('Switch');
    if (flips) parts.push(flips > 1 ? `Double ${a.flip > 0 ? 'Front' : 'Back'}flip` : `${a.flip > 0 ? 'Front' : 'Back'}flip`);
    if (spin) parts.push(String(spin));
    if (grab) parts.push(grab[0]);
    if (!spin && !flips && !grab) parts.push('Straight Air');
    const points = Math.round(100 * a.time + spin * 0.8 + flips * 400 + (grab ? grab[1] * 300 : 0));
    st.landing = { name: parts.join(' '), points, at: st.time, air: a.time, height: a.peak - a.startZ, landedSwitch: st.switch };
    st.events.push({ type: 'land', trick: st.landing.name, time: st.time, air: a.time, upright: dot(zB, st.normal) });
  }
  if (st.landing && st.mode === 'ride' && st.time - st.landing.at > 0.7) {
    st.score += st.landing.points;
    st.events.push({ type: 'trick', trick: st.landing.name, points: st.landing.points, time: st.time });
    st.landing = null;
  }
}

export function advance(st, input, terrain, seconds, s = SETTINGS) {
  const steps = Math.max(1, Math.round(seconds / s.dt));
  for (let i = 0; i < steps; i++) substep(st, input, terrain, s);
  return st;
}

// Summary used by the viewer and the tests.
export function report(st, s = SETTINGS) {
  const fB = rotate(st.q, [1, 0, 0]);
  const ft = normalize(sub(fB, scale(st.normal, dot(fB, st.normal))));
  return {
    speed: length(st.v),
    edgeDeg: st.edge * 180 / Math.PI,
    rollDeg: angleAbout(st.normal, rotate(st.q, [0, 0, 1]), ft) * 180 / Math.PI,
    yawRate: dot(angularVelocity(st, s), st.normal),
    grounded: st.grounded,
    mode: st.mode,
  };
}
