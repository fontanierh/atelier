// The grip poser: a person bends Modori's fingers round a held prop's handle; every pose is saved for the game.
// Scenes come from moments.py (data/moments.json): each grip's handle frame has A at the origin, the usable span along
// +x and the oval's major axis along +y (glTF axes, metres). Joint rotations are kept as bend / spread / twist about
// each joint's own axes (flex curls toward the palm), from the rest pose.
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { TransformControls } from 'three/addons/controls/TransformControls.js';
import { clone as cloneScene } from 'three/addons/utils/SkeletonUtils.js';

const NAMES = ['Index', 'Middle', 'Ring', 'Little', 'Thumb'];
const COLORS = ['#ff6b6b', '#ffd166', '#06d6a0', '#4cc9f0', '#c77dff'];
const JOINTS = ['base', 'middle', 'end'];
const SKIN = [1, 1, .8, .75, .95];   // FingerWrapNode's per-digit skin over the bone (cm)
const TOUCH = .0015;                  // skin within 1.5 mm of the surface touches it
const LIMITS = {   // degrees: [flex, spread, twist] ranges per joint, fingers then thumb
  finger: [[[-25, 100], [-25, 25], [-20, 20]], [[-10, 115], [-10, 10], [-15, 15]], [[-10, 95], [-10, 10], [-15, 15]]],
  thumb: [[[-40, 80], [-60, 60], [-60, 60]], [[-25, 80], [-25, 25], [-30, 30]], [[-20, 95], [-15, 15], [-20, 20]]],
};
const digitBones = side => [0, 1, 2, 3].map(f => [`finger_${f}_${side}`, `finger_tip_${f}_${side}`, `finger_end_${f}_${side}`])
  .concat([[`thumb_${side}`, `thumb_tip_${side}`, `thumb_end_${side}`]]);
const $ = id => document.getElementById(id);
const deg = THREE.MathUtils.degToRad;

// ------------------------------------------------------------------------------------------------ handle geometry
function ellipseDistance(px, py, ra, rb) {   // FingerWrapNode::EllipseDistance
  const x = Math.abs(px), y = Math.abs(py);
  let tx = Math.SQRT1_2, ty = Math.SQRT1_2;
  for (let i = 0; i < 4; i++) {
    const ex = (ra * ra - rb * rb) * tx ** 3 / ra, ey = (rb * rb - ra * ra) * ty ** 3 / rb;
    const rx = ra * tx - ex, ry = rb * ty - ey, qx = x - ex, qy = y - ey;
    const r = Math.hypot(rx, ry), q = Math.max(Math.hypot(qx, qy), 1e-9);
    tx = Math.min(Math.max((qx * r / q + ex) / ra, 0), 1); ty = Math.min(Math.max((qy * r / q + ey) / rb, 0), 1);
    const t = Math.max(Math.hypot(tx, ty), 1e-9); tx /= t; ty /= t;
  }
  const d = Math.hypot(x - ra * tx, y - rb * ty);
  return x * x / (ra * ra) + y * y / (rb * rb) < 1 ? -d : d;
}
function radiiAt(h, t) {
  const at = Math.min(Math.max(t / h.length, 0), 1);
  const lerp = (a, b, k) => [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k];
  if (!(h.mid_at > 0 && h.mid_at < 1)) return lerp(h.r0, h.r1, at);
  return at < h.mid_at ? lerp(h.r0, h.rm, at / h.mid_at) : lerp(h.rm, h.r1, (at - h.mid_at) / (1 - h.mid_at));
}
function outside(h, p) {   // signed distance from the handle's surface (capped oval cylinder), metres
  const r = radiiAt(h, p.x);
  const side = ellipseDistance(p.y, p.z, r[0], r[1]);
  const past = Math.max(-p.x, p.x - h.length) - h.beyond;
  return side > 0 && past > 0 ? Math.hypot(side, past) : Math.max(side, past);
}
function handleMesh(h) {
  const rings = 40, around = 28, pos = [], idx = [];
  for (let i = 0; i <= rings; i++) {
    const x = -h.beyond + (h.length + 2 * h.beyond) * i / rings, r = radiiAt(h, x);
    for (let j = 0; j < around; j++) { const a = j / around * Math.PI * 2; pos.push(x, Math.cos(a) * r[0], Math.sin(a) * r[1]); }
  }
  for (let i = 0; i < rings; i++) for (let j = 0; j < around; j++) {
    const a = i * around + j, b = i * around + (j + 1) % around;
    idx.push(a, a + around, b + around, a, b + around, b);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.setIndex(idx);
  return new THREE.Mesh(g, new THREE.MeshBasicMaterial({ color: 0x6ea8fe, wireframe: true, transparent: true, opacity: .35 }));
}

// ------------------------------------------------------------------------------------------------ a posable hand
class Hand {
  constructor(source, side, ghost) {
    this.side = side;
    const root = cloneScene(source);
    root.updateMatrixWorld(true);
    let body = null;
    root.traverse(o => { if (o.isSkinnedMesh && o.name.includes('Body')) body = o; });
    this.skeleton = body.skeleton;
    this.hand = root.getObjectByName(`hand_${side}`);
    this.digits = digitBones(side).map(names => names.map(n => root.getObjectByName(n)));
    // Only the hand's skin, its weights moved onto the hand's own bones (the wrist then follows the hand rigidly).
    const own = new Set([this.hand, ...this.digits.flat()].map(b => this.skeleton.bones.indexOf(b)));
    const digitOf = new Map();
    this.digits.forEach((d, k) => d.forEach(b => digitOf.set(this.skeleton.bones.indexOf(b), k)));
    const g = body.geometry, si = g.attributes.skinIndex, sw = g.attributes.skinWeight;
    const n = g.attributes.position.count, weightIn = new Float32Array(n);
    for (let v = 0; v < n; v++) for (let k = 0; k < 4; k++) if (own.has(si.getComponent(v, k))) weightIn[v] += sw.getComponent(v, k);
    const index = g.index.array, keep = [], remap = new Int32Array(n).fill(-1), verts = [];
    for (let t = 0; t < index.length; t += 3) {
      const a = index[t], b = index[t + 1], c = index[t + 2];
      if (weightIn[a] >= .5 && weightIn[b] >= .5 && weightIn[c] >= .5) for (const v of [a, b, c]) {
        if (remap[v] < 0) { remap[v] = verts.length; verts.push(v); }
        keep.push(remap[v]);
      }
    }
    const out = new THREE.BufferGeometry();
    for (const name of ['position', 'normal', 'uv']) {
      const src = g.attributes[name]; if (!src) continue;
      const arr = new Float32Array(verts.length * src.itemSize);
      verts.forEach((v, i) => { for (let k = 0; k < src.itemSize; k++) arr[i * src.itemSize + k] = src.getComponent(v, k); });
      out.setAttribute(name, new THREE.BufferAttribute(arr, src.itemSize));
    }
    const sIdx = new Uint16Array(verts.length * 4), sWt = new Float32Array(verts.length * 4);
    this.vertexDigit = new Int8Array(verts.length);
    const handIndex = this.skeleton.bones.indexOf(this.hand);
    verts.forEach((v, i) => {
      let total = 0; const per = new Float32Array(5); let palm = 0;
      for (let k = 0; k < 4; k++) {
        const b = si.getComponent(v, k), w = own.has(b) ? sw.getComponent(v, k) : 0;
        sIdx[i * 4 + k] = own.has(b) ? b : handIndex; sWt[i * 4 + k] = w; total += w;
        if (digitOf.has(b)) per[digitOf.get(b)] += w; else if (b === handIndex) palm += w;
      }
      for (let k = 0; k < 4; k++) sWt[i * 4 + k] /= total;
      let best = -1, most = palm;
      per.forEach((w, k) => { if (w > most) { most = w; best = k; } });
      this.vertexDigit[i] = best;
    });
    out.setAttribute('skinIndex', new THREE.BufferAttribute(sIdx, 4));
    out.setAttribute('skinWeight', new THREE.BufferAttribute(sWt, 4));
    out.setIndex(keep);
    this.colors = new Float32Array(verts.length * 3).fill(1);
    out.setAttribute('color', new THREE.BufferAttribute(this.colors, 3));
    const material = body.material.clone();
    material.vertexColors = true;
    if (ghost) { material.transparent = true; material.opacity = .45; material.depthWrite = false; }
    this.mesh = new THREE.SkinnedMesh(out, material);
    this.mesh.bind(this.skeleton, body.bindMatrix);
    this.mesh.frustumCulled = false;
    this.restWorld = new Map([this.hand, ...this.digits.flat()].map(b => [b.name, b.matrixWorld.clone()]));
    // the hand bone hangs from a pivot (the moment's hold) through an adjustment (the person's own move of the hand)
    this.pivot = new THREE.Group(); this.adjust = new THREE.Group();
    this.pivot.add(this.adjust); this.adjust.add(this.hand);
    this.hand.position.set(0, 0, 0); this.hand.quaternion.identity(); this.hand.scale.set(1, 1, 1);
    this.rest = this.digits.map(d => d.map(b => b.quaternion.clone()));
    this.params = this.digits.map(d => d.map(() => [0, 0, 0]));
    this.group = new THREE.Group(); this.group.add(this.pivot, this.mesh);
  }

  place(p) {
    this.pivot.position.fromArray(p.position); this.pivot.quaternion.fromArray(p.quaternion); this.pivot.scale.setScalar(p.scale);
    this.group.updateMatrixWorld(true);
  }

  // Each joint's axes in its own (rest) frame: twist along the bone, flex about the bone x palm normal (positive curls
  // toward the palm), spread about the back-of-hand normal. Computed with the joints straight, the hand at the given hold.
  axes(handleFrame) {
    for (const [k, d] of this.digits.entries()) d.forEach((b, j) => b.quaternion.copy(this.rest[k][j]));
    this.group.updateMatrixWorld(true);
    const w = b => b.getWorldPosition(new THREE.Vector3());
    const knuckles = w(this.digits[0][0]).add(w(this.digits[3][0])).multiplyScalar(.5);
    const along = knuckles.clone().sub(w(this.hand)).normalize();
    // the palm faces the handle: from the knuckles toward its axis (the x axis of the handle frame)
    const normal = new THREE.Vector3(knuckles.x, 0, 0).sub(knuckles);
    normal.addScaledVector(along, -normal.dot(along)).normalize();
    this.palmNormal = normal;
    this.basis = this.digits.map(d => d.map((b, j) => {
      const dir = (j < 2 ? w(d[j + 1]).sub(w(b)) : w(d[2]).sub(w(d[1]))).normalize();
      const flex = new THREE.Vector3().crossVectors(dir, normal).normalize();
      const spread = new THREE.Vector3().crossVectors(dir, flex);   // right-handed: flex x spread = along
      const world = new THREE.Matrix4().makeBasis(flex, spread, dir);
      const inv = new THREE.Matrix4().extractRotation(b.matrixWorld).invert();
      return new THREE.Matrix4().multiplyMatrices(inv, world);   // columns: flex, spread, twist in bone-local
    }));
    // the fingertip: the farthest skin of the last segment along it, kept in the last bone's frame
    this.tips = this.digits.map((d, k) => {
      const end = w(d[2]), dir = end.clone().sub(w(d[1])).normalize();
      let far = 0, tip = end.clone(); const v = new THREE.Vector3();
      for (let i = 0; i < this.vertexDigit.length; i++) {
        if (this.vertexDigit[i] !== k) continue;
        this.mesh.getVertexPosition(i, v);
        const s = v.clone().sub(end).dot(dir);
        if (s > far) { far = s; tip = end.clone().addScaledVector(dir, s); }
      }
      return d[2].worldToLocal(tip.clone());
    });
    this.apply();
  }

  rotationOf(k, j, p = this.params[k][j]) {
    const B = this.basis[k][j];
    const R = new THREE.Matrix4().makeRotationFromEuler(new THREE.Euler(deg(p[0]), deg(p[1]), deg(p[2]), 'XYZ'));
    const local = new THREE.Matrix4().multiplyMatrices(B, R).multiply(B.clone().transpose());
    return this.rest[k][j].clone().multiply(new THREE.Quaternion().setFromRotationMatrix(local));
  }

  apply() {
    this.digits.forEach((d, k) => d.forEach((b, j) => b.quaternion.copy(this.rotationOf(k, j))));
    this.group.updateMatrixWorld(true);
  }

  // A local rotation (the game's fitted pose) as bend / spread / twist.
  paramsFrom(k, j, q) {
    const B = this.basis[k][j];
    const local = new THREE.Matrix4().makeRotationFromQuaternion(this.rest[k][j].clone().invert().multiply(q));
    const R = B.clone().transpose().multiply(local).multiply(B);
    const e = new THREE.Euler().setFromRotationMatrix(R, 'XYZ');
    return [e.x, e.y, e.z].map(THREE.MathUtils.radToDeg);
  }

  points(k) {   // a digit's base, middle and end joints and its tip, world
    const d = this.digits[k], w = b => b.getWorldPosition(new THREE.Vector3());
    return [w(d[0]), w(d[1]), w(d[2]), d[2].localToWorld(this.tips[k].clone())];
  }

  limits(k, j) { return LIMITS[k === 4 ? 'thumb' : 'finger'][j]; }

  // CCD onto a target for the point at `effector` (1: middle joint, 2: end joint, 3: tip), within the joints' limits.
  // With `couple`, a finger's end joint bends two thirds as much as its middle one.
  reach(k, effector, target, couple) {
    const d = this.digits[k], q = new THREE.Quaternion();
    const effectorPoint = () => this.points(k)[effector];
    const coupled = couple && k < 4;
    for (let pass = 0; pass < 14; pass++) {
      for (let j = effector - 1; j >= 0; j--) {
        if (coupled && j === 2) continue;
        const dofs = j === 0 || (k === 4 && j === 1) ? [1, 0] : [0];
        for (const dof of dofs) {
          const pivot = d[j].getWorldPosition(new THREE.Vector3());
          const parentRot = d[j].parent.getWorldQuaternion(new THREE.Quaternion());
          const B = this.basis[k][j], p = this.params[k][j];
          // flex turns about its own (outermost) axis; spread about its axis after the flex
          const axis = new THREE.Vector3().setFromMatrixColumn(B, dof === 1 ? 1 : 0);
          if (dof === 1) axis.applyQuaternion(q.setFromAxisAngle(new THREE.Vector3().setFromMatrixColumn(B, 0), deg(p[0])));
          axis.applyQuaternion(this.rest[k][j]).applyQuaternion(parentRot).normalize();
          const u = effectorPoint().sub(pivot), v = target.clone().sub(pivot);
          u.addScaledVector(axis, -u.dot(axis)); v.addScaledVector(axis, -v.dot(axis));
          if (u.lengthSq() < 1e-12 || v.lengthSq() < 1e-12) continue;
          const angle = Math.atan2(axis.dot(new THREE.Vector3().crossVectors(u, v)), u.dot(v));
          const [lo, hi] = this.limits(k, j)[dof];
          p[dof] = Math.min(hi, Math.max(lo, p[dof] + THREE.MathUtils.radToDeg(angle)));
          if (coupled && j === 1) this.params[k][2][0] = Math.min(95, Math.max(-10, p[0] * 2 / 3));
          this.apply();
        }
      }
    }
  }
}

// ------------------------------------------------------------------------------------------------ the page
const renderer = new THREE.WebGLRenderer({ canvas: $('view'), antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x101216);
const camera = new THREE.PerspectiveCamera(35, 1, .005, 20);
const orbit = new OrbitControls(camera, renderer.domElement);
orbit.enableDamping = true;
scene.add(new THREE.HemisphereLight(0xffffff, 0x444455, 1.6));
const sun = new THREE.DirectionalLight(0xffffff, 1.6); sun.position.set(.4, 1, .6); scene.add(sun);
const fill = new THREE.DirectionalLight(0xbfd4ff, .7); fill.position.set(-.6, -.3, -.5); scene.add(fill);
const gizmo = new TransformControls(camera, renderer.domElement);
gizmo.setSize(.7);
gizmo.addEventListener('dragging-changed', e => {
  orbit.enabled = !e.value;
  if (e.value) pushUndo(); else changed(gizmo.mode === 'rotate' ? 'turn hand' : 'move hand');
});
gizmo.addEventListener('objectChange', () => refresh());
scene.add(gizmo.getHelper());

let data, saved, bodyGltf, props = {}, grip, hand, other, propObject, collision, ghost, dots = [], selected = 0;
let state = { grips: {} }, undo = [], redo = [], saveTimer = null, momentIndex = 0;

function gripState(id) {
  return state.grips[id] ??= { status: 'untouched', notes: '', edits: 0, params: null, offset: null, log: [], derived: null };
}

async function load() {
  const loader = new GLTFLoader();
  const [moments, poses, body, sword, glider] = await Promise.all([
    fetch('data/moments.json').then(r => r.json()), fetch('api/poses').then(r => r.json()),
    loader.loadAsync('data/body.glb'), loader.loadAsync('data/LinkSword.glb'), loader.loadAsync('data/LinkGlider.glb')]);
  data = moments; saved = poses; bodyGltf = body;
  props = { 'LinkSword.glb': sword.scene, 'LinkGlider.glb': glider.scene };
  if (saved.grips) state.grips = saved.grips;
  const remirror = placeGliderPoses();
  $('character').textContent = data.character[0].toUpperCase() + data.character.slice(1);
  $('status').textContent = saved.saved ? `Last saved ${stamp(saved.saved.at)}` : 'Nothing saved yet';
  buildGripList();
  for (const id of remirror) select(id);
  select(data.grips[0].id);
  try { if (!localStorage.getItem('grip-poser-help')) $('help').hidden = false; } catch { $('help').hidden = false; }
}

function stamp(s) { return s ? `${s.slice(9, 11)}:${s.slice(11, 13)}` : ''; }

function buildGripList() {
  const box = $('grips'); box.innerHTML = '';
  for (const g of data.grips) {
    const b = document.createElement('button');
    b.className = 'grip' + (grip && g.id === grip.id ? ' on' : '');
    const st = gripState(g.id).status;
    b.innerHTML = `<span>${g.label}</span><span class="badge ${st}">${st === 'untouched' ? 'not started' : st}</span>`;
    b.onclick = () => select(g.id);
    box.appendChild(b);
  }
}

function makeHand(g, side, ghostly) {
  const h = new Hand(bodyGltf.scene, side, ghostly);
  const typical = g.moments[g.typical];
  h.place(side === g.side ? typical.hand : typical.other);
  h.axes();
  return h;
}

function startParams(h, g) {
  return h.digits.map((d, k) => d.map((b, j) => {
    const q = g.start.bones[b.name];
    return q ? h.paramsFrom(k, j, new THREE.Quaternion().fromArray(q)) : [0, 0, 0];
  }));
}

function select(id) {
  grip = data.grips.find(g => g.id === id);
  for (const o of [hand?.group, other?.group, propObject, collision, ghost]) if (o) scene.remove(o);
  handMode(null);
  dots.forEach(d => scene.remove(d)); dots = [];
  hand = makeHand(grip, grip.side, false);
  const st = gripState(id);
  hand.start = startParams(hand, grip);
  hand.params = st.params ? clone(st.params) : clone(hand.start);
  if (st.offset) { hand.adjust.position.fromArray(st.offset.position); hand.adjust.quaternion.fromArray(st.offset.quaternion); }
  hand.apply();
  scene.add(hand.group);
  // the other hand on this prop, exactly as it is posed on its own grip (or as the game has it)
  const partner = partnerOf(grip), ps = partner && gripState(partner.id);
  if (partner) {
    other = makeHand(partner, partner.side, true);   // its joint axes as on its own grip, so its angles mean the same
    other.params = ps.params ? clone(ps.params) : startParams(other, partner);
    other.apply();
    other.place(placementOf(toFrame(grip, partner).multiply(holdOf(partner))));
  } else other = makeHand(grip, grip.side === 'R' ? 'L' : 'R', true);
  other.group.visible = $('show-other').checked;
  scene.add(other.group);
  // the prop and its handle
  const pm = grip.prop_mesh;
  propObject = cloneScene(props[pm.file]);   // the glider is skinned: a plain clone would draw it at its own origin
  propObject.position.fromArray(pm.position); propObject.quaternion.fromArray(pm.quaternion); propObject.scale.setScalar(pm.scale);
  propObject.traverse(o => { if (o.isMesh) { o.material = o.material.clone(); o.material.transparent = true; o.frustumCulled = false; } });
  scene.add(propObject);
  setPropLook();
  collision = handleMesh({ ...grip.handle }); collision.visible = $('show-collision').checked; scene.add(collision);
  const gp = new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(grip.start.ghost_skin.flat(), 3));
  ghost = new THREE.Points(gp, new THREE.PointsMaterial({ color: 0xbbbbbb, size: .0022 }));
  ghost.visible = $('show-ghost').checked; scene.add(ghost);
  // the joint dots
  hand.digits.forEach((d, k) => [1, 2, 3].forEach(e => {
    const m = new THREE.Mesh(new THREE.SphereGeometry(e === 3 ? .0042 : .0034, 16, 12),
      new THREE.MeshBasicMaterial({ color: COLORS[k], depthTest: false, transparent: true, opacity: .95 }));
    m.renderOrder = 10; m.userData = { digit: k, effector: e };
    const hit = new THREE.Mesh(new THREE.SphereGeometry(.008, 8, 6), new THREE.MeshBasicMaterial({ visible: false }));
    hit.userData = m.userData; m.add(hit);
    scene.add(m); dots.push(m);
  }));
  momentIndex = anchorOf(grip);
  hand.place(grip.moments[momentIndex].hand);
  if (st.remirror) { delete st.remirror; mirrorOther(); changed('mirror other hand again (glider drawn in place)'); }
  undo = []; redo = [];
  $('notes').value = st.notes || '';
  const offer = st.status === 'untouched' && ps?.params;
  $('offer').hidden = !offer;
  if (offer) $('offer-side').textContent = partner.side === 'R' ? 'right' : 'left';
  buildGripList(); buildDigits(); refresh(); frame('palm');
}

// Each grip's hand is pinned to the prop: the game's place at the moment the person posed it, then their own move.
// The pose holds through the whole animation (the game reaches the arm to it).
const matrixOf = p => new THREE.Matrix4().compose(new THREE.Vector3().fromArray(p.position),
  new THREE.Quaternion().fromArray(p.quaternion), new THREE.Vector3().setScalar(p.scale ?? 1));
function placementOf(M) {
  const position = new THREE.Vector3(), quaternion = new THREE.Quaternion(), scale = new THREE.Vector3();
  M.decompose(position, quaternion, scale);
  return { position: position.toArray(), quaternion: quaternion.toArray(), scale: scale.x };
}
const partnerOf = g => data.grips.find(o => o.prop === g.prop && o.side !== g.side);
function anchorOf(g) {   // grips posed before pinning keep the moment they were posed at
  const st = gripState(g.id);
  st.anchor ??= st.params ? (st.derived?.moment ?? st.log.at(-1)?.moment ?? g.typical) : g.typical;
  return st.anchor;
}
function holdOf(g) {   // the grip's hand bone in its own handle frame
  const st = gripState(g.id), M = matrixOf(g.moments[anchorOf(g)].hand);
  return st.offset ? M.multiply(matrixOf(st.offset)) : M;
}
// Glider poses saved before the glider was drawn in place were posed against it at its own origin and size: keep each
// hand where it was on the glider's bars. A hand that was only mirrored is mirrored again from its corrected partner.
function placeGliderPoses() {
  const remirror = [];
  let moved = false;
  for (const g of data.grips) {
    const st = state.grips[g.id];
    if (g.prop_mesh.file !== 'LinkGlider.glb' || !st?.offset || st.prop_placed) continue;
    if (st.log.length && st.log.every(l => l.action.startsWith('mirror'))) { st.remirror = true; remirror.push(g.id); }
    else {
      const p = new THREE.Vector3(), q = new THREE.Quaternion(), s = new THREE.Vector3();
      const pp = new THREE.Vector3(), pq = new THREE.Quaternion(), ps = new THREE.Vector3(), P = matrixOf(g.prop_mesh);
      holdOf(g).decompose(p, q, s); P.decompose(pp, pq, ps);
      const held = new THREE.Matrix4().compose(p.applyMatrix4(P), pq.multiply(q), new THREE.Vector3(1, 1, 1));
      st.offset = placementOf(matrixOf(g.moments[anchorOf(g)].hand).invert().multiply(held));
      st.log.push({ at: new Date().toISOString(), action: 'kept on the glider when it was drawn in place', moment: st.anchor });
    }
    st.prop_placed = moved = true;
  }
  if (moved) scheduleSave();
  return remirror;
}
const toFrame = (g, from) => matrixOf(g.prop_mesh).multiply(matrixOf(from.prop_mesh).invert());   // from's frame to g's

// The other hand's grip mirrored onto this one: its place through the prop's mirror plane (between the two handles),
// each joint through the body's own left/right mirror (the body's z: its hands lie along z at rest).

function restReflection(src, dst, a, b) {   // S with dst's rest frame of b = Mirror x src's rest frame of a x S
  const Ra = new THREE.Matrix4().extractRotation(src.restWorld.get(a.name));
  const Rb = new THREE.Matrix4().extractRotation(dst.restWorld.get(b.name));
  return new THREE.Matrix4().makeScale(1, 1, -1).multiply(Ra).transpose().multiply(Rb);
}
function mirrorOther() {
  const partner = partnerOf(grip);
  if (!partner) return;
  const Pd = matrixOf(grip.prop_mesh), Ps = matrixOf(partner.prop_mesh);
  const centre = (g, P) => new THREE.Vector3(g.handle.length / 2, 0, 0).applyMatrix4(P.clone().invert());
  const cd = centre(grip, Pd), cs = centre(partner, Ps);
  const n = cd.clone().sub(cs).normalize(), t = n.clone().multiplyScalar(2 * n.dot(cd.clone().add(cs).multiplyScalar(.5)));
  const plane = new THREE.Matrix4().set(
    1 - 2 * n.x * n.x, -2 * n.x * n.y, -2 * n.x * n.z, t.x,
    -2 * n.x * n.y, 1 - 2 * n.y * n.y, -2 * n.y * n.z, t.y,
    -2 * n.x * n.z, -2 * n.y * n.z, 1 - 2 * n.z * n.z, t.z,
    0, 0, 0, 1);
  const S = restReflection(other, hand, other.hand, hand.hand);
  const H = Pd.clone().multiply(plane).multiply(Ps.clone().invert()).multiply(holdOf(partner)).multiply(S);
  const offset = placementOf(matrixOf(grip.moments[momentIndex].hand).invert().multiply(H));
  hand.adjust.position.fromArray(offset.position); hand.adjust.quaternion.fromArray(offset.quaternion);
  hand.params = hand.digits.map((d, k) => d.map((b, j) => {
    const Sp = j === 0 ? S : restReflection(other, hand, other.digits[k][j - 1], d[j - 1]);
    const L = Sp.clone().transpose().multiply(new THREE.Matrix4().makeRotationFromQuaternion(other.rotationOf(k, j)))
      .multiply(restReflection(other, hand, other.digits[k][j], b));
    return hand.paramsFrom(k, j, new THREE.Quaternion().setFromRotationMatrix(L));
  }));
  hand.apply(); refresh();
}

function clone(v) { return JSON.parse(JSON.stringify(v)); }

function setPropLook() {
  const op = +$('prop-opacity').value;
  propObject.visible = $('show-prop').checked;
  propObject.traverse(o => { if (o.isMesh) { o.material.opacity = op; o.material.depthWrite = op > .95; } });
}

// ------------------------------------------------------------------------------------------------ contact
function contact(h) {
  const v = new THREE.Vector3(), handle = grip.handle;
  const digits = NAMES.map(() => ({ min: Infinity, inside: 0, touching: 0 }));
  const palm = { min: Infinity, inside: 0, touching: 0 };
  for (let i = 0; i < h.vertexDigit.length; i++) {
    h.mesh.getVertexPosition(i, v);
    const d = outside(handle, v), k = h.vertexDigit[i], s = k >= 0 ? digits[k] : palm;
    s.min = Math.min(s.min, d);
    if (d < 0) s.inside++; else if (d < TOUCH) s.touching++;
    if (h === hand) {
      const c = h.colors;
      if (d < 0) { const t = Math.min(1, -d / .003); c[i * 3] = 1; c[i * 3 + 1] = .45 - .35 * t; c[i * 3 + 2] = .45 - .35 * t; }
      else if (d < TOUCH) { c[i * 3] = .45; c[i * 3 + 1] = 1; c[i * 3 + 2] = .55; }
      else { c[i * 3] = 1; c[i * 3 + 1] = 1; c[i * 3 + 2] = 1; }
    }
  }
  if (h === hand) h.mesh.geometry.attributes.color.needsUpdate = true;
  return { digits, palm };
}

function capsules(h) {   // the game's own measure: each segment's capsule (skin radius) from the handle, cm
  const handle = grip.handle;
  return h.digits.map((d, k) => {
    const p = h.points(k);
    return [0, 1, 2].map(s => {
      let least = Infinity;
      for (let i = 0; i <= 16; i++) least = Math.min(least, outside(handle, p[s].clone().lerp(p[s + 1], i / 16)));
      return +((least * 100) - SKIN[k]).toFixed(3);
    });
  });
}

function describe(s) {
  if (s.inside) return [`${(-s.min * 1000).toFixed(1)} mm in`, 'in'];
  if (s.touching) return ['touching', 'ok'];
  return [`${(s.min * 1000).toFixed(1)} mm gap`, ''];
}

function refresh() {
  hand.group.updateMatrixWorld(true);
  const c = contact(hand);
  hand.lastContact = c;
  NAMES.forEach((n, k) => {
    const chip = document.querySelector(`.chip[data-digit="${k}"] .m`);
    if (!chip) return;
    const [text, cls] = describe(c.digits[k]);
    chip.textContent = text; chip.className = 'm ' + cls;
  });
  const [ptext, pcls] = describe(c.palm);
  const deepest = Math.min(...c.digits.map(d => d.min), c.palm.min);
  $('readout').innerHTML = `Palm: <span class="${pcls}">${ptext}</span> · deepest skin ` +
    (deepest < 0 ? `<span class="in">${(-deepest * 1000).toFixed(1)} mm inside</span>` : `<span class="ok">none inside</span>`);
  dots.forEach(m => m.position.copy(hand.points(m.userData.digit)[m.userData.effector]));
  const moved = hand.adjust.position.length() * 1000, turned = THREE.MathUtils.radToDeg(2 * Math.acos(Math.min(1, Math.abs(hand.adjust.quaternion.w))));
  $('hand-offset').textContent = moved < .05 && turned < .05 ? 'Where the game holds it.'
    : `Moved ${moved.toFixed(1)} mm and turned ${turned.toFixed(1)}° from where the game holds it.`;
  dots.forEach(m => { m.visible = $('show-dots').checked; m.scale.setScalar(m.userData.digit === selected ? 1.25 : 1); });
  syncSliders();
}

// ------------------------------------------------------------------------------------------------ controls
function buildDigits() {
  const box = $('digits'); box.innerHTML = '';
  NAMES.forEach((n, k) => {
    const c = document.createElement('div');
    c.className = 'chip' + (k === selected ? ' sel' : ''); c.dataset.digit = k;
    c.innerHTML = `<i style="background:${COLORS[k]}"></i>${n} <span class="m"></span>`;
    c.onclick = () => { selected = k; buildDigits(); refresh(); };
    box.appendChild(c);
  });
  const sl = $('sliders'); sl.innerHTML = '';
  JOINTS.forEach((jn, j) => {
    const div = document.createElement('div'); div.className = 'joint';
    div.innerHTML = `<div class="name">${NAMES[selected]}, ${jn} joint</div>`;
    ['Bend', 'Spread', 'Twist'].forEach((label, dof) => {
      const [lo, hi] = hand.limits(selected, j)[dof], value = hand.params[selected][j][dof];
      const row = document.createElement('label'); row.className = 'slider';
      row.innerHTML = `<span>${label}</span><input type="range" step="0.5" min="${Math.min(lo, Math.floor(value))}" max="${Math.max(hi, Math.ceil(value))}" value="${value}" data-j="${j}" data-dof="${dof}"><span></span>`;
      const input = row.querySelector('input');
      input.addEventListener('pointerdown', () => pushUndo());
      input.addEventListener('keydown', () => pushUndo());
      input.addEventListener('input', () => { hand.params[selected][j][dof] = +input.value; hand.apply(); refresh(); });
      input.addEventListener('change', () => changed(`slider ${NAMES[selected]} ${jn} ${label}`));
      div.appendChild(row);
    });
    sl.appendChild(div);
  });
  syncSliders();
}

function syncSliders() {
  document.querySelectorAll('#sliders input').forEach(input => {
    const v = hand.params[selected][+input.dataset.j][+input.dataset.dof];
    if (document.activeElement !== input) input.value = v;
    input.nextElementSibling.textContent = `${v.toFixed(0)}°`;
  });
}

function snapshot() {
  return { params: clone(hand.params), offset: { position: hand.adjust.position.toArray(), quaternion: hand.adjust.quaternion.toArray() } };
}
function restore(s) {
  hand.params = clone(s.params);
  hand.adjust.position.fromArray(s.offset.position); hand.adjust.quaternion.fromArray(s.offset.quaternion);
  hand.apply(); refresh();
}
function pushUndo() { undo.push(snapshot()); if (undo.length > 200) undo.shift(); redo = []; }

function changed(action) {
  const st = gripState(grip.id);
  const s = snapshot();
  st.params = s.params; st.offset = s.offset; st.edits++;
  if (st.status === 'untouched') st.status = 'draft';
  $('offer').hidden = true;
  st.log.push({ at: new Date().toISOString(), action, moment: momentIndex });
  if (st.log.length > 600) st.log.splice(0, st.log.length - 600);
  buildGripList();
  scheduleSave();
}

// dragging a joint dot
const ray = new THREE.Raycaster(), pointer = new THREE.Vector2();
let drag = null;
function pick(e) {
  const r = renderer.domElement.getBoundingClientRect();
  pointer.set((e.clientX - r.left) / r.width * 2 - 1, -(e.clientY - r.top) / r.height * 2 + 1);
  ray.setFromCamera(pointer, camera);
}
renderer.domElement.addEventListener('pointerdown', e => {
  if (!$('show-dots').checked || gizmo.dragging || gizmo.axis) return;
  pick(e);
  const hits = ray.intersectObjects(dots, true);
  if (!hits.length) return;
  const { digit, effector } = hits[0].object.userData;
  const at = hand.points(digit)[effector];
  drag = { digit, effector, plane: new THREE.Plane().setFromNormalAndCoplanarPoint(camera.getWorldDirection(new THREE.Vector3()), at) };
  if (selected !== digit) { selected = digit; buildDigits(); }
  pushUndo();
  orbit.enabled = false;
  renderer.domElement.setPointerCapture(e.pointerId);
  e.stopPropagation();
}, true);
renderer.domElement.addEventListener('pointermove', e => {
  if (!drag) return;
  pick(e);
  const target = new THREE.Vector3();
  if (!ray.ray.intersectPlane(drag.plane, target)) return;
  hand.reach(drag.digit, drag.effector, target, $('couple').checked);
  refresh();
});
renderer.domElement.addEventListener('pointerup', e => {
  if (!drag) return;
  changed(`drag ${NAMES[drag.digit]} ${['', 'middle joint', 'end joint', 'tip'][drag.effector]}`);
  drag = null; orbit.enabled = true;
  renderer.domElement.releasePointerCapture(e.pointerId);
});

function closeDigit(k) {   // open the digit clear of the handle if it is inside, then curl its joints together until its skin meets it
  const shares = [1, .9, .6], d = () => contact(hand).digits[k].min;
  const turn = step => {
    let moved = false;
    shares.forEach((share, j) => {
      const [lo, hi] = hand.limits(k, j)[0], p = hand.params[k][j];
      const next = Math.min(hi, Math.max(lo, p[0] + step * share));
      if (next !== p[0]) { p[0] = next; moved = true; }
    });
    hand.apply();
    return moved;
  };
  for (let i = 0; i < 120 && d() < TOUCH; i++) if (!turn(-1)) break;
  for (let i = 0; i < 240 && d() >= TOUCH * .5; i++) if (!turn(.5)) break;
  for (let i = 0; i < 20 && d() < 0; i++) turn(-.25);
}

$('close-all').onclick = () => { pushUndo(); [0, 1, 2, 3].forEach(closeDigit); refresh(); changed('close all fingers'); };
$('close-one').onclick = () => { pushUndo(); closeDigit(selected); refresh(); changed(`close ${NAMES[selected]}`); };
$('reset-game').onclick = () => { pushUndo(); hand.params = clone(hand.start); hand.apply(); refresh(); changed('reset to game pose'); };
$('reset-open').onclick = () => { pushUndo(); hand.params = hand.params.map(d => d.map(() => [0, 0, 0])); hand.apply(); refresh(); changed('open hand'); };
$('mirror').onclick = () => { pushUndo(); mirrorOther(); changed('mirror other hand'); };
$('offer-yes').onclick = () => $('mirror').click();
$('offer-no').onclick = () => { $('offer').hidden = true; };
function handMode(mode) {   // null, 'translate' or 'rotate': the gizmo on the hand's own adjustment, pivoting at the wrist
  $('hand-move').classList.toggle('on', mode === 'translate');
  $('hand-turn').classList.toggle('on', mode === 'rotate');
  if (!mode) { gizmo.detach(); return; }
  gizmo.attach(hand.adjust); gizmo.setMode(mode); gizmo.setSpace('local');
}
$('hand-move').onclick = () => handMode($('hand-move').classList.contains('on') ? null : 'translate');
$('hand-turn').onclick = () => handMode($('hand-turn').classList.contains('on') ? null : 'rotate');
$('hand-reset').onclick = () => {
  pushUndo(); hand.adjust.position.set(0, 0, 0); hand.adjust.quaternion.identity(); refresh(); changed('hand back to game place');
};
$('undo').onclick = () => { if (undo.length) { redo.push(snapshot()); restore(undo.pop()); changed('undo'); } };
$('redo').onclick = () => { if (redo.length) { undo.push(snapshot()); restore(redo.pop()); changed('redo'); } };
$('show-prop').onchange = setPropLook;
$('prop-opacity').oninput = setPropLook;
$('show-collision').onchange = e => { collision.visible = e.target.checked; };
$('show-ghost').onchange = e => { ghost.visible = e.target.checked; };
$('show-other').onchange = e => { other.group.visible = e.target.checked; };
$('show-dots').onchange = () => refresh();
$('notes').oninput = () => { gripState(grip.id).notes = $('notes').value; scheduleSave(); };
$('help-button').onclick = () => { $('help').hidden = false; };
$('help-close').onclick = () => { $('help').hidden = true; try { localStorage.setItem('grip-poser-help', '1'); } catch { /* private window */ } };
document.querySelectorAll('#views button').forEach(b => { b.onclick = () => frame(b.dataset.view); });
addEventListener('keydown', e => {
  if (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT' && e.target.type !== 'range' && e.target.type !== 'checkbox') return;
  if (e.key === 'z' || e.key === 'Z') (e.shiftKey ? $('redo') : $('undo')).click();
  else if (e.key === 'h') { $('show-prop').checked = !$('show-prop').checked; setPropLook(); }
  else if (e.key >= '1' && e.key <= '5') { selected = +e.key - 1; buildDigits(); refresh(); }
  else if (e.key === 'm') $('hand-move').click();
  else if (e.key === 'r') $('hand-turn').click();
  else if (e.key === 'Escape') handMode(null);
});
$('done').onclick = async () => {
  const st = gripState(grip.id);
  st.status = 'done'; st.notes = $('notes').value;
  st.log.push({ at: new Date().toISOString(), action: 'marked done', moment: momentIndex });
  const s = snapshot(); st.params = s.params; st.offset = s.offset;
  buildGripList();
  await save(true);
  const next = data.grips.find(g => gripState(g.id).status !== 'done');
  if (next) select(next.id); else $('status').textContent = 'All grips done and saved. Thank you!';
};

// ------------------------------------------------------------------------------------------------ views and saving
function frame(view) {
  const p = hand.points(1), centre = hand.hand.getWorldPosition(new THREE.Vector3()).lerp(p[1], .6);
  const knuckles = hand.digits[0][0].getWorldPosition(new THREE.Vector3()).lerp(hand.digits[3][0].getWorldPosition(new THREE.Vector3()), .5);
  const n = new THREE.Vector3(knuckles.x, 0, 0).sub(knuckles).normalize();   // toward the handle's axis
  const along = new THREE.Vector3(1, 0, 0);
  const dirs = {
    palm: n.clone().add(new THREE.Vector3(0, .35, 0)),
    back: n.clone().multiplyScalar(-1).add(new THREE.Vector3(0, .35, 0)),
    thumb: along.clone().multiplyScalar(grip.side === 'R' ? 1 : -1).add(new THREE.Vector3(0, .25, 0)),
    end: along.clone().multiplyScalar(-1).add(new THREE.Vector3(0, .1, 0)),
  };
  camera.position.copy(centre).addScaledVector(dirs[view].normalize(), .32);
  orbit.target.copy(centre);
  camera.up.set(0, 1, 0);
  orbit.update();
}

function scheduleSave() {
  $('status').textContent = 'Unsaved changes…';
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => save(false), 1500);
}

function derived() {   // what the game needs from this pose, in the handle's frame
  const c = contact(hand);
  const w = b => b.getWorldPosition(new THREE.Vector3()).toArray().map(v => +v.toFixed(5));
  const joints = {}, quaternions = {}, axes = {};
  hand.digits.forEach((d, k) => d.forEach((b, j) => {
    joints[b.name] = w(b);
    quaternions[b.name] = b.quaternion.toArray().map(v => +v.toFixed(7));
    const R = new THREE.Matrix4().extractRotation(b.matrixWorld).multiply(hand.basis[k][j]);
    axes[b.name] = { flex: new THREE.Vector3().setFromMatrixColumn(R, 0).toArray().map(v => +v.toFixed(5)),
                     along: new THREE.Vector3().setFromMatrixColumn(R, 2).toArray().map(v => +v.toFixed(5)) };
  }));
  joints[hand.hand.name] = w(hand.hand);
  return {
    moment: momentIndex, pinned: true, hand_world: { position: hand.hand.getWorldPosition(new THREE.Vector3()).toArray(),
      quaternion: hand.hand.getWorldQuaternion(new THREE.Quaternion()).toArray() },
    joints, tips: hand.digits.map((d, k) => hand.points(k)[3].toArray().map(v => +v.toFixed(5))), quaternions, axes,
    digits: NAMES.map((n, k) => ({ name: n, min_mm: +(c.digits[k].min * 1000).toFixed(2), inside_vertices: c.digits[k].inside,
                                   touching_vertices: c.digits[k].touching })),
    palm: { min_mm: +(c.palm.min * 1000).toFixed(2), inside_vertices: c.palm.inside, touching_vertices: c.palm.touching },
    capsules_cm: capsules(hand),
  };
}

function shots() {
  const out = {}, size = renderer.getSize(new THREE.Vector2()), keep = [camera.position.clone(), orbit.target.clone()];
  const dotsShown = $('show-dots').checked;
  dots.forEach(d => { d.visible = false; });
  const opacity = $('prop-opacity').value;
  $('prop-opacity').value = Math.min(opacity, .5); setPropLook();
  renderer.setSize(800, 600, false); camera.aspect = 800 / 600; camera.updateProjectionMatrix();
  for (const v of ['palm', 'back', 'thumb', 'end']) {
    frame(v); renderer.render(scene, camera);
    out[`${grip.id}-${v}`] = renderer.domElement.toDataURL('image/png');
  }
  camera.position.copy(keep[0]); orbit.target.copy(keep[1]); orbit.update();
  dots.forEach(d => { d.visible = dotsShown; });
  $('prop-opacity').value = opacity; setPropLook();
  resize(size);
  return out;
}

async function save(withShots) {
  clearTimeout(saveTimer);
  const st = gripState(grip.id);
  if (st.params) st.derived = derived();
  const body = {
    tool: 'grip-poser', version: 1, character: data.character, samples: data.samples,
    frame: data.frame, units: 'metres; angles in degrees (bend, spread, twist about each joint\'s own axes, from the rest pose)',
    grips: state.grips,
  };
  if (withShots) body.snapshots = shots();
  $('status').textContent = 'Saving…';
  try {
    const r = await fetch('api/poses', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Grip-Poser': '1' }, body: JSON.stringify(body) });
    if (!r.ok) throw new Error(await r.text());
    const out = await r.json();
    $('status').textContent = `Saved ${stamp(out.saved)}${withShots ? ' with snapshots' : ''}`;
  } catch (err) {
    $('status').textContent = `Not saved (${err.message}); retrying…`;
    saveTimer = setTimeout(() => save(withShots), 4000);
  }
}

function resize(size) {
  const s = $('stage');
  const w = size?.x ?? s.clientWidth, h = size?.y ?? s.clientHeight;
  renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix();
}
addEventListener('resize', () => resize());
resize();
renderer.setAnimationLoop(() => { orbit.update(); renderer.render(scene, camera); });
load().catch(err => { $('status').textContent = `Could not load: ${err.message}`; console.error(err); });
window.poser = { get hand() { return hand; }, get other() { return other; }, get grip() { return grip; }, get dots() { return dots; }, get prop() { return propObject; }, camera, orbit, renderer, gizmo, contact, refresh, select };
