// Ski lab viewer: Three.js (global THREE, r128) around sim.js. Simulation axes are z up; Three.js is y up,
// so a simulation point (x, y, z) is drawn at (x, z, -y).
import { SETTINGS, INPUT, createSkier, advance, report, rotate } from './sim.js';
import { makePark } from './terrain.js';

const smoothstep = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
const toThree = (p) => new THREE.Vector3(p[0], p[2], -p[1]);
const quatToThree = (q) => new THREE.Quaternion(q[1], q[3], -q[2], q[0]);

const settings = { ...SETTINGS };
const terrain = makePark();
const canvas = document.getElementById('view');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x9fb4c8);
scene.fog = new THREE.Fog(0x9fb4c8, 120, 700);
const camera = new THREE.PerspectiveCamera(62, 1, 0.1, 2000);

const sun = new THREE.DirectionalLight(0xfff2e0, 1.15);
sun.position.set(-60, 120, 40);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
Object.assign(sun.shadow.camera, { left: -30, right: 30, top: 30, bottom: -30, near: 1, far: 400 });
scene.add(sun, sun.target, new THREE.HemisphereLight(0xdde8ff, 0x5a5250, 0.42));

// Snow: a grid over the park, coloured by slope so features read at a glance.
{
  const { park } = terrain;
  const x0 = park.startX - 20, x1 = park.finishX + 60, y0 = -park.halfWidth - 40, y1 = park.halfWidth + 40;
  const nx = Math.round((x1 - x0) / 0.5), ny = Math.round((y1 - y0) / 0.5);
  const positions = new Float32Array((nx + 1) * (ny + 1) * 3), colours = new Float32Array(positions.length);
  const snow = new THREE.Color(0xf4f7fb), shade = new THREE.Color(0xa9bdd6), ash = new THREE.Color(0x3a3532);
  let k = 0;
  for (let j = 0; j <= ny; j++) for (let i = 0; i <= nx; i++) {
    const x = x0 + i * (x1 - x0) / nx, y = y0 + j * (y1 - y0) / ny, z = terrain.height(x, y);
    positions.set([x, z, -y], k);
    const n = terrain.normal(x, y);
    // Snow thins to ash up the banks; steeper faces shade bluer so the jumps read.
    const speckle = 0.97 + 0.03 * Math.sin(x * 12.9898 + y * 78.233) * Math.sin(x * 3.1 - y * 5.7);
    const c = snow.clone().lerp(shade, Math.min(1, (1 - n[2]) * 3.5)).lerp(ash, smoothstep(park.halfWidth + 4, park.halfWidth + 20, Math.abs(y)) * 0.85)
      .multiplyScalar(speckle);
    colours.set([c.r, c.g, c.b], k);
    k += 3;
  }
  const index = [];
  for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
    const a = j * (nx + 1) + i, b = a + 1, c = a + nx + 1, d = c + 1;
    index.push(a, b, c, b, d, c);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute('color', new THREE.BufferAttribute(colours, 3));
  geometry.setIndex(index);
  geometry.computeVertexNormals();
  // Groomer corduroy along the fall line: the eye reads speed from it.
  const cord = document.createElement('canvas');
  cord.width = 64; cord.height = 8;
  const g = cord.getContext('2d');
  g.fillStyle = '#ffffff'; g.fillRect(0, 0, 64, 8);
  for (let i = 0; i < 64; i += 4) { g.fillStyle = i % 8 ? '#e9eef5' : '#dde5ef'; g.fillRect(i, 0, 2, 8); }
  const texture = new THREE.CanvasTexture(cord);
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  texture.anisotropy = 8;
  const uv = new Float32Array((nx + 1) * (ny + 1) * 2);
  for (let j = 0, q = 0; j <= ny; j++) for (let i = 0; i <= nx; i++, q += 2) uv.set([j * 0.5 / 1.2, i * 0.5 / 8], q);
  geometry.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
  const mesh = new THREE.Mesh(geometry, new THREE.MeshLambertMaterial({ vertexColors: true, map: texture }));
  mesh.receiveShadow = true;
  scene.add(mesh);
}

// The volcano: the park runs down its upper flank from the crater rim behind the start. Lava-rock ridges with
// steaming vents line the run, and the island and the sea lie far below.
const steam = [];
{
  const rock = new THREE.MeshLambertMaterial({ color: 0x2f2b2a });
  const top = terrain.height(-30, 0);
  const summit = new THREE.Mesh(new THREE.ConeGeometry(260, 220, 40, 4, true), new THREE.MeshLambertMaterial({ color: 0xe9eef4 }));
  summit.position.set(-200, top + 60, 0);
  scene.add(summit);
  const crater = new THREE.Mesh(new THREE.CylinderGeometry(70, 95, 12, 32, 1, true), rock);
  crater.position.set(-200, top + 166, 0);
  scene.add(crater);
  const vents = [];
  for (const side of [1, -1]) {
    for (let x = -10; x < terrain.park.finishX + 60; x += 38) {
      const y = side * (terrain.park.halfWidth + 20 + 8 * Math.sin(x * 0.07 + side));
      const ridge = new THREE.Mesh(new THREE.DodecahedronGeometry(9 + 5 * Math.sin(x * 0.13), 0), rock);
      ridge.position.copy(toThree([x, y, terrain.height(x, y) + 2]));
      ridge.scale.set(1.6, 0.9, 1);
      ridge.rotation.y = x;
      scene.add(ridge);
      if ((x / 38 + (side > 0 ? 0 : 1)) % 3 < 1) vents.push(ridge.position.clone().add(new THREE.Vector3(0, 7, 0)));
    }
  }
  const sea = new THREE.Mesh(new THREE.PlaneGeometry(6000, 6000), new THREE.MeshLambertMaterial({ color: 0x3f6f8f }));
  sea.rotation.x = -Math.PI / 2;
  sea.position.set(1500, terrain.height(terrain.park.finishX, 0) - 420, 0);
  scene.add(sea);
  const land = new THREE.Mesh(new THREE.ConeGeometry(1500, 420, 48, 1, true), new THREE.MeshLambertMaterial({ color: 0x4f6b45 }));
  land.position.set(300, terrain.height(terrain.park.finishX, 0) - 230, 0);
  scene.add(land);
  const puff = new THREE.MeshLambertMaterial({ color: 0xffffff, transparent: true, opacity: 0.35, depthWrite: false });
  vents.forEach((vent, v) => {
    for (let i = 0; i < 5; i++) {
      const m = new THREE.Mesh(new THREE.SphereGeometry(1, 10, 8), puff.clone());
      m.userData = { phase: i / 5 + v * 0.13, vent };
      scene.add(m);
      steam.push(m);
    }
  });
}

// Jump lips: a dark line marks each lip, a blue one each knuckle.
for (const jump of terrain.jumps) {
  for (const [u, colour] of [[jump.profile.lipU, 0x1d2a3a], [jump.profile.tableEnd, 0x3f7fbf]]) {
    const pts = [];
    for (let y = -jump.width / 2; y <= jump.width / 2; y += 0.5) pts.push(toThree([jump.x + u, y, terrain.height(jump.x + u, y) + 0.02]));
    scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: colour })));
  }
}

// Rider: pelvis at the body origin, legs to the boots, skis rolled by the angulation.
const rider = new THREE.Group();
const jacket = new THREE.MeshLambertMaterial({ color: 0xd9452b });
const pants = new THREE.MeshLambertMaterial({ color: 0x24303f });
const skin = new THREE.MeshLambertMaterial({ color: 0xe0b48f });
const skiMat = new THREE.MeshLambertMaterial({ color: 0x1fa3a0 });
const part = (geometry, material) => { const m = new THREE.Mesh(geometry, material); m.castShadow = true; return m; };
const torso = part(new THREE.BoxGeometry(0.24, 0.5, 0.34), jacket);
const head = part(new THREE.SphereGeometry(0.11, 14, 10), skin);
const helmet = part(new THREE.SphereGeometry(0.125, 14, 10, 0, Math.PI * 2, 0, Math.PI / 2), new THREE.MeshLambertMaterial({ color: 0xf0f0f0 }));
const segment = (material, radius) => part(new THREE.CylinderGeometry(radius, radius * 0.85, 1, 8), material);
const legs = [0.11, -0.11].map((side) => ({ side, thigh: segment(pants, 0.07), shin: segment(pants, 0.055) }));
const arms = [0.21, -0.21].map((side) => ({ side, upper: segment(jacket, 0.045), lower: segment(jacket, 0.04) }));
const skis = new THREE.Group();
for (const side of [0.11, -0.11]) {
  const ski = part(new THREE.BoxGeometry(SETTINGS.skiLength, 0.025, 0.095), skiMat);
  ski.position.set(0, 0.012, -side);
  const tip = part(new THREE.BoxGeometry(0.16, 0.025, 0.095), skiMat);
  tip.position.set(SETTINGS.skiLength / 2 + 0.06, 0.05, -side);
  tip.rotation.z = 0.5;
  const tail = tip.clone();
  tail.position.x = -tip.position.x;
  tail.rotation.z = -0.5;
  skis.add(ski, tip, tail);
}
rider.add(torso, head, helmet, skis, ...legs.flatMap((l) => [l.thigh, l.shin]), ...arms.flatMap((a) => [a.upper, a.lower]));
scene.add(rider);

function place(mesh, a, b) {
  const d = b.clone().sub(a);
  mesh.position.copy(a).add(b).multiplyScalar(0.5);
  mesh.scale.set(1, Math.max(d.length(), 1e-3), 1);
  mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), d.normalize());
}

// Two-bone leg: the knee bends forward, in the body's local frame (Three.js axes: x forward, y up, z right).
function limb(upper, lower, from, to, lengths, bend) {
  const d = to.clone().sub(from);
  const reach = Math.min(d.length(), lengths[0] + lengths[1] - 1e-3);
  const along = (lengths[0] ** 2 - lengths[1] ** 2 + reach ** 2) / (2 * reach);
  const out = Math.sqrt(Math.max(0, lengths[0] ** 2 - along ** 2));
  const axis = d.normalize();
  const side = bend.clone().sub(axis.clone().multiplyScalar(bend.dot(axis))).normalize();
  const joint = from.clone().add(axis.clone().multiplyScalar(along)).add(side.multiplyScalar(out));
  place(upper, from, joint);
  place(lower, joint, to);
}

function pose(st) {
  rider.position.copy(toThree(st.p));
  rider.quaternion.copy(quatToThree(st.q));
  const tuck = st.tuck;
  torso.position.set(0.03 + 0.12 * tuck, 0.25 - 0.08 * tuck, 0);
  torso.rotation.z = -0.25 - 0.6 * tuck;
  head.position.set(0.12 + 0.28 * tuck, 0.58 - 0.22 * tuck, 0);
  helmet.position.copy(head.position);
  skis.position.set(st.footX, -st.h, 0);
  skis.rotation.set(st.angulation, 0, 0);
  for (const leg of legs) {
    const hip = new THREE.Vector3(0, -0.02, -leg.side);
    const boot = new THREE.Vector3(st.footX + 0.02, -st.h + 0.12, -leg.side);
    limb(leg.thigh, leg.shin, hip, boot, [0.46, 0.46], new THREE.Vector3(1, 0, 0));
  }
  const grab = st.grabbing;
  for (const arm of arms) {
    const shoulder = new THREE.Vector3(0.05 + 0.15 * tuck, 0.45 - 0.15 * tuck, -arm.side);
    let hand = new THREE.Vector3(0.35, 0.05, -arm.side * 1.9);
    if (grab === 1 && arm.side > 0) hand = new THREE.Vector3(st.footX + 0.25, -st.h + 0.08, 0);
    if (grab === 2 && arm.side < 0) hand = new THREE.Vector3(st.footX - 0.05, -st.h + 0.08, -arm.side * 1.6);
    limb(arm.upper, arm.lower, shoulder, hand, [0.3, 0.3], new THREE.Vector3(-0.3, -1, 0));
  }
}

// Ski tracks: a thin dark line pressed into the snow behind each ski.
const trackLength = 600;
const tracks = [0.11, -0.11].map((side) => {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(trackLength * 3), 3));
  geometry.setDrawRange(0, 0);
  const line = new THREE.Line(geometry, new THREE.LineBasicMaterial({ color: 0x9aaabd }));
  line.frustumCulled = false;
  scene.add(line);
  return { side, geometry, count: 0 };
});

function extendTracks(st) {
  if (!st.grounded) return;
  for (const t of tracks) {
    const p = rotate(st.q, [st.footX, t.side, -st.h]);
    const at = [st.p[0] + p[0], st.p[1] + p[1]];
    const v = toThree([at[0], at[1], terrain.height(at[0], at[1]) + 0.015]);
    const arr = t.geometry.attributes.position.array;
    if (t.count === trackLength) { arr.copyWithin(0, 3); t.count--; }
    arr.set([v.x, v.y, v.z], t.count * 3);
    t.count++;
    t.geometry.setDrawRange(0, t.count);
    t.geometry.attributes.position.needsUpdate = true;
  }
}

// Spray: points thrown off the skis in proportion to how hard they skid.
const sprayCount = 400;
const spray = { pos: new Float32Array(sprayCount * 3), vel: new Float32Array(sprayCount * 3), life: new Float32Array(sprayCount), next: 0 };
const sprayGeometry = new THREE.BufferGeometry();
sprayGeometry.setAttribute('position', new THREE.BufferAttribute(spray.pos, 3));
const sprayPoints = new THREE.Points(sprayGeometry, new THREE.PointsMaterial({ color: 0xffffff, size: 0.09, transparent: true, opacity: 0.85 }));
sprayPoints.frustumCulled = false;
scene.add(sprayPoints);

function emitSpray(st, dt) {
  const amount = st.grounded ? Math.min(1, st.slip * 1.2) * Math.min(1, report(st).speed / 6) : 0;
  const n = Math.floor(amount * 220 * dt + Math.random());
  const foot = rotate(st.q, [st.footX, 0, -st.h]);
  for (let i = 0; i < n * (amount > 0.05); i++) {
    const k = spray.next;
    spray.next = (k + 1) % sprayCount;
    const at = toThree([st.p[0] + foot[0], st.p[1] + foot[1], st.p[2] + foot[2] + 0.05]);
    spray.pos.set([at.x + (Math.random() - 0.5) * 1.2, at.y, at.z + (Math.random() - 0.5) * 1.2], k * 3);
    const v = toThree(st.v);
    spray.vel.set([v.x * 0.5 + (Math.random() - 0.5) * 3, 1 + Math.random() * 2.5, v.z * 0.5 + (Math.random() - 0.5) * 3], k * 3);
    spray.life[k] = 0.6 + Math.random() * 0.4;
  }
  for (let k = 0; k < sprayCount; k++) {
    if (spray.life[k] <= 0) { spray.pos[k * 3 + 1] = -1e4; continue; }
    spray.life[k] -= dt;
    spray.vel[k * 3 + 1] -= 9.81 * dt;
    for (let a = 0; a < 3; a++) spray.pos[k * 3 + a] += spray.vel[k * 3 + a] * dt;
  }
  sprayGeometry.attributes.position.needsUpdate = true;
}

// Input: keyboard, and the first gamepad when the page may read it.
const keys = new Set();
addEventListener('keydown', (e) => { keys.add(e.code); if (['Space', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.code)) e.preventDefault(); });
addEventListener('keyup', (e) => keys.delete(e.code));
addEventListener('blur', () => keys.clear());
let usingPad = false;

function readInput() {
  const k = (...codes) => codes.some((c) => keys.has(c));
  const input = {
    ...INPUT,
    steer: (k('KeyD', 'ArrowRight') ? 1 : 0) - (k('KeyA', 'ArrowLeft') ? 1 : 0),
    lean: (k('KeyW', 'ArrowUp') ? 1 : 0) - (k('KeyS', 'ArrowDown') ? 1 : 0),
    crouch: k('Space'),
    spin: (k('KeyJ') ? 1 : 0) - (k('KeyL') ? 1 : 0),
    grab: k('KeyQ') ? 1 : k('KeyE') ? 2 : 0,
    brake: k('ShiftLeft', 'ShiftRight'),
    reset: k('KeyR'),
  };
  let pads = [];
  try { pads = navigator.getGamepads ? [...navigator.getGamepads()].filter(Boolean) : []; } catch { pads = []; }
  const pad = pads[0];
  if (pad) {
    const dead = (x) => (Math.abs(x) < 0.12 ? 0 : x);
    const b = (i) => pad.buttons[i]?.pressed;
    const any = dead(pad.axes[0]) || dead(pad.axes[1]) || dead(pad.axes[2]) || pad.buttons.some((x) => x.pressed);
    if (any) usingPad = true;
    if (usingPad) {
      input.steer = dead(pad.axes[0]) || input.steer;
      input.lean = -dead(pad.axes[1]) || input.lean;
      input.crouch = b(0) || input.crouch;
      input.spin = -dead(pad.axes[2]) || input.spin;
      input.grab = (pad.buttons[6]?.value ?? 0) > 0.3 ? 1 : (pad.buttons[7]?.value ?? 0) > 0.3 ? 2 : input.grab;
      input.brake = b(1) || input.brake;
      input.reset = b(3) || input.reset;
    }
  }
  return input;
}

// Simulation loop at a fixed step under the display's frame rate.
let st = null;
const feed = document.getElementById('feed');
const hud = {
  speed: document.getElementById('speed'), state: document.getElementById('state'), edge: document.getElementById('edge'),
  score: document.getElementById('score'), trick: document.getElementById('trick'),
};
let trickTimer = 0;

function spawn() {
  st = createSkier(terrain, terrain.start, 0, 3, settings);
  for (const t of tracks) { t.count = 0; t.geometry.setDrawRange(0, 0); }
  camPos.copy(toThree(st.p)).add(new THREE.Vector3(-7, 3, 0));
}

function showTrick(text, kind) {
  hud.trick.textContent = text;
  hud.trick.dataset.kind = kind;
  trickTimer = 1.8;
  const row = document.createElement('li');
  row.textContent = text;
  row.dataset.kind = kind;
  feed.prepend(row);
  while (feed.children.length > 5) feed.lastChild.remove();
}

const camPos = new THREE.Vector3();
const camLook = new THREE.Vector3();
let last = performance.now(), carry = 0;
spawn();

function frame(now) {
  const dt = Math.min(0.05, (now - last) / 1000);
  last = now;
  const input = readInput();
  if (input.reset || (st.mode === 'crash' && st.crashTime > 3)) spawn();
  carry += dt;
  const steps = Math.floor(carry / settings.dt);
  carry -= steps * settings.dt;
  if (steps) advance(st, input, terrain, steps * settings.dt, settings);
  st.grabbing = !st.grounded && st.mode === 'ride' ? input.grab : 0;
  for (const e of st.events.splice(0)) {
    if (e.type === 'trick') showTrick(`${e.trick}  +${e.points}`, 'trick');
    if (e.type === 'bail') showTrick(`Bailed: ${e.trick}`, 'bail');
    if (e.type === 'crash' && !st.landing) showTrick(e.why === 'fell over' ? 'Fell over' : 'Crashed', 'bail');
  }
  pose(st);
  extendTracks(st);
  emitSpray(st, dt);

  // Camera: behind the direction of travel, lifted, easing in.
  const r = report(st, settings);
  const vel = toThree(st.v);
  vel.y = 0;
  const dir = vel.lengthSq() > 1 ? vel.normalize() : toThree(rotate(st.q, [1, 0, 0])).setY(0).normalize();
  const target = toThree(st.p);
  const want = target.clone().sub(dir.clone().multiplyScalar(6.5)).add(new THREE.Vector3(0, 2.6, 0));
  want.y = Math.max(want.y, terrain.height(want.x, -want.z) + 1.2);
  camPos.lerp(want, 1 - Math.exp(-dt * 4));
  camLook.lerp(target.clone().add(dir.clone().multiplyScalar(4)), 1 - Math.exp(-dt * 6));
  camera.position.copy(camPos);
  camera.lookAt(camLook);
  sun.position.copy(target).add(new THREE.Vector3(-30, 60, 20));
  sun.target.position.copy(target);

  for (const m of steam) {
    const t = (now / 6000 + m.userData.phase) % 1;
    m.position.copy(m.userData.vent).add(new THREE.Vector3(t * 4, t * 26, t * 2));
    m.scale.setScalar(1.5 + t * 7);
    m.material.opacity = 0.4 * (1 - t);
  }

  hud.speed.textContent = `${Math.round(r.speed * 3.6)} km/h`;
  hud.state.textContent = st.mode === 'crash' ? 'crashed' : !st.grounded ? 'air' : st.pivoting ? 'braking' : Math.abs(r.edgeDeg) > 8 ? 'carving' : 'gliding';
  hud.edge.textContent = `edge ${Math.round(r.edgeDeg)}°  lean ${Math.round(r.rollDeg)}°`;
  hud.score.textContent = st.score ? String(st.score) : '';
  trickTimer -= dt;
  hud.trick.style.opacity = trickTimer > 0 ? Math.min(1, trickTimer * 2) : 0;

  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (canvas.width !== Math.floor(w * renderer.getPixelRatio()) || canvas.height !== Math.floor(h * renderer.getPixelRatio())) {
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  renderer.render(scene, camera);
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);

// Assist sliders.
for (const input of document.querySelectorAll('[data-setting]')) {
  const key = input.dataset.setting;
  input.value = settings[key];
  const out = input.parentElement.querySelector('output');
  const show = () => { out.textContent = Number(input.value).toFixed(2); };
  show();
  input.addEventListener('input', () => { settings[key] = Number(input.value); show(); });
}
document.getElementById('respawn').addEventListener('click', () => { spawn(); canvas.focus(); });
