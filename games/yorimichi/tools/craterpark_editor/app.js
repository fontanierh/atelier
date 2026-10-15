/* Crater Park editor: UI, 3D view, interaction, saving. Geometry and physics live in pieces.js (window.Park). */
(() => {
  'use strict';
  const P = window.Park, D2R = Math.PI / 180, LIFT = 680;
  const $ = s => document.querySelector(s);
  const el = (tag, attrs, ...kids) => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === 'class') e.className = v; else if (k === 'style') e.style.cssText = v;
      else if (k.startsWith('on')) e.addEventListener(k.slice(2), v); else if (v !== undefined && v !== null && v !== false) e.setAttribute(k, v === true ? '' : v);
    }
    for (const c of kids.flat()) if (c !== null && c !== undefined && c !== false) e.append(c.nodeType ? c : document.createTextNode(c));
    return e;
  };
  const fmt = (v, d = 1) => (Number.isFinite(v) ? v.toFixed(d) : '–');
  const span2 = (a, d = 1, u = '') => (a && Number.isFinite(a[0]) ? (Math.abs(a[1] - a[0]) < 0.05 ? fmt(a[0], d) : `${fmt(a[0], d)}–${fmt(a[1], d)}`) + u : '–');
  const clone = o => JSON.parse(JSON.stringify(o));

  // ---------------------------------------------------------------- state
  let park = null, built = new Map(), sim = null, terrain = null;
  let sel = new Set(), activeLine = 'L1';
  const hidden = new Set(); let solo = null;
  const settings = { speed: false, arcs: true, labels: true, snap: true, view: '3d', xray: false };
  const undoStack = [], redoStack = [];
  let rev = 0, saveTimer = null, saveState = 'saved', conflict = false;
  let editSession = null;   // coalesces slider drags into one undo step
  let mode = null;          // {kind:'place', preset, ghost} | {kind:'link', from}
  let lastPlaceHeading = null;
  const TAB = Math.random().toString(36).slice(2, 10);
  let activeAt = Date.now(), groupOffset = { dy: 0, dh: 0 }, applyingRemote = false;
  ['pointerdown', 'keydown', 'wheel'].forEach(t => window.addEventListener(t, () => { activeAt = Date.now(); }, true));

  const byId = id => park.pieces.find(p => p.id === id);
  const lineOf = id => park.lines.find(l => l.id === id) || { id, name: id, color: '#888888' };
  const visibleLine = l => !hidden.has(l) && (!solo || l === solo || l === 'S');
  const visiblePiece = p => visibleLine(p.line);

  // ---------------------------------------------------------------- terrain
  async function loadTerrain() {
    const meta = await (await fetch('data/terrain.json')).json();
    const f32 = async f => new Float32Array(await (await fetch('data/' + f)).arrayBuffer());
    const [nat, dug, outer] = await Promise.all([f32(meta.inner.layers.natural), f32(meta.inner.layers.dug), f32(meta.outer.file)]);
    terrain = { meta, layers: { natural: nat, dug }, outer, active: 'dug' };
  }
  function sampleGrid(H, nx, nz, fi, fj) {
    const i = Math.floor(fi), j = Math.floor(fj), a = fi - i, b = fj - j;
    const h = (jj, ii) => H[jj * nx + ii];
    return (1 - a) * (1 - b) * h(j, i) + a * (1 - b) * h(j, i + 1) + (1 - a) * b * h(j + 1, i) + a * b * h(j + 1, i + 1);
  }
  function groundAt(x, z) {
    if (!terrain) return null;
    const I = terrain.meta.inner;
    let fi = (x - I.x0) / I.G - 0.5, fj = (z - I.z0) / I.G - 0.5;
    if (fi >= 0 && fj >= 0 && fi < I.nx - 1 && fj < I.nz - 1) return sampleGrid(groundLayer(), I.nx, I.nz, fi, fj);
    const O = terrain.meta.outer;
    fi = (x - O.x0) / O.G; fj = (z - O.z0) / O.G;
    if (fi >= 0 && fj >= 0 && fi < O.nx - 1 && fj < O.nz - 1) return sampleGrid(terrain.outer, O.nx, O.nz, fi, fj);
    return null;
  }

  // ---------------------------------------------------------------- three.js scene
  const canvas = $('#c');
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x9fb4c8);
  scene.fog = new THREE.Fog(0x9fb4c8, 2500, 6000);
  const camera = new THREE.PerspectiveCamera(45, 1, 1.5, 12000);   // near plane 1.5 m keeps depth precise at crater scale
  const controls = new THREE.OrbitControls(camera, canvas);
  controls.enableDamping = true; controls.dampingFactor = 0.12; controls.screenSpacePanning = true;
  controls.maxPolarAngle = Math.PI * 0.495; controls.zoomSpeed = 1.4; controls.minDistance = 4;   // zooming right in must not collapse the orbit (zoom and pan scale with it)
  // zooming in close flies forward: the orbit target moves ahead instead of the orbit shrinking to nothing
  canvas.addEventListener('wheel', e => {
    if (e.deltaY >= 0) return;
    const d = camera.position.distanceTo(controls.target);
    if (d < 25) { const dir = controls.target.clone().sub(camera.position).normalize(); controls.target.addScaledVector(dir, 25 - d + 10); }
  }, { capture: true, passive: true });
  scene.add(new THREE.HemisphereLight(0xe8eef5, 0x5b4c38, 0.55));
  const sun = new THREE.DirectionalLight(0xfff1dc, 0.6); sun.position.set(-0.5, 1, 0.35); scene.add(sun);
  const SUN = new THREE.Vector3(-0.5, 1, 0.35).normalize();

  const terrainMat = (dim) => new THREE.ShaderMaterial({
    uniforms: { sunDir: { value: SUN }, dim: { value: dim }, gridOn: { value: 1.0 }, opacity: { value: 1.0 } },
    extensions: { derivatives: true },
    vertexShader: `varying vec3 vW; varying vec3 vN;
      void main(){ vec4 w = modelMatrix * vec4(position,1.0); vW = w.xyz; vN = normal; gl_Position = projectionMatrix * viewMatrix * w; }`,
    fragmentShader: `uniform vec3 sunDir; uniform float dim; uniform float gridOn; uniform float opacity; varying vec3 vW; varying vec3 vN;
      vec3 ramp(float y){ float t = clamp((y + 140.0) / 270.0, 0.0, 1.0);
        vec3 a = vec3(0.40,0.34,0.27), b = vec3(0.58,0.50,0.39), c = vec3(0.74,0.68,0.58);
        return t < 0.5 ? mix(a, b, t * 2.0) : mix(b, c, (t - 0.5) * 2.0); }
      float iso(float v){ float w = fwidth(v); return 1.0 - min(abs(fract(v - 0.5) - 0.5) / max(w, 1e-4), 1.0); }
      void main(){
        vec3 n = normalize(vN); float slope = 1.0 - n.y;
        vec3 col = ramp(vW.y);
        col = mix(col, vec3(0.47,0.42,0.38), smoothstep(0.2, 0.55, slope));
        float diff = max(dot(n, sunDir), 0.0);
        col *= 0.55 + 0.6 * diff;
        col = mix(col, col * 0.75, iso(vW.y / 5.0) * 0.5);
        col = mix(col, col * 0.55, iso(vW.y / 25.0) * 0.75);
        vec2 g = vW.xz / 100.0; vec2 gw = fwidth(g); vec2 gl = abs(fract(g - 0.5) - 0.5) / max(gw, vec2(1e-4));
        float grid = 1.0 - min(min(gl.x, gl.y), 1.0);
        col = mix(col, col * 1.25 + 0.03, grid * 0.35 * gridOn);
        gl_FragColor = vec4(col * dim, opacity);
      }`,
  });
  let innerMesh = null, outerMesh = null, rimLine = null;
  function gridMesh(H, nx, nz, x0, z0, G, step, centred, yOff, mat) {
    const cx = Math.floor((nx - 1) / step) + 1, cz = Math.floor((nz - 1) / step) + 1;
    const pos = new Float32Array(cx * cz * 3);
    let k = 0;
    for (let j = 0; j < cz; j++) for (let i = 0; i < cx; i++) {
      const ii = Math.min(i * step, nx - 1), jj = Math.min(j * step, nz - 1);
      pos[k++] = x0 + (ii + (centred ? 0.5 : 0)) * G; pos[k++] = H[jj * nx + ii] + yOff; pos[k++] = z0 + (jj + (centred ? 0.5 : 0)) * G;
    }
    const idx = new Uint32Array((cx - 1) * (cz - 1) * 6); k = 0;
    for (let j = 0; j < cz - 1; j++) for (let i = 0; i < cx - 1; i++) {
      const a = j * cx + i, b = a + 1, c = a + cx, d = c + 1;
      idx[k++] = a; idx[k++] = c; idx[k++] = b; idx[k++] = b; idx[k++] = c; idx[k++] = d;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3)); g.setIndex(new THREE.BufferAttribute(idx, 1));
    g.computeVertexNormals();
    return new THREE.Mesh(g, mat);
  }
  // the crater grid with the park's cuts (bowl holes, dug trenches) applied
  function groundLayer() { return terrain.cut && terrain.cutFor === terrain.active ? terrain.cut : terrain.layers[terrain.active]; }
  let cutSig = null;
  function cutsSignature() {
    const parts = [terrain.active];
    for (const p of park.pieces) {
      if (p.type !== 'bowl' && !(p.params && p.params.dig)) continue;
      const b = built.get(p.id); if (!b) continue;
      parts.push(p.id, b.pose.x.toFixed(2), b.pose.z.toFixed(2), b.pose.y.toFixed(2), b.pose.h.toFixed(2), JSON.stringify(p.params));
    }
    return parts.join('|');
  }
  function updateCuts() {
    const sig = cutsSignature(); if (sig === cutSig) return false;
    cutSig = sig;
    terrain.cut = P.carveGround(park, built, terrain.layers[terrain.active], terrain.meta.inner); terrain.cutFor = terrain.active;
    buildTerrain();
    for (const p of park.pieces) rebuildMesh(p.id);
    return true;
  }
  function buildTerrain() {
    if (innerMesh) { scene.remove(innerMesh); innerMesh.geometry.dispose(); }
    const I = terrain.meta.inner, O = terrain.meta.outer;
    innerMesh = gridMesh(groundLayer(), I.nx, I.nz, I.x0, I.z0, I.G, 2, true, 0, terrainMat(1.0));
    innerMesh.userData.terrain = true; scene.add(innerMesh);
    // surroundings: natural 5 m grid, sunk below the detailed crater wherever the crater grid covers it
    if (outerMesh) { scene.remove(outerMesh); outerMesh.geometry.dispose(); }
    const OH = Float32Array.from(terrain.outer), IH = groundLayer();
    for (let j = 0; j < O.nz; j++) for (let i = 0; i < O.nx; i++) {
      const x = O.x0 + i * O.G, z = O.z0 + j * O.G, fi = (x - I.x0) / I.G - 0.5, fj = (z - I.z0) / I.G - 0.5;
      if (fi >= 1 && fj >= 1 && fi < I.nx - 2 && fj < I.nz - 2) OH[j * O.nx + i] = sampleGrid(IH, I.nx, I.nz, fi, fj) - 4;
    }
    outerMesh = gridMesh(OH, O.nx, O.nz, O.x0, O.z0, O.G, 2, false, -1.0, terrainMat(0.86));
    scene.add(outerMesh);
    setGroundSeeThrough(settings.xray);
    if (rimLine) scene.remove(rimLine);
    const pts = terrain.meta.rim.map(([x, z]) => new THREE.Vector3(x, (groundAt(x, z) || 0) + 1.2, z));
    pts.push(pts[0].clone());
    rimLine = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: 0xb8402f }));
    scene.add(rimLine);
  }

  function setGroundSeeThrough(on) {
    for (const m of [innerMesh, outerMesh]) {
      if (!m) continue;
      m.material.transparent = on; m.material.uniforms.opacity.value = on ? 0.38 : 1; m.material.depthWrite = !on;
      m.material.uniforms.dim.value = (m === innerMesh ? 1.0 : 0.86); m.material.needsUpdate = true; m.renderOrder = on ? -1 : 0;
    }
  }

  // ---------------------------------------------------------------- piece meshes
  const matBase = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.88, metalness: 0, side: THREE.DoubleSide });
  const matSel = matBase.clone(); matSel.emissive = new THREE.Color(0x7a3a0c);
  const matHover = matBase.clone(); matHover.emissive = new THREE.Color(0x2c2c2c);
  const matGhost = matBase.clone(); matGhost.transparent = true; matGhost.opacity = 0.55; matGhost.depthWrite = false;
  const meshes = new Map();
  let hoverId = null;

  function geomFrom(M) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(M.pos, 3));
    g.setAttribute('normal', new THREE.Float32BufferAttribute(M.nor, 3));
    g.setAttribute('color', new THREE.Float32BufferAttribute(M.col, 3));
    g.setIndex(M.idx);
    g.computeBoundingSphere();
    return g;
  }
  function meshOpts(p) {
    const r = sim && sim.res.get(p.id);
    return { lineColour: lineOf(p.line).color, groundAt, speed: settings.speed && r && r.vst ? r.vst : null };
  }
  function rebuildMesh(id) {
    const p = byId(id), b = built.get(id);
    removeMesh(id);
    if (!p || !b) return;
    const m = new THREE.Mesh(geomFrom(P.mesh(p, b, meshOpts(p))), matBase);
    m.userData.id = id; m.userData.joins = joinKey(id);
    m.visible = visiblePiece(p);
    scene.add(m); meshes.set(id, m);
    paintMesh(id);
  }
  const joinKey = id => { const b = built.get(id); return b && b.joins ? `${b.joins.start}${b.joins.end}` : ''; };
  function removeMesh(id) { const m = meshes.get(id); if (m) { scene.remove(m); m.geometry.dispose(); meshes.delete(id); } }
  function paintMesh(id) { const m = meshes.get(id); if (m) m.material = sel.has(id) ? matSel : id === hoverId ? matHover : matBase; }
  function applyVisibility() { for (const p of park.pieces) { const m = meshes.get(p.id); if (m) m.visible = visiblePiece(p); } refreshOverlays(); renderLines(); }

  // ---------------------------------------------------------------- layout / rebuild / physics
  function relayout(changed) {
    const prev = built;
    built = P.layout(park, prev, changed || null);
    for (const p of park.pieces) if (prev.get(p.id) !== built.get(p.id) || !meshes.has(p.id) || meshes.get(p.id).userData.joins !== joinKey(p.id)) rebuildMesh(p.id);
    for (const id of [...meshes.keys()]) if (!built.has(id)) removeMesh(id);
    scheduleSim();
  }
  let simTimer = null;
  function scheduleSim() {
    clearTimeout(simTimer);
    simTimer = setTimeout(() => {
      updateCuts();
      sim = P.simulate(park, built, { groundAt });
      if (settings.speed) for (const p of park.pieces) rebuildMesh(p.id);
      refreshOverlays(); renderIssues(); renderLines(); renderInspector(true); drawProfile();
    }, 60);
  }

  // ---------------------------------------------------------------- overlays: arcs, links, ports, ring, handles, labels
  const overlay = new THREE.Group(); scene.add(overlay);
  const selOverlay = new THREE.Group(); scene.add(selOverlay);
  let ring = null, handles = [];
  const LINE_MAT = c => new THREE.LineBasicMaterial({ color: c, transparent: true, opacity: 0.95, depthTest: true });
  function clearGroup(g) { while (g.children.length) { const c = g.children.pop(); c.geometry && c.geometry.dispose(); } }
  function worstLevel(r) { if (!r) return null; let w = 'ok'; for (const l of r.issues.values()) { if (l === 'fail') return 'fail'; w = 'warn'; } return w; }
  const LEVEL_COL = { fail: 0xe5534b, warn: 0xe3b341, ok: 0x4fb477 };

  function refreshOverlays() {
    clearGroup(overlay);
    if (!park) return;
    for (const p of park.pieces) {
      if (!visiblePiece(p)) continue;
      const b = built.get(p.id); if (!b) continue;
      const r = sim && sim.res.get(p.id);
      // flight arcs
      if (settings.arcs && r && r.jump && (p.type === 'jump' || p.type === 'kicker') && Number.isFinite(r.jump.vlip[0])) {
        const s0 = p.type === 'jump' ? b.stations[b.info.lip.i] : b.stations[b.info.lip.i];
        const lift = b.info.lift, col = LEVEL_COL[worstLevel(r)];
        for (const [k, v] of r.jump.vlip.entries()) {
          const air = r.jump.air[k], th = (s0.a - lift) * D2R, h = s0.h * D2R;
          const vx = v * Math.cos(th), vy = v * Math.sin(th), pts = [];
          const maxD = Number.isFinite(air) ? air : (b.info.knuckle ? b.info.knuckle.d - b.info.lip.d + 4 : 30);
          for (let t = 0; t < 8; t += 0.04) {
            const d = vx * t; if (d > maxD) break;
            const y = s0.y + vy * t - 4.905 * t * t; pts.push(new THREE.Vector3(s0.x + d * Math.cos(h), y + 0.6, s0.z + d * Math.sin(h)));
            if (y < s0.y - 60) break;
          }
          if (pts.length > 2) overlay.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), Math.min(80, pts.length * 2), 0.35, 6, false), new THREE.MeshBasicMaterial({ color: col })));
        }
      }
      // flow links that are not physical attachments
      for (const n of p.next || []) {
        const q = byId(n), nb = built.get(n); if (!q || !nb || !b.exit || !visiblePiece(q)) continue;
        if (q.attach === p.id) continue;
        const to = q.type === 'bowl' ? null : nb.stations[0];
        if (!to) continue;
        const gap = Math.hypot(to.x - b.exit.x, to.z - b.exit.z);
        if (gap < 0.3) continue;
        const flies = p.type === 'kicker';
        const g = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(b.exit.x, b.exit.y + 1, b.exit.z), new THREE.Vector3(to.x, to.y + 1, to.z)]);
        const line = new THREE.Line(g, new THREE.LineDashedMaterial({ color: flies ? 0xdddddd : 0xe5534b, dashSize: 3, gapSize: 2 }));
        line.computeLineDistances(); overlay.add(line);
      }
    }
    refreshSelectionOverlay();
    rebuildLabels();
  }

  function selectionPivot() {
    const roots = movableRoots([...sel]);
    if (!roots.length) return null;
    if (sel.size === 1) { const b = built.get(roots[0].id); const p0 = b.pose; return new THREE.Vector3(p0.x, p0.y, p0.z); }
    let x = 0, z = 0, y = 0, n = 0;
    for (const id of sel) { const b = built.get(id); if (!b) continue; for (const s of b.stations.length ? b.stations : [{ x: b.pose.x, y: b.pose.y, z: b.pose.z }]) { x += s.x; y += s.y; z += s.z; n++; } }
    return new THREE.Vector3(x / n, y / n, z / n);
  }
  function selectionRadius() {
    let r = 8; const c = selectionPivot(); if (!c) return r;
    for (const id of sel) { const b = built.get(id); if (!b) continue; for (const s of b.stations) r = Math.max(r, Math.hypot(s.x - c.x, s.z - c.z)); }
    return sel.size === 1 ? Math.max(9, Math.min(r * 0.35, 30)) : Math.min(r * 1.05, 600);
  }
  function refreshSelectionOverlay() {
    clearGroup(selOverlay); ring = null; handles = [];
    if (!park || !sel.size) return;
    // entry / exit arrows of selected pieces
    for (const id of sel) {
      const b = built.get(id); if (!b || !visiblePiece(byId(id))) continue;
      if (b.stations.length) {
        const s = b.stations[0];
        selOverlay.add(new THREE.ArrowHelper(new THREE.Vector3(Math.cos(s.h * D2R), 0, Math.sin(s.h * D2R)), new THREE.Vector3(s.x, s.y + 2, s.z), 8, 0x4fb477, 3, 2.2));
      }
      if (b.exit) selOverlay.add(new THREE.ArrowHelper(new THREE.Vector3(Math.cos(b.exit.h * D2R), 0, Math.sin(b.exit.h * D2R)), new THREE.Vector3(b.exit.x, b.exit.y + 2, b.exit.z), 8, 0xe0672c, 3, 2.2));
    }
    // rotate ring
    const c = selectionPivot();
    if (c) {
      const R = selectionRadius();
      const g = new THREE.RingGeometry(R, R + Math.max(1.2, R * 0.06), 96); g.rotateX(-Math.PI / 2);
      ring = new THREE.Mesh(g, new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: sel.size > 1 ? 0.3 : 0.6, side: THREE.DoubleSide, depthTest: false }));
      ring.position.set(c.x, c.y + 0.4, c.z); ring.renderOrder = 5; ring.userData.ring = true;
      selOverlay.add(ring);
    }
    // bowl outline handles
    if (sel.size === 1) {
      const p = byId([...sel][0]);
      if (p && ((p.type === 'bowl' && !(built.get(p.id) && built.get(p.id).info.through)) || (p.type === 'deck' && (P.getp(p, 'outline') || []).length >= 3))) {   // a flow bowl's outline comes from its size and the runway
        const b = built.get(p.id), out = P.bowlOutlineWorld(p, b), yTop = b.pose.y + (p.type === 'bowl' ? P.num(P.getp(p, 'wall_h'), 3) : 0) + 0.4;
        const hg = new THREE.SphereGeometry(1.0, 10, 8), mg = new THREE.SphereGeometry(0.55, 8, 6);
        const hm = new THREE.MeshBasicMaterial({ color: 0xffffff, depthTest: false }), mm = new THREE.MeshBasicMaterial({ color: 0xe0672c, depthTest: false });
        out.forEach((q, i) => {
          const h = new THREE.Mesh(hg, hm); h.position.set(q[0], yTop, q[1]); h.renderOrder = 6; h.userData.handle = { id: p.id, i }; selOverlay.add(h); handles.push(h);
          const nq = out[(i + 1) % out.length];
          const m = new THREE.Mesh(mg, mm); m.position.set((q[0] + nq[0]) / 2, yTop, (q[1] + nq[1]) / 2); m.renderOrder = 6; m.userData.handle = { id: p.id, i, mid: true }; selOverlay.add(m); handles.push(m);
        });
      }
    }
  }

  // HTML labels
  const labelsEl = $('#labels');
  let labels = [];
  function rebuildLabels() {
    labelsEl.innerHTML = ''; labels = [];
    if (!park) return;
    const add = (pos, text, cls, colour, isSel) => { const e = el('div', { class: 'lab ' + (cls || '') }, text); if (colour) e.style.borderColor = colour; labelsEl.append(e); labels.push({ e, pos, sel: isSel }); };
    for (const n of park.notes || []) add(new THREE.Vector3(n.x, n.y + 3, n.z), `📌 ${n.text}`, n.author === 'claude' ? 'ok' : 'warn', null, true);
    for (const p of park.pieces) {
      if (!visiblePiece(p)) continue;
      const b = built.get(p.id); if (!b) continue;
      const L = lineOf(p.line);
      if (p.type === 'rollin' || p.start) add(new THREE.Vector3(b.pose.x, b.pose.y + 6, b.pose.z), `▶ ${L.name}`, 'start', L.color);
      if (!settings.labels) continue;
      const r = sim && sim.res.get(p.id);
      if (p.type === 'jump' || p.type === 'kicker') {
        const s = b.stations[b.info.lip.i], w = worstLevel(r);
        const v = r && r.jump && Number.isFinite(r.jump.vlip[0]) ? ` · lip ${span2(r.jump.vlip, 0)} m/s` : '';
        add(new THREE.Vector3(s.x, s.y + 4, s.z), `${p.type === 'jump' ? fmt(P.num(P.getp(p, 'open'), 0), 0) + ' m gap' : 'kicker'}${v}${w === 'fail' ? ' ✗' : w === 'ok' ? ' ✓' : ''}`, w);
      } else if (p.type === 'bowl') add(new THREE.Vector3(b.pose.x, b.pose.y + 14, b.pose.z), p.name, '');
      else if (sel.size === 1 && sel.has(p.id) && b.stations.length) { const s = b.stations[Math.floor(b.stations.length / 2)]; add(new THREE.Vector3(s.x, s.y + 4, s.z), p.name, '', null, true); }
    }
  }
  const tmpV = new THREE.Vector3();
  function placeLabels() {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    for (const L of labels) {
      tmpV.copy(L.pos).project(camera);
      if (tmpV.z > 1 || tmpV.x < -1.1 || tmpV.x > 1.1 || tmpV.y < -1.1 || tmpV.y > 1.1) { L.e.style.display = 'none'; continue; }
      if (!L.e.classList.contains('start') && !L.sel && camera.position.distanceTo(L.pos) > 950) { L.e.style.display = 'none'; continue; }
      L.e.style.display = ''; L.e.style.left = ((tmpV.x + 1) / 2 * w) + 'px'; L.e.style.top = ((1 - tmpV.y) / 2 * h) + 'px';
    }
  }

  // ---------------------------------------------------------------- camera views
  function frameBox(pts, top) {
    if (!pts.length) return;
    const box = new THREE.Box3().setFromPoints(pts);
    const c = box.getCenter(new THREE.Vector3()), size = box.getSize(new THREE.Vector3());
    const R = Math.max(30, Math.hypot(size.x, size.z) * 0.62, size.y);
    const dist = R / Math.tan(camera.fov * D2R / 2) * 1.05;
    controls.target.copy(c);
    if (top || settings.view === 'top') camera.position.set(c.x, c.y + dist, c.z + 0.01);
    else { const dir = camera.position.clone().sub(controls.target).normalize(); if (dir.y < 0.25) dir.set(0.45, 0.75, 0.5).normalize(); camera.position.copy(c).addScaledVector(dir, dist); }
    controls.update();
  }
  function selectionPoints(ids) {
    const pts = [];
    for (const id of ids) {
      const b = built.get(id), p = byId(id); if (!b) continue;
      if (b.stations.length) for (let i = 0; i < b.stations.length; i += 4) { const s = b.stations[i]; pts.push(new THREE.Vector3(s.x, s.y, s.z)); }
      else if (p.type === 'bowl') for (const q of P.bowlOutlineWorld(p, b)) pts.push(new THREE.Vector3(q[0], b.pose.y, q[1]));
      else { const L = P.num(P.getp(p, 'len'), 20) / 2, h = b.pose.h * D2R; pts.push(new THREE.Vector3(b.pose.x - L * Math.cos(h), b.pose.y, b.pose.z - L * Math.sin(h)), new THREE.Vector3(b.pose.x + L * Math.cos(h), b.pose.y, b.pose.z + L * Math.sin(h))); }
    }
    return pts;
  }
  function frameSelection() {
    const ids = sel.size ? [...sel] : park.pieces.filter(visiblePiece).map(p => p.id);
    frameBox(selectionPoints(ids));
  }
  function setView(v) {
    settings.view = v;
    $('#v3d').classList.toggle('on', v === '3d'); $('#vtop').classList.toggle('on', v === 'top');
    const t = controls.target.clone(), dist = camera.position.distanceTo(t);
    if (v === 'top') {
      controls.minPolarAngle = 0; controls.maxPolarAngle = 0.0001; controls.mouseButtons.LEFT = THREE.MOUSE.PAN;
      camera.position.set(t.x, t.y + dist, t.z + 0.01);
    } else {
      controls.minPolarAngle = 0; controls.maxPolarAngle = Math.PI * 0.495; controls.mouseButtons.LEFT = THREE.MOUSE.ROTATE;
      camera.position.set(t.x + dist * 0.4, t.y + dist * 0.7, t.z + dist * 0.6);
    }
    controls.update();
  }

  // ---------------------------------------------------------------- picking
  const raycaster = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  function setRay(e) {
    const r = canvas.getBoundingClientRect();
    ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    raycaster.setFromCamera(ndc, camera);
  }
  function pickPiece(e) {
    setRay(e);
    const objs = [...meshes.values()].filter(m => m.visible);
    const hit = raycaster.intersectObjects(objs, false)[0];
    return hit ? { id: hit.object.userData.id, point: hit.point } : null;
  }
  function pickHandle(e) {
    setRay(e);
    if (handles.length) { const h = raycaster.intersectObjects(handles, false)[0]; if (h) return { handle: h.object.userData.handle, point: h.point }; }
    if (ring) { const h = raycaster.intersectObject(ring, false)[0]; if (h) return { ring: true, point: h.point }; }
    return null;
  }
  function rayGround(e) {
    setRay(e);
    const o = raycaster.ray.origin, d = raycaster.ray.direction;
    let prev = 0, step = 3;
    for (let t = 0; t < 9000; t += step) {
      const x = o.x + d.x * t, y = o.y + d.y * t, z = o.z + d.z * t, g = groundAt(x, z);
      if (g !== null && y < g) {
        let a = prev, b = t;
        for (let k = 0; k < 20; k++) { const m = (a + b) / 2; const gm = groundAt(o.x + d.x * m, o.z + d.z * m); if (gm !== null && o.y + d.y * m < gm) b = m; else a = m; }
        return new THREE.Vector3(o.x + d.x * b, o.y + d.y * b, o.z + d.z * b);
      }
      prev = t; step = Math.min(12, 3 + t * 0.004);
    }
    // fall back: horizontal plane through the target
    const pl = new THREE.Plane(new THREE.Vector3(0, 1, 0), -controls.target.y), out = new THREE.Vector3();
    return raycaster.ray.intersectPlane(pl, out) ? out : null;
  }
  function rayPlane(e, y) { setRay(e); const pl = new THREE.Plane(new THREE.Vector3(0, 1, 0), -y), out = new THREE.Vector3(); return raycaster.ray.intersectPlane(pl, out) ? out : null; }

  // ---------------------------------------------------------------- selection helpers
  function select(ids, additive) {
    groupOffset = { dy: 0, dh: 0 };
    if (!additive) sel.clear();
    for (const id of ids) sel.add(id);
    for (const id of meshes.keys()) paintMesh(id);
    const p = sel.size ? byId([...sel][sel.size - 1]) : null;
    if (p) activeLine = p.line;
    refreshSelectionOverlay(); rebuildLabels(); renderInspector(); renderLines(); drawProfile(); updateHint();
  }
  function toggleSel(id) { if (sel.has(id)) sel.delete(id); else sel.add(id); select([], true); }
  function selectLine(lid) { select(park.pieces.filter(p => p.line === lid).map(p => p.id)); }
  // pieces of the selection whose pose is not derived from another selected piece
  function movableRoots(ids) { const s = new Set(ids); return ids.map(byId).filter(p => p && (!p.attach || !s.has(p.attach))); }
  // the root plus everything attached behind it (transitively)
  function attachedClosure(ids) {
    const out = new Set(ids), kids = new Map();
    for (const p of park.pieces) if (p.attach) { if (!kids.has(p.attach)) kids.set(p.attach, []); kids.get(p.attach).push(p.id); }
    const st = [...ids];
    while (st.length) { const id = st.pop(); for (const k of kids.get(id) || []) if (!out.has(k)) { out.add(k); st.push(k); } }
    return out;
  }

  // ---------------------------------------------------------------- undo / redo
  const snapshot = () => JSON.stringify({ pieces: park.pieces, lines: park.lines, notes: park.notes || [] });
  function pushUndo() { undoStack.push(snapshot()); if (undoStack.length > 150) undoStack.shift(); redoStack.length = 0; updateUndoButtons(); }
  function restore(s) {
    const d = JSON.parse(s); park.pieces = d.pieces; park.lines = d.lines; park.notes = d.notes || [];
    for (const id of [...sel]) if (!byId(id)) sel.delete(id);
    built = new Map(); for (const id of [...meshes.keys()]) removeMesh(id);
    relayout(null); select([...sel]); changed(false);
  }
  function undo() { if (!undoStack.length) return; redoStack.push(snapshot()); restore(undoStack.pop()); updateUndoButtons(); toast('Undone'); }
  function redo() { if (!redoStack.length) return; undoStack.push(snapshot()); restore(redoStack.pop()); updateUndoButtons(); toast('Redone'); }
  function updateUndoButtons() { $('#undo').disabled = !undoStack.length; $('#redo').disabled = !redoStack.length; }

  // ---------------------------------------------------------------- saving
  function changed(markUndo) { scheduleSave(); }
  function setSaveText(text, cls) { const s = $('#save'); s.className = cls || ''; s.innerHTML = ''; s.append(text); }
  function scheduleSave() { saveState = 'pending'; setSaveText('Unsaved changes…', 'busy'); clearTimeout(saveTimer); saveTimer = setTimeout(() => save(), 1200); }
  async function save(label, force) {
    clearTimeout(saveTimer);
    if (conflict && !force) return;
    setSaveText('Saving…', 'busy');
    const body = { park: { ...park, pieces: park.pieces, lines: park.lines, notes: park.notes || [] }, base_rev: rev, label: label || '', force: !!force, by: 'editor', tab: TAB };
    try {
      const r = await fetch('api/save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const d = await r.json();
      if (r.status === 409) {
        conflict = true;
        const s = $('#save'); s.className = 'bad'; s.innerHTML = '';
        s.append('Changed elsewhere since you opened it. ', el('button', { onclick: () => location.reload() }, 'Load theirs'), ' ', el('button', { onclick: () => { conflict = false; save(label, true); } }, 'Keep mine'));
        return;
      }
      if (!r.ok) throw new Error(d.error || r.status);
      rev = d.rev; park.rev = d.rev; saveState = 'saved'; conflict = false;
      const t = new Date(d.saved_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      setSaveText(`All changes saved · ${t}` + (d.version ? ' · version kept' : ''));
      if (label) toast(`Saved version “${label}”`);
    } catch (err) {
      saveState = 'error'; setSaveText('Not saved: the Mac is unreachable. Retrying…', 'bad');
      saveTimer = setTimeout(() => save(label), 5000);
    }
  }

  // ---------------------------------------------------------------- editing operations
  function nextId() { let m = 0; for (const p of park.pieces) { const n = +String(p.id).replace(/\D/g, ''); if (n > m) m = n; } return 'p' + (m + 1); }
  function newPiece(preset, pose, line) {
    const T = P.TYPES[preset.type];
    const p = { id: nextId(), type: preset.type, name: preset.name || T.label, line: line || activeLine, attach: null, next: [],
      x: pose.x, y: pose.y, z: pose.z, heading: pose.h, slope: pose.a || 0, params: clone({ ...T.defaults, ...(preset.params || {}) }) };
    if (preset.type === 'rollin') p.start = true;
    return p;
  }
  function addFromPalette(preset) {
    const one = sel.size === 1 ? byId([...sel][0]) : null;
    const ob = one && built.get(one.id);
    if (one && ob && ob.exit && P.TYPES[preset.type].ride && !P.TYPES[preset.type].start && preset.type !== 'bowl') {
      pushUndo();
      const p = newPiece(preset, ob.exit, one.line);
      p.attach = one.id;
      const kids = park.pieces.filter(q => q.attach === one.id);
      p.next = [...(one.next || [])];
      one.next = [p.id];
      for (const k of kids) k.attach = p.id;
      park.pieces.push(p);
      relayout(new Set([p.id])); select([p.id]); changed();
      toast(kids.length ? `Inserted ${p.name} after ${one.name}` : `Added ${p.name} after ${one.name}`);
      return;
    }
    startPlacing(preset);
  }
  function startPlacing(preset) {
    cancelMode();
    mode = { kind: 'place', preset, heading: lastPlaceHeading };
    showMode(`Click the crater to place: ${preset.name}. Q/E rotate · Esc cancels`);
  }
  function cancelMode() {
    if (mode && mode.ghost) { scene.remove(mode.ghost); mode.ghost.geometry.dispose(); }
    mode = null; showMode('');
  }
  function showMode(t) { const m = $('#mode'); m.textContent = t; m.style.display = t ? 'block' : 'none'; }
  function placementPose(pt) {
    const g = groundAt(pt.x, pt.z) || pt.y;
    let h = mode.heading;
    if (h === null || h === undefined) { const c = { x: 1300, z: 1030 }; h = Math.atan2(c.z - pt.z, c.x - pt.x) / D2R; }
    const lift = mode.preset.type === 'deck' ? (mode.preset.params && mode.preset.params.solid ? 20 : 3) : 0;
    return { x: pt.x, z: pt.z, y: g + lift, h, a: 0 };
  }
  function updateGhost(e) {
    const pt = rayGround(e); if (!pt) return;
    const pose = placementPose(pt);
    const p = newPiece(mode.preset, pose, activeLine);
    const b = P.build(p, pose);
    if (mode.ghost) { scene.remove(mode.ghost); mode.ghost.geometry.dispose(); }
    mode.ghost = new THREE.Mesh(geomFrom(P.mesh(p, b, { lineColour: lineOf(activeLine).color, groundAt })), matGhost);
    scene.add(mode.ghost); mode.lastPose = pose;
  }
  function commitPlace(e) {
    const pt = rayGround(e); if (!pt) return;
    const pose = placementPose(pt);
    pushUndo();
    const p = newPiece(mode.preset, pose, activeLine);
    if (p.type === 'bowl' && mode.preset.params && mode.preset.params.outline) p.params.outline = clone(mode.preset.params.outline);
    park.pieces.push(p);
    lastPlaceHeading = pose.h;
    cancelMode();
    relayout(new Set([p.id])); select([p.id]); changed();
    toast(`Placed ${p.name}. Drag it, Q/E to rotate, or pick another piece to add after it.`);
  }
  function deleteSelected() {
    if (!sel.size) return;
    pushUndo();
    const gone = new Set(sel);
    for (const p of park.pieces) {
      if (p.attach && gone.has(p.attach)) p.attach = null;
      p.next = (p.next || []).filter(n => !gone.has(n));
    }
    park.pieces = park.pieces.filter(p => !gone.has(p.id));
    sel.clear(); relayout(null); select([]); changed();
    toast(`Deleted ${gone.size} piece${gone.size > 1 ? 's' : ''}`);
  }
  function duplicateSelected() {
    if (!sel.size) return;
    pushUndo();
    const map = new Map(), copies = [];
    let n = +nextId().slice(1);
    for (const id of sel) map.set(id, 'p' + (n++));
    for (const id of sel) {
      const p = clone(byId(id)); p.id = map.get(id);
      p.attach = p.attach && map.has(p.attach) ? map.get(p.attach) : null;
      p.next = (p.next || []).filter(x => map.has(x)).map(x => map.get(x));
      if (!p.attach) { p.x += 15; p.z += 15; }
      p.name = p.name + ' copy';
      copies.push(p);
    }
    park.pieces.push(...copies);
    relayout(new Set(copies.map(c => c.id))); select(copies.map(c => c.id)); changed();
    toast(`Duplicated ${copies.length} piece${copies.length > 1 ? 's' : ''} (offset 15 m)`);
  }
  // move / rotate / raise the selection by a delta (keyboard and panel)
  function transformSelection(dx, dz, dy, dh, fromSlider) {
    if (!sel.size) return;
    const roots = movableRoots([...sel]);
    if (!roots.length) return;
    if (fromSlider) beginEdit('group', 'offset'); else { pushUndo(); groupOffset.dy += dy; groupOffset.dh += dh; }
    const piv = selectionPivot();
    let detached = 0;
    for (const p of roots) {
      if (p.attach) { p.detached_from = p.attach; p.attach = null; detached++; }
      if (dh) {
        const c = Math.cos(dh * D2R), s = Math.sin(dh * D2R), rx = p.x - piv.x, rz = p.z - piv.z;
        p.x = piv.x + rx * c - rz * s; p.z = piv.z + rx * s + rz * c; p.heading = P.wrap(p.heading + dh);
      }
      p.x += dx; p.z += dz; p.y += dy;
    }
    relayout(new Set(roots.map(p => p.id)));
    if (reattach(roots)) relayout(new Set(roots.map(p => p.id)));
    refreshSelectionOverlay(); changed();
    if (detached && roots.some(p => !p.attach)) toast('Detached from the piece before it. Put it back exactly and it re-attaches.');
  }
  // a piece that was detached by a move re-attaches when it lines up with that piece's end again
  function reattach(roots) {
    let any = false;
    for (const p of roots) {
      if (p.attach || !p.detached_from) continue;
      const par = byId(p.detached_from), pb = par && built.get(par.id), b = built.get(p.id);
      if (!pb || !pb.exit || !b) { delete p.detached_from; continue; }
      const e = pb.exit, o = b.pose;
      if (Math.hypot(e.x - o.x, e.z - o.z) < 0.05 && Math.abs(e.y - o.y) < 0.05 && Math.abs(P.wrap(e.h - o.h)) < 0.2) {
        p.attach = par.id; delete p.detached_from; any = true;
      }
    }
    if (any) toast('Re-attached: it lines up with the piece before it again');
    return any;
  }
  function putOnGround() {
    const roots = movableRoots([...sel]); if (!roots.length) return;
    pushUndo();
    for (const p of roots) { const b = built.get(p.id); const g = groundAt(b.pose.x, b.pose.z); if (g !== null) { if (p.attach) p.attach = null; p.y = g + (p.type === 'deck' ? 0 : 0); } }
    relayout(new Set(roots.map(p => p.id))); changed(); toast('Put on the ground');
  }

  // ---------------------------------------------------------------- pointer interaction
  const main = document.querySelector('main');
  let down = null, drag = null;
  main.addEventListener('pointerdown', e => {
    if (e.button !== 0 || !park) return;
    canvas.focus();
    if (isLocked()) { const hit = pickPiece(e); if (hit) select([hit.id]); return; }   // view only: look and select, no edits
    if (mode && mode.kind === 'place') { commitPlace(e); e.stopPropagation(); e.preventDefault(); return; }
    if (mode && mode.kind === 'note') { placeNote(e); e.stopPropagation(); e.preventDefault(); return; }
    if (mode && mode.kind === 'link') {
      const hit = pickPiece(e);
      if (hit && hit.id !== mode.from) {
        const from = byId(mode.from);
        pushUndo(); if (!from.next.includes(hit.id)) from.next.push(hit.id);
        cancelMode(); scheduleSim(); renderInspector(); changed(); toast(`${from.name} now leads to ${byId(hit.id).name}`);
      }
      e.stopPropagation(); return;
    }
    const h = pickHandle(e);
    if (h && h.handle) {
      const p = byId(h.handle.id);
      if (h.handle.mid) {   // add a point
        pushUndo(); const o = P.getp(p, 'outline'); const a = o[h.handle.i], b = o[(h.handle.i + 1) % o.length];
        p.params.outline = clone(o); p.params.outline.splice(h.handle.i + 1, 0, [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]);
        relayout(new Set([p.id])); refreshSelectionOverlay(); changed(); e.stopPropagation(); return;
      }
      if (e.altKey) {
        const o = P.getp(p, 'outline'); if (o.length > 4) { pushUndo(); p.params.outline = clone(o); p.params.outline.splice(h.handle.i, 1); relayout(new Set([p.id])); refreshSelectionOverlay(); changed(); }
        e.stopPropagation(); return;
      }
      drag = { kind: 'outline', id: p.id, i: h.handle.i, x0: e.clientX, y0: e.clientY, started: false, y: h.point.y };
      e.stopPropagation(); return;
    }
    if (h && h.ring) {
      const piv = selectionPivot();
      const g = rayPlane(e, piv.y);
      drag = { kind: 'rotate', x0: e.clientX, y0: e.clientY, started: false, piv, a0: Math.atan2(g.z - piv.z, g.x - piv.x) };
      e.stopPropagation(); return;
    }
    const hit = pickPiece(e);
    if (hit) {
      if (e.shiftKey) { toggleSel(hit.id); e.stopPropagation(); return; }
      if (!sel.has(hit.id)) select([hit.id]);
      drag = { kind: e.altKey ? 'lift' : 'move', x0: e.clientX, y0: e.clientY, started: false, plane: hit.point.y, start: hit.point.clone() };
      e.stopPropagation(); return;
    }
    down = { x: e.clientX, y: e.clientY, shift: e.shiftKey };
  }, true);

  function beginDrag() {
    drag.started = true;
    drag.snapshot = snapshot();
    drag.roots = movableRoots([...sel]);
    drag.affected = attachedClosure(drag.roots.map(p => p.id));
    labelsEl.style.display = 'none'; overlay.visible = false;
  }
  function dragVisual(dx, dz, dy, dh, piv) {
    for (const id of drag.affected) {
      const m = meshes.get(id); if (!m) continue;
      if (dh) {
        const c = Math.cos(dh * D2R), s = Math.sin(dh * D2R);
        m.rotation.y = -dh * D2R; m.position.set(piv.x - (piv.x * c - piv.z * s), dy, piv.z - (piv.x * s + piv.z * c));
      } else { m.rotation.y = 0; m.position.set(dx, dy, dz); }
    }
    selOverlay.position.set(dh ? 0 : dx, dy, dh ? 0 : dz);
  }
  let snapMarker = null;
  function findSnap(root, dx, dz) {
    if (!settings.snap || !root || !P.TYPES[root.type].ride) return null;
    const b = built.get(root.id); if (!b || !b.stations.length) return null;
    const ex = b.pose.x + dx, ez = b.pose.z + dz;
    let best = null;
    for (const p of park.pieces) {
      if (drag.affected.has(p.id) || !visiblePiece(p)) continue;
      const q = built.get(p.id); if (!q || !q.exit) continue;
      const d = Math.hypot(q.exit.x - ex, q.exit.z - ez);
      if (d < 10 && Math.abs(P.wrap(q.exit.h - b.pose.h)) < 60 && (!best || d < best.d)) best = { d, id: p.id, exit: q.exit };
    }
    return best;
  }
  window.addEventListener('pointermove', e => {
    if (!park) return;
    if (drag) {
      if (!drag.started) { if (Math.hypot(e.clientX - drag.x0, e.clientY - drag.y0) < 4) return; if (drag.kind !== 'outline') beginDrag(); else { drag.started = true; pushUndo(); } }
      if (drag.kind === 'move') {
        const g = rayPlane(e, drag.plane); if (!g) return;
        drag.dx = g.x - drag.start.x; drag.dz = g.z - drag.start.z;
        const snap = drag.roots.length === 1 && !(e.metaKey || e.ctrlKey) ? findSnap(drag.roots[0], drag.dx, drag.dz) : null;
        drag.snap = snap;
        if (snapMarker) { scene.remove(snapMarker); snapMarker = null; }
        if (snap) {
          const g2 = new THREE.RingGeometry(5, 6.5, 40); g2.rotateX(-Math.PI / 2);
          snapMarker = new THREE.Mesh(g2, new THREE.MeshBasicMaterial({ color: 0xe0672c, depthTest: false, side: THREE.DoubleSide }));
          snapMarker.position.set(snap.exit.x, snap.exit.y + 1, snap.exit.z); snapMarker.renderOrder = 7; scene.add(snapMarker);
        }
        dragVisual(drag.dx, drag.dz, 0, 0);
        hud(`move ${fmt(Math.hypot(drag.dx, drag.dz), 1)} m` + (snap ? ` · release to attach to ${byId(snap.id).name}` : ''));
      } else if (drag.kind === 'lift') {
        const dist = camera.position.distanceTo(drag.start);
        const st = e.shiftKey ? 0.1 : 0.5;
        drag.dy = Math.round(-(e.clientY - drag.y0) * dist * 0.0016 / st) * st;
        dragVisual(0, 0, drag.dy, 0);
        hud(`raise ${drag.dy >= 0 ? '+' : ''}${fmt(drag.dy, 1)} m`);
      } else if (drag.kind === 'rotate') {
        const g = rayPlane(e, drag.piv.y); if (!g) return;
        let dh = (Math.atan2(g.z - drag.piv.z, g.x - drag.piv.x) - drag.a0) / D2R;
        dh = P.wrap(dh); if (e.shiftKey) dh = Math.round(dh / 15) * 15; else dh = Math.round(dh);
        drag.dh = dh; dragVisual(0, 0, 0, dh, drag.piv);
        hud(`rotate ${dh >= 0 ? '+' : ''}${dh}° (Shift: 15° steps)`);
      } else if (drag.kind === 'outline') {
        const g = rayPlane(e, drag.y); if (!g) return;
        const p = byId(drag.id), b = built.get(p.id), h = -b.pose.h * D2R, rx = g.x - b.pose.x, rz = g.z - b.pose.z;
        p.params.outline = clone(P.getp(p, 'outline'));
        p.params.outline[drag.i] = [+(rx * Math.cos(h) - rz * Math.sin(h)).toFixed(2), +(rx * Math.sin(h) + rz * Math.cos(h)).toFixed(2), ...p.params.outline[drag.i].slice(2)];
        relayout(new Set([p.id])); refreshSelectionOverlay();
      }
      return;
    }
    if (mode && mode.kind === 'place') { updateGhost(e); }
    if (e.target !== canvas) return;
    const hit = e.buttons ? null : pickPiece(e);
    const nh = hit ? hit.id : null;
    if (nh !== hoverId) { const old = hoverId; hoverId = nh; if (old) paintMesh(old); if (nh) paintMesh(nh); canvas.style.cursor = nh ? 'pointer' : ''; }
    const g = e.buttons ? null : rayGround(e);
    if (g) cursorWorld = { x: +g.x.toFixed(1), z: +g.z.toFixed(1), ground_alt: +(g.y + LIFT).toFixed(1) };
    let t = g ? `x ${fmt(g.x, 0)}  z ${fmt(g.z, 0)}  ground ${fmt(g.y + LIFT, 0)} m` : '';
    if (nh) { const p = byId(nh); t += `   ·   ${lineOf(p.line).name} · ${p.name}`; }
    hud(t);
  });
  window.addEventListener('pointerup', e => {
    if (snapMarker) { scene.remove(snapMarker); snapMarker = null; }
    if (drag) {
      const d = drag; drag = null;
      labelsEl.style.display = ''; overlay.visible = true; selOverlay.position.set(0, 0, 0);
      for (const id of d.affected || []) { const m = meshes.get(id); if (m) { m.position.set(0, 0, 0); m.rotation.y = 0; } }
      if (!d.started) return;
      if (d.kind === 'outline') { changed(); renderInspector(); return; }
      undoStack.push(d.snapshot); redoStack.length = 0; updateUndoButtons();
      let detached = 0;
      for (const p of d.roots) {
        const parent = p.attach;
        if (p.attach) { p.detached_from = p.attach; p.attach = null; detached++; }
        if (d.kind === 'move') { p.x += d.dx || 0; p.z += d.dz || 0; }
        if (d.kind === 'lift') p.y = +(p.y + (d.dy || 0)).toFixed(3);
        if (d.kind === 'rotate' && d.dh) {
          const c = Math.cos(d.dh * D2R), s = Math.sin(d.dh * D2R), rx = p.x - d.piv.x, rz = p.z - d.piv.z;
          p.x = d.piv.x + rx * c - rz * s; p.z = d.piv.z + rx * s + rz * c; p.heading = P.wrap(p.heading + d.dh);
        }
        if (d.kind === 'move' && d.snap && d.roots.length === 1) {
          const tgt = byId(d.snap.id);
          if (parent && parent !== tgt.id) { const op = byId(parent); if (op) op.next = op.next.filter(n => n !== p.id); }
          p.attach = tgt.id; if (!tgt.next.includes(p.id)) tgt.next.push(p.id);
          detached = 0; toast(`Attached to the end of ${tgt.name}`);
        }
      }
      if (detached && d.kind !== 'rotate') toast('Detached: it no longer follows the piece before it (the line shows a red gap until you reconnect it)');
      relayout(new Set(d.roots.map(p => p.id)));
      if (reattach(d.roots)) relayout(new Set(d.roots.map(p => p.id)));
      if (d.kind === 'lift' && sel.size > 1) groupOffset.dy += d.dy || 0;
      if (d.kind === 'rotate' && sel.size > 1) groupOffset.dh += d.dh || 0;
      refreshSelectionOverlay(); changed(); renderInspector();
      return;
    }
    if (down) {
      if (Math.hypot(e.clientX - down.x, e.clientY - down.y) < 4 && e.target === canvas && !down.shift) select([]);
      down = null;
    }
  });
  canvas.addEventListener('dblclick', e => { const hit = pickPiece(e); if (hit) { selectLine(byId(hit.id).line); toast(`Selected the whole ${lineOf(byId(hit.id).line).name} line: drag it, Q/E or the ring to rotate`); } });
  canvas.addEventListener('contextmenu', e => e.preventDefault());

  // ---------------------------------------------------------------- keyboard
  window.addEventListener('keydown', e => {
    const tag = (document.activeElement && document.activeElement.tagName) || '';
    const typing = ['INPUT', 'SELECT', 'TEXTAREA'].includes(tag) && document.activeElement.type !== 'range';
    const mod = e.metaKey || e.ctrlKey;
    if (mod && e.key.toLowerCase() === 's') { e.preventDefault(); askVersion(); return; }
    if (typing) { if (e.key === 'Escape') document.activeElement.blur(); return; }
    if (isLocked() && !['Escape', 'f', 'F', '?'].includes(e.key)) { if (!['Meta', 'Control', 'Shift', 'Alt'].includes(e.key)) toast('Claude is editing: view only until it finishes'); e.preventDefault(); return; }
    if (mod && e.key.toLowerCase() === 'z') { e.preventDefault(); e.shiftKey ? redo() : undo(); return; }
    if (mod && e.key.toLowerCase() === 'y') { e.preventDefault(); redo(); return; }
    if (mod && e.key.toLowerCase() === 'd') { e.preventDefault(); duplicateSelected(); return; }
    if (mod && e.key.toLowerCase() === 'a') { e.preventDefault(); select(park.pieces.filter(visiblePiece).map(p => p.id)); return; }
    const big = e.shiftKey;
    switch (e.key) {
      case 'Escape': if (ride) stopRide(); else if (mode) cancelMode(); else select([]); break;
      case 'r': case 'R': startRide(); break;
      case 'n': case 'N': startNote(); break;
      case 'Delete': case 'Backspace': deleteSelected(); break;
      case 'ArrowLeft': case 'ArrowRight': case 'ArrowUp': case 'ArrowDown': {
        e.preventDefault();
        const st = big ? 10 : 1;
        // screen-relative nudge on the ground plane
        const f = new THREE.Vector3(); camera.getWorldDirection(f); f.y = 0;
        if (f.lengthSq() < 1e-6) f.set(0, 0, -1); f.normalize();
        const r = new THREE.Vector3(-f.z, 0, f.x);
        const v = e.key === 'ArrowUp' ? f : e.key === 'ArrowDown' ? f.clone().negate() : e.key === 'ArrowRight' ? r : r.clone().negate();
        const ax = Math.abs(v.x) > Math.abs(v.z) ? [Math.sign(v.x) * st, 0] : [0, Math.sign(v.z) * st];
        transformSelection(ax[0], ax[1], 0, 0); break;
      }
      case 'PageUp': case ']': e.preventDefault(); transformSelection(0, 0, big ? 5 : 0.5, 0); break;
      case 'PageDown': case '[': e.preventDefault(); transformSelection(0, 0, big ? -5 : -0.5, 0); break;
      case 'q': case 'Q': if (mode && mode.kind === 'place') { mode.heading = (mode.heading ?? mode.lastPose?.h ?? 0) - (big ? 15 : 5); } else transformSelection(0, 0, 0, big ? -15 : -5); break;
      case 'e': case 'E': if (mode && mode.kind === 'place') { mode.heading = (mode.heading ?? mode.lastPose?.h ?? 0) + (big ? 15 : 5); } else transformSelection(0, 0, 0, big ? 15 : 5); break;
      case 'g': case 'G': putOnGround(); break;
      case 'f': case 'F': frameSelection(); break;
      case 't': case 'T': setView('top'); break;
      case 'v': case 'V': setView('3d'); break;
      case 's': case 'S': toggleSetting('speed'); break;
      case 'a': case 'A': toggleSetting('arcs'); break;
      case 'l': case 'L': toggleSetting('labels'); break;
      case 'x': case 'X': toggleSetting('xray'); break;
      case '?': openModal('help'); break;
      default: return;
    }
  });

  // ---------------------------------------------------------------- palette
  const tplOutline = name => { const b = park && park.pieces.find(p => p.type === 'bowl' && p.name.toLowerCase().includes(name)); return b ? clone(P.getp(b, 'outline')) : null; };
  const PALETTE = [
    ['Runways', [
      { type: 'run', name: 'Straight run', sub: '40 m, −5°', params: { len: 40, slope: -5 } },
      { type: 'run', name: 'Turn right', sub: '90°, R 60 m', params: { len: 94.2, turn: 90, slope: -5 } },
      { type: 'run', name: 'Turn left', sub: '90°, R 60 m', params: { len: 94.2, turn: -90, slope: -5 } },
      { type: 'run', name: 'Bend', sub: '30°, R 80 m', params: { len: 41.9, turn: 30, slope: -5 } },
    ]],
    ['Vert and transitions', [
      { type: 'run', name: 'Vert corner right', sub: '90°, 9 m wall', params: { len: 18.85, turn: 90, slope: 0, wl: { h: 9, R: 8 }, deck: 3 } },
      { type: 'run', name: 'Vert corner left', sub: '90°, 9 m wall', params: { len: 18.85, turn: -90, slope: 0, wr: { h: 9, R: 8 }, deck: 3 } },
      { type: 'run', name: 'Half bowl', sub: '180°, 9 m wall', params: { len: 50.3, turn: 180, slope: 0, wl: { h: 9, R: 8 }, deck: 3 } },
      { type: 'qp', name: 'Quarter pipe', sub: '4 m', params: {} },
      { type: 'qp', name: 'Vert wall', sub: '9 m, R 8', params: { h: 9, R: 8 } },
      { type: 'run', name: 'Flared mouth', sub: '40 → 18 m', params: { len: 40, slope: -3, width: 40, width_end: 18 } },
    ]],
    ['Jumps (proven)', Object.keys(P.TEMPLATES).map(k => ({ type: 'jump', name: (k.startsWith('mega') ? 'Mega ' : 'Gap ') + P.TEMPLATES[k].open + ' m', sub: k.startsWith('mega') ? `${P.TEMPLATES[k].land_width} m landing` : 'medium', params: { ...P.TEMPLATES[k], template: k } }))],
    ['Jump parts', [
      { type: 'kicker', name: 'Kicker', sub: 'lands on the next piece', params: {} },
      { type: 'landing', name: 'Landing', sub: 'knuckle + slope', params: {} },
      { type: 'rail', name: 'Rainbow rail', sub: '30 m arch', params: {} },
    ]],
    ['Start and finish', [
      { type: 'rollin', name: 'Roll-in', sub: '30 m drop', params: {} },
      { type: 'rollin', name: 'Big drop', sub: '60 m, 45°', params: { drop: 60, steep_deg: 45, crest_R: 30, foot_R: 60 } },
      { type: 'deck', name: 'Tower deck', sub: '44 × 72 m, solid', params: { len: 72, width: 44, thick: 3, solid: true } },
      { type: 'deck', name: 'Platform', sub: '20 × 20 m', params: { solid: false } },
      { type: 'bowl', name: 'Round bowl', sub: '28 m', params: {} },
      { type: 'bowl', name: 'Prado copy', sub: 'big bowl', get params() { const o = tplOutline('prado'); return o ? { outline: o, wall_h: 10.2, wall_R: 9, deck: 3 } : { wall_h: 10.2, wall_R: 9 }; } },
      { type: 'bowl', name: 'Blue Pool copy', sub: 'kidney', get params() { const o = tplOutline('pool'); return o ? { outline: o, wall_h: 3.2, wall_R: 2.5 } : {}; } },
      { type: 'bowl', name: 'Peanut copy', sub: 'peanut', get params() { const o = tplOutline('peanut'); return o ? { outline: o, wall_h: 3.6, wall_R: 2.5 } : {}; } },
    ]],
  ];
  function renderPalette() {
    const host = $('#palette'); host.innerHTML = '';
    for (const [title, items] of PALETTE) {
      host.append(el('h3', {}, title));
      const g = el('div', { class: 'pal' });
      for (const it of items) g.append(el('button', { title: P.TYPES[it.type].label, onclick: () => addFromPalette({ type: it.type, name: it.name, params: it.params }) }, el('b', {}, it.name), el('small', {}, it.sub)));
      host.append(g);
    }
  }

  // ---------------------------------------------------------------- lines panel
  function renderLines() {
    if (!park) return;
    const host = $('#lines'); host.innerHTML = '';
    const sum = sim ? P.lineSummary(park, sim) : {};
    for (const L of park.lines) {
      const n = park.pieces.filter(p => p.line === L.id).length;
      const s = sum[L.id];
      const isSel = sel.size && [...sel].every(id => (byId(id) || {}).line === L.id) && sel.size === n;
      const vis = visibleLine(L.id);
      const colour = el('input', { type: 'color', value: L.color, style: 'position:absolute;opacity:0;width:0;height:0' });
      colour.addEventListener('input', () => { L.color = colour.value; for (const p of park.pieces) if (p.line === L.id) rebuildMesh(p.id); rebuildLabels(); });
      colour.addEventListener('change', () => { changed(); renderLines(); });
      const sw = el('button', { class: 'sw', style: `background:${L.color}`, title: 'Change colour', onclick: ev => { ev.stopPropagation(); colour.click(); } });
      const nm = el('span', { class: 'nm', title: `${L.role || ''} — double-click to rename` }, L.name);
      nm.addEventListener('dblclick', ev => {
        ev.stopPropagation();
        const inp = el('input', { type: 'text', value: L.name, style: 'width:100%' });
        nm.replaceWith(inp); inp.focus(); inp.select();
        const done = () => { pushUndo(); L.name = inp.value.trim() || L.name; changed(); renderLines(); rebuildLabels(); };
        inp.addEventListener('keydown', k => { if (k.key === 'Enter') inp.blur(); if (k.key === 'Escape') { inp.value = L.name; inp.blur(); } });
        inp.addEventListener('blur', done);
      });
      const stat = s && s.routes ? `${s.fails ? '✗ ' + s.fails : '✓'}` : (n ? '' : 'empty');
      const row = el('div', { class: 'ln' + (isSel ? ' sel' : '') + (vis ? '' : ' hid'), title: `${n} pieces. Click to select the whole line.`, onclick: () => { activeLine = L.id; selectLine(L.id); } },
        el('span', { style: 'position:relative' }, sw, colour), nm,
        el('span', { class: 'st', title: s ? `${s.fails} failing and ${s.warns} warning checks; slowest ${fmt(s.vmin, 1)} m/s` : '' }, stat),
        el('button', { title: vis ? 'Hide this line' : 'Show this line', onclick: ev => { ev.stopPropagation(); if (solo === L.id) solo = null; hidden.has(L.id) ? hidden.delete(L.id) : hidden.add(L.id); applyVisibility(); } }, vis ? '👁' : '–'),
        el('button', { class: solo === L.id ? 'on' : '', title: 'Show only this line (plus the tower and bowls)', onclick: ev => { ev.stopPropagation(); solo = solo === L.id ? null : L.id; hidden.delete(L.id); applyVisibility(); if (solo) { selectLine(L.id); frameSelection(); } } }, 'Solo'));
      host.append(row);
    }
    const al = lineOf(activeLine);
    $('.palhint').innerHTML = '';
    $('.palhint').append('New pieces join ', el('b', { style: `color:${al.color}` }, al.name), '. With a piece selected, the new piece snaps onto its end. With nothing selected, click the crater to place it.');
  }

  // ---------------------------------------------------------------- inspector
  let inspTab = 'insp';
  function setTab(t) { inspTab = t; for (const [b, pn, k] of [['#tinsp', '#insp', 'insp'], ['#tiss', '#issues', 'iss'], ['#tnotes', '#notes', 'notes']]) { $(b).classList.toggle('on', t === k); $(pn).hidden = t !== k; } if (t === 'notes') renderNotes(); }
  function numberRow(label, unit, value, opts, onInput, help) {
    const o = opts || {};
    const rng = el('input', { type: 'range', min: o.min ?? 0, max: o.max ?? 100, step: o.step || 0.1, value: value ?? 0, disabled: o.disabled });
    const nb = el('input', { type: 'number', step: o.step || 0.1, value: value === null || value === undefined ? '' : +(+value).toFixed(o.dec ?? 2), disabled: o.disabled, placeholder: o.placeholder || '' });
    rng.addEventListener('input', () => { nb.value = rng.value; onInput(+rng.value, false); });
    rng.addEventListener('change', () => { onInput(+rng.value, true); });
    nb.addEventListener('change', () => { if (nb.value === '' && o.nullable) onInput(null, true); else if (nb.value !== '') { rng.value = nb.value; onInput(+nb.value, true); } });
    const row = el('div', { class: 'row' }, el('label', { title: help || label }, label, unit ? el('span', { class: 'u' }, ` ${unit}`) : ''), rng, nb);
    return help ? [row, el('div', { class: 'help-t' }, help)] : [row];
  }
  function beginEdit(id, key) { if (!editSession || editSession.id !== id || editSession.key !== key) { pushUndo(); editSession = { id, key }; } }
  function endEdit() { editSession = null; }
  function setParam(p, key, val, commit) {
    beginEdit(p.id, key);
    p.params = p.params || {};
    if (key.includes('.')) { const [a, b] = key.split('.'); p.params[a] = { ...(P.TYPES[p.type].defaults[a] || {}), ...(p.params[a] || {}), [b]: val }; }
    else p.params[key] = val;
    if (p.type === 'jump' && key !== 'rail' && key !== 'template' && p.params.template && P.TEMPLATES[p.params.template] && key in P.TEMPLATES[p.params.template] && P.TEMPLATES[p.params.template][key] !== val) p.params.template = null;
    if (p.type === 'jump' && key === 'open' && /^(Gap|Mega) [\d.]+ m/.test(p.name)) p.name = p.name.replace(/^(Gap|Mega) [\d.]+ m/, `${val >= 40 ? 'Mega' : 'Gap'} ${+(+val).toFixed(1)} m`);
    relayout(new Set([p.id]));
    if (commit) { endEdit(); changed(); renderInspector(); rebuildLabels(); }
  }
  function setPose(p, key, val, commit) {
    beginEdit(p.id, 'pose.' + key);
    if (p.attach) { p.attach = null; toast('Detached so it can be placed freely'); }
    if (key === 'world') p.y = val - LIFT; else p[key] = val;
    relayout(new Set([p.id]));
    if (commit) { endEdit(); changed(); renderInspector(); }
  }
  function renderInspector(soft) {
    const host = $('#insp');
    if (soft && host.contains(document.activeElement) && document.activeElement.tagName === 'INPUT') { renderStats(); return; }
    host.innerHTML = '';
    if (!park) return;
    if (!sel.size) {
      const s = sim ? P.lineSummary(park, sim) : {};
      host.append(el('div', { class: 'kind', style: 'margin-left:0' }, `${park.pieces.length} pieces · ${park.lines.length} lines`));
      host.append(el('p', { class: 'note' }, el('b', {}, 'Click a piece'), ' to edit it, or ', el('b', {}, 'double-click'), ' to take its whole line. Drag pieces to move them; the pieces attached behind follow. Every dimension appears here.'));
      const tb = el('div', { class: 'stat' });
      for (const L of park.lines) { const x = s[L.id]; if (!x) continue; tb.append(el('span', {}, L.name), el('span', {}, x.routes ? `${x.fails} fails · ${x.warns} warns` : '—')); }
      host.append(el('div', { class: 'sec' }, el('b', {}, 'Lines'), tb));
      host.append(el('p', { class: 'note' }, 'Press ', el('b', {}, '?'), ' for every control.'));
      return;
    }
    if (sel.size > 1) {
      const ps = [...sel].map(byId).filter(Boolean);
      const lines = [...new Set(ps.map(p => p.line))].map(l => lineOf(l).name).join(', ');
      let len = 0; for (const p of ps) len += (built.get(p.id) || {}).len || 0;
      host.append(el('div', { class: 'ttl' }, el('b', { style: 'font-size:14px' }, `${ps.length} pieces selected`)));
      host.append(el('div', { class: 'kind' }, `${lines} · ${fmt(len, 0)} m of riding`));
      host.append(el('p', { class: 'note' }, 'Drag any of them to move them together. Drag the white ring or press Q/E to rotate them about their centre. Alt-drag or PgUp/PgDn raises them.'));
      const sl = el('select', {}, park.lines.map(L => el('option', { value: L.id, selected: ps.every(p => p.line === L.id) }, L.name)));
      sl.addEventListener('change', () => { pushUndo(); for (const p of ps) p.line = sl.value; for (const p of ps) rebuildMesh(p.id); changed(); renderLines(); rebuildLabels(); });
      host.append(el('div', { class: 'row b' }, el('label', {}, 'Line'), sl));
      host.append(el('div', { class: 'sec' }, el('b', {}, 'Offset since selected'),
        ...numberRow('Rotated by', '°', groupOffset.dh, { min: -180, max: 180, step: 1 }, (v, c) => { const d = v - groupOffset.dh; if (Math.abs(d) > 1e-9) { groupOffset.dh = v; transformSelection(0, 0, 0, d, true); } if (c) endEdit(); }, 'Back to 0 returns it to where it was when you selected it.'),
        ...numberRow('Raised by', 'm', groupOffset.dy, { min: -60, max: 60, step: 0.5 }, (v, c) => { const d = v - groupOffset.dy; if (Math.abs(d) > 1e-9) { groupOffset.dy = v; transformSelection(0, 0, d, 0, true); } if (c) endEdit(); }, 'Back to 0 returns it to where it was when you selected it.')));
      host.append(el('div', { class: 'btns' }, el('button', { onclick: frameSelection }, 'Frame'), el('button', { onclick: putOnGround }, 'Put on ground'), el('button', { onclick: duplicateSelected }, 'Duplicate'), el('button', { class: 'danger', onclick: deleteSelected }, 'Delete')));
      return;
    }
    const p = byId([...sel][0]); if (!p) return;
    const T = P.TYPES[p.type], b = built.get(p.id);
    const name = el('input', { type: 'text', value: p.name });
    name.addEventListener('change', () => { pushUndo(); p.name = name.value; changed(); rebuildLabels(); });
    host.append(el('div', { class: 'ttl' }, el('span', { class: 'sw', style: `display:inline-block;width:12px;height:12px;border-radius:3px;background:${lineOf(p.line).color}` }), name));
    const lsel = el('select', {}, park.lines.map(L => el('option', { value: L.id, selected: L.id === p.line }, L.name)));
    lsel.addEventListener('change', () => { pushUndo(); p.line = lsel.value; rebuildMesh(p.id); changed(); renderLines(); rebuildLabels(); renderInspector(); });
    host.append(el('div', { class: 'kind' }, `${T.label} · ${p.id}`));
    host.append(el('div', { class: 'row b' }, el('label', {}, 'Line'), lsel));
    host.append(el('div', { id: 'pstats' }));
    renderStats();
    // position
    const pos = el('div', { class: 'sec' }, el('b', {}, 'Position'));
    const par = p.attach ? byId(p.attach) : null;
    if (par) pos.append(el('p', { class: 'note' }, 'Follows the end of ', el('b', {}, par.name), '. Changing a value below detaches it. ', el('button', { onclick: () => { pushUndo(); p.attach = null; changed(); renderInspector(); toast('Detached'); } }, 'Detach')));
    const gIn = groundAt(b.pose.x, b.pose.z);
    pos.append(...numberRow('East (x)', 'm', p.x, { min: p.x - 200, max: p.x + 200, step: 0.5 }, (v, c) => setPose(p, 'x', v, c)));
    pos.append(...numberRow('South (z)', 'm', p.z, { min: p.z - 200, max: p.z + 200, step: 0.5 }, (v, c) => setPose(p, 'z', v, c)));
    pos.append(...numberRow('Height', 'm alt.', p.y + LIFT, { min: Math.round(p.y + LIFT - 100), max: Math.round(p.y + LIFT + 100), step: 0.5, dec: 1 }, (v, c) => setPose(p, 'world', v, c), gIn !== null ? `${fmt(p.y - gIn, 1)} m above the ground here (ground ${fmt(gIn + LIFT, 0)} m)` : ''));
    pos.append(...numberRow('Heading', '°', p.heading, { min: -180, max: 180, step: 1 }, (v, c) => setPose(p, 'heading', v, c), '0 = east, 90 = south, −90 = north'));
    if (T.ride && !T.start && !['landing', 'qp', 'bowl'].includes(p.type)) pos.append(...numberRow('Start slope', '°', p.slope, { min: -45, max: 30, step: 0.1 }, (v, c) => setPose(p, 'slope', v, c), 'Incoming slope (follows the previous piece when attached)'));
    const gbtn = [el('button', { onclick: putOnGround, title: 'G' }, 'Put on ground')];
    if (p.type === 'run') gbtn.push(el('button', { onclick: () => slopeToGround(p), title: 'Set the slope so the end meets the ground' }, 'Slope to ground at end'), el('button', { onclick: () => splitRun(p) }, 'Split in two'));
    if (!p.attach && T.ride && !T.start) gbtn.push(el('button', { onclick: () => attachNearest(p) }, 'Attach to nearest end'));
    pos.append(el('div', { class: 'btns' }, gbtn));
    host.append(pos);
    if (p.type === 'jump') host.append(gapSection(p));
    if (p.type === 'rollin') host.append(el('div', { class: 'btns' },
      el('button', { onclick: () => smoothRollin(p), title: 'Top and bottom curves meet: no straight part' }, 'Make it one smooth curve'),
      el('button', { onclick: () => { pushUndo(); p.params.turn = (P.num(P.getp(p, 'turn'), 0)) + 45; relayout(new Set([p.id])); changed(); renderInspector(); } }, 'Bend right 45°'),
      el('button', { onclick: () => { pushUndo(); p.params.turn = (P.num(P.getp(p, 'turn'), 0)) - 45; relayout(new Set([p.id])); changed(); renderInspector(); } }, 'Bend left 45°')));
    // parameters
    const prm = el('div', { class: 'sec' }, el('b', {}, 'Shape'));
    for (const d of T.params) {
      if (d.showIf && !P.getp(p, d.showIf)) continue;
      if (d.kind === 'bool') {
        const cb = el('input', { type: 'checkbox', checked: !!P.getp(p, d.key) });
        cb.addEventListener('change', () => setParam(p, d.key, cb.checked, true));
        prm.append(el('div', { class: 'row b' }, el('label', {}, d.label), el('span', {}, cb)));
        continue;
      }
      if (d.kind === 'template') {
        const cur = p.params.template && P.TEMPLATES[p.params.template] ? p.params.template : '';
        const ts = el('select', {}, el('option', { value: '' }, cur ? 'Custom' : 'Custom (edited)'), Object.keys(P.TEMPLATES).map(k => el('option', { value: k, selected: k === cur }, `${k} — ${P.TEMPLATE_NOTE[k]}`)));
        ts.addEventListener('change', () => { if (!ts.value) return; pushUndo(); Object.assign(p.params, clone(P.TEMPLATES[ts.value]), { template: ts.value }); p.name = (ts.value.startsWith('mega') ? 'Mega ' : 'Gap ') + P.TEMPLATES[ts.value].open + ' m'; relayout(new Set([p.id])); changed(); renderInspector(); rebuildLabels(); });
        prm.append(el('div', { class: 'row b' }, el('label', {}, d.label), ts));
        if (cur) prm.append(el('div', { class: 'help-t', style: 'margin-left:0' }, `Proven in the physics tests: ${P.TEMPLATE_NOTE[cur]}.`));
        else prm.append(el('div', { class: 'help-t', style: 'margin-left:0;color:var(--warn)' }, 'Custom shape: not physics-tested yet. Use the speeds and the landing check below as a guide.'));
        continue;
      }
      if (d.kind === 'outline') { prm.append(el('p', { class: 'note' }, el('b', {}, 'Shape: '), d.help, ` ${P.getp(p, 'outline').length} points.`)); continue; }
      if (p.type === 'jump' && d.key === 'open') continue;
      const v = P.getp(p, d.key);
      prm.append(...numberRow(d.label, d.unit, v, { min: d.min, max: d.max, step: d.step, nullable: d.nullable, placeholder: d.nullable ? 'same' : '' }, (val, c) => setParam(p, d.key, val, c), d.help));
    }
    host.append(prm);
    // flow
    const flow = el('div', { class: 'sec' }, el('b', {}, 'Where the rider goes next'));
    const chips = el('div', { class: 'chips' });
    for (const n of p.next || []) {
      const q = byId(n); if (!q) continue;
      chips.append(el('span', { class: 'chip', onclick: () => { select([n]); frameSelection(); }, title: q.attach === p.id ? 'attached to this end' : 'not attached: the rider must fly or there is a gap' },
        el('span', { class: 'dot ' + (q.attach === p.id ? 'ok' : p.type === 'kicker' ? 'warn' : 'fail'), style: 'margin:0' }), q.name,
        el('button', { class: 'x', title: 'Remove this link', onclick: ev => { ev.stopPropagation(); pushUndo(); p.next = p.next.filter(x => x !== n); if (q.attach === p.id) q.attach = null; relayout(new Set([q.id])); changed(); renderInspector(); } }, '×')));
    }
    if (!(p.next || []).length) chips.append(el('span', { class: 'note', style: 'margin:0' }, T.terminal ? 'The line ends here.' : 'Nowhere yet: this is a dead end.'));
    flow.append(chips);
    const fb = [el('button', { onclick: () => { cancelMode(); mode = { kind: 'link', from: p.id }; showMode(`Click the piece the rider goes to after ${p.name} · Esc cancels`); } }, 'Link to…')];
    if (T.ride && !T.start) {
      const st = el('input', { type: 'checkbox', checked: !!p.start });
      st.addEventListener('change', () => { pushUndo(); p.start = st.checked; changed(); scheduleSim(); rebuildLabels(); });
      fb.push(el('label', { class: 'note', style: 'display:inline-flex;gap:5px;align-items:center;margin:0 0 0 6px' }, st, 'Line starts here'));
    }
    flow.append(el('div', { class: 'btns' }, fb));
    host.append(flow);
    setTimeout(renderStats, 0);
    host.append(el('div', { class: 'btns', style: 'margin-top:12px' }, el('button', { onclick: frameSelection }, 'Frame (F)'), el('button', { onclick: () => selectLine(p.line) }, 'Select whole line'), el('button', { onclick: duplicateSelected }, 'Duplicate'), el('button', { class: 'danger', onclick: deleteSelected }, 'Delete')));
  }
  function renderStats() {
    const host = document.getElementById('pstats'); if (!host || sel.size !== 1) return;
    host.innerHTML = '';
    const p = byId([...sel][0]); if (!p) return;
    const r = sim && sim.res.get(p.id), b = built.get(p.id);
    const st = el('div', { class: 'stat' });
    if (b && b.len) st.append(el('span', {}, 'Length'), el('span', {}, fmt(b.len, 1) + ' m'));
    if (b && b.stations.length > 1) {
      const s0 = b.stations[0], s1 = b.stations[b.stations.length - 1];
      st.append(el('span', {}, 'Height change'), el('span', {}, fmt(s1.y - s0.y, 1) + ' m'));
      const g0 = groundAt(s0.x, s0.z), g1 = groundAt(s1.x, s1.z);
      if (g0 !== null && g1 !== null) st.append(el('span', {}, 'Above ground (start / end)'), el('span', {}, `${fmt(s0.y - g0, 1)} / ${fmt(s1.y - g1, 1)} m`));
    }
    if (r && Number.isFinite(r.vin[0])) st.append(el('span', {}, 'Speed in'), el('span', {}, span2(r.vin, 1, ' m/s')));
    if (r && Number.isFinite(r.vout[0])) st.append(el('span', {}, 'Speed out'), el('span', {}, span2(r.vout, 1, ' m/s')));
    if (r && r.jump) {
      st.append(el('span', {}, 'Lip speed'), el('span', {}, span2(r.jump.vlip, 1, ' m/s')));
      if (Number.isFinite(r.jump.air[0])) st.append(el('span', {}, 'Air (horizontal)'), el('span', {}, span2(r.jump.air, 0, ' m')));
      if (Number.isFinite(r.jump.past[0])) st.append(el('span', {}, 'Lands past knuckle'), el('span', {}, span2(r.jump.past, 1, ' m')));
      if (Number.isFinite(r.jump.impact[0])) st.append(el('span', {}, 'Impact into slope'), el('span', {}, span2(r.jump.impact, 1, ' m/s')));
    }
    if (r && r.qp) st.append(el('span', {}, 'Air above coping'), el('span', {}, span2(r.qp.air, 1, ' m')));
    if (b && p.type === 'rollin') { const fi = b.stations.findIndex(s => s.d >= (b.stations[b.stations.length - 1].d - P.num(P.getp(p, 'run'), 0))); if (r && r.vst && fi > 0 && Number.isFinite(r.vst[fi])) st.append(el('span', {}, 'Speed at the foot'), el('span', {}, fmt(r.vst[fi], 1) + ' m/s')); }
    if (r && r.arrive && Number.isFinite(r.arrive[0])) st.append(el('span', {}, 'Riders arrive at'), el('span', {}, span2(r.arrive, 1, ' m/s')));
    host.append(el('div', { class: 'sec' }, el('b', {}, 'Ride check (riders starting at 1, 4, 8 m/s)'), st));
    const jv = document.getElementById('jverdict');
    if (jv && p.type === 'jump' && b) {
      jv.innerHTML = '';
      const need = P.minLipSpeed(b), have = r && r.jump ? r.jump.vlip : null;
      let lvl = 'warn', txt;
      if (!Number.isFinite(need)) txt = 'This shape cannot clear the gap at any speed: raise the lip angle or press Fit.';
      else if (!have || !Number.isFinite(have[0])) txt = `Needs at least ${need.toFixed(1)} m/s at the lip. No roll-in reaches this jump yet.`;
      else if (have[0] >= need) { lvl = 'ok'; txt = `Speed is enough: it needs ${need.toFixed(1)} m/s at the lip and riders reach ${span2(have, 1)} m/s.`; }
      else { lvl = 'fail'; const ex = P.extraDrop(have[0], need); txt = `Too slow by ${(need - have[0]).toFixed(1)} m/s: it needs ${need.toFixed(1)} m/s at the lip, the slowest rider reaches ${have[0].toFixed(1)}. Add about ${ex.toFixed(1)} m of drop before it, shorten the gap, or press Fit.`; }
      jv.append(el('div', { class: 'iss', style: 'cursor:default' }, el('span', { class: 'dot ' + lvl }), el('span', {}, txt)));
    }
    if (r && r.afterFail && !Number.isFinite(r.vin[0])) host.append(el('p', { class: 'note' }, 'Riders only get here after an earlier problem, so the speeds shown assume they pushed on.'));
    if (r && r.issues.size) {
      const list = el('div', {});
      for (const [t, l] of r.issues) list.append(el('div', { class: 'iss', style: 'cursor:default' }, el('span', { class: 'dot ' + l }), el('span', {}, t)));
      host.append(list);
    } else if (r && r.visited) host.append(el('div', { class: 'iss', style: 'cursor:default' }, el('span', { class: 'dot ok' }), el('span', {}, 'No problems found on this piece')));
  }
  function arrivalSpeeds(p) {
    const r = sim && sim.res.get(p.id);
    if (r && Number.isFinite(r.vin[0])) {
      let a = r.vin[0], b = r.vin[1];
      if (b - a < 0.4) { const m = (a + b) / 2; a = m - 0.2; b = m + 0.2; }
      return { vin: [a, (a + b) / 2, b], from: 'line' };
    }
    const v = P.num(P.getp(p, 'assume_v'), 20);
    return { vin: [v - 0.3, v, v + 0.3], from: 'assumed' };
  }
  function gapSection(p) {
    const sec = el('div', { class: 'sec' }, el('b', {}, 'Gap'));
    sec.append(...numberRow('Gap length', 'm', P.getp(p, 'open'), { min: 3, max: 90, step: 0.5 }, (v, c) => {
      setParam(p, 'open', v, c);
      if (c && P.getp(p, 'autofit') !== false) fitJumpUI(p, true);
    }, 'Lip to knuckle. Pick the size you want; the kicker and landing can be fitted to it.'));
    const a = arrivalSpeeds(p);
    if (a.from === 'assumed') sec.append(...numberRow('Assumed arrival speed', 'm/s', P.getp(p, 'assume_v') ?? 20, { min: 5, max: 40, step: 0.5 }, (v, c) => { if (c) { pushUndo(); p.params.assume_v = v; changed(); } }, 'No roll-in reaches this jump yet, so the fit uses this speed.'));
    const auto = el('input', { type: 'checkbox', checked: P.getp(p, 'autofit') !== false });
    auto.addEventListener('change', () => { pushUndo(); p.params.autofit = auto.checked; changed(); });
    sec.append(el('div', { class: 'btns' },
      el('button', { class: 'primary', onclick: () => fitJumpUI(p, false), title: 'Choose lip angle, kicker radius, knuckle drop and landing for the speed riders arrive with' }, 'Fit kicker and landing'),
      el('label', { class: 'note', style: 'display:inline-flex;gap:5px;align-items:center;margin:0' }, auto, 'Refit when the gap changes')));
    sec.append(el('div', { id: 'jverdict' }));
    return sec;
  }
  function fitJumpUI(p, auto) {
    const b = built.get(p.id); if (!b) return;
    const a = arrivalSpeeds(p);
    const f = P.fitJump(p, b.pose, a.vin);
    if (!f.ok) {
      const extra = f.have && f.have.length && !f.fastEnough ? P.extraDrop(Math.min(...f.have), f.need) : 0;
      toast(f.why + (extra > 0.2 ? ` That is about ${extra.toFixed(1)} m more drop before the kicker, or a shorter gap.` : ''));
      return;
    }
    if (!auto) pushUndo();
    Object.assign(p.params, f.params); p.params.template = null;
    relayout(new Set([p.id])); changed(); renderInspector();
    const r = f.report, lo = r[0], hi = r[r.length - 1];
    toast(`Fitted for ${a.from === 'line' ? 'riders arriving at' : 'an assumed'} ${a.vin[0].toFixed(1)}–${a.vin[2].toFixed(1)} m/s: lip ${f.params.lip_deg}° (radius ${f.params.kick_R} m), knuckle ${f.params.drop} m below, landing ${f.params.land_deg}° × ${f.params.land_len} m. Riders land ${lo.past.toFixed(0)}–${hi.past.toFixed(0)} m past the knuckle at ≤ ${Math.max(...r.map(x => x.impact)).toFixed(1)} m/s.`);
  }
  function smoothRollin(p) {
    const D = P.num(P.getp(p, 'drop'), 30), th = P.num(P.getp(p, 'steep_deg'), 35) * D2R, o = P.num(P.getp(p, 'out_deg'), -5) * D2R;
    const R = D / Math.max(0.05, (1 - Math.cos(th)) + (Math.cos(o) - Math.cos(th)));
    pushUndo(); p.params.crest_R = +(R * 0.999).toFixed(1); p.params.foot_R = +(R * 0.999).toFixed(1);
    relayout(new Set([p.id])); changed(); renderInspector(); toast(`One smooth curve: radius ${R.toFixed(0)} m top and bottom`);
  }
  function splitRun(p) {
    pushUndo();
    const L = P.num(P.getp(p, 'len'), 40), T = P.num(P.getp(p, 'turn'), 0);
    const q = clone(p); q.id = nextId(); q.name = p.name + ' (2)'; q.attach = p.id; q.next = [...(p.next || [])];
    p.params.len = +(L / 2).toFixed(2); p.params.turn = +(T / 2).toFixed(2); q.params.len = p.params.len; q.params.turn = p.params.turn;
    if (p.params.ease_end) { p.params.ease_end = false; }
    for (const k of park.pieces) if (k.attach === p.id) k.attach = q.id;
    p.next = [q.id];
    park.pieces.push(q);
    relayout(new Set([p.id, q.id])); select([p.id]); changed(); toast('Split into two pieces');
  }
  function slopeToGround(p) {
    const b = built.get(p.id); const e = b.stations[b.stations.length - 1]; const g = groundAt(e.x, e.z); if (g === null) return;
    pushUndo();
    let lo = -45, hi = 30;
    for (let k = 0; k < 40; k++) { const m = (lo + hi) / 2; p.params.slope = m; const bb = P.build(p, b.pose); const y = bb.stations[bb.stations.length - 1].y; if (y < g) lo = m; else hi = m; }
    p.params.slope = +((lo + hi) / 2).toFixed(2);
    relayout(new Set([p.id])); changed(); renderInspector(); toast(`Slope set to ${p.params.slope}° so the end meets the ground`);
  }
  function attachNearest(p) {
    const b = built.get(p.id); let best = null;
    for (const q of park.pieces) { if (q.id === p.id || attachedClosure([p.id]).has(q.id)) continue; const qb = built.get(q.id); if (!qb || !qb.exit) continue; const d = Math.hypot(qb.exit.x - b.pose.x, qb.exit.z - b.pose.z); if (!best || d < best.d) best = { d, q }; }
    if (!best || best.d > 60) { toast('No piece end within 60 m'); return; }
    pushUndo(); p.attach = best.q.id; if (!best.q.next.includes(p.id)) best.q.next.push(p.id);
    relayout(new Set([p.id])); changed(); renderInspector(); toast(`Attached to the end of ${best.q.name} (${fmt(best.d, 0)} m away)`);
  }

  // ---------------------------------------------------------------- issues panel
  function renderIssues() {
    const host = $('#issues'); host.innerHTML = '';
    if (!sim) return;
    const rows = [];
    for (const p of park.pieces) { const r = sim.res.get(p.id); if (!r) continue; for (const [t, l] of r.issues) rows.push({ p, t, l }); }
    rows.sort((a, b) => (a.l === b.l ? 0 : a.l === 'fail' ? -1 : 1) || park.lines.indexOf(lineOf(a.p.line)) - park.lines.indexOf(lineOf(b.p.line)));
    const fails = rows.filter(r => r.l === 'fail').length;
    $('#icnt').textContent = fails || rows.length; $('#icnt').style.background = fails ? '' : '#3b3522';
    host.append(el('p', { class: 'note' }, `${fails} failing, ${rows.length - fails} warnings. Click one to go to the piece.`));
    let lastLine = null;
    for (const r of rows) {
      if (!visiblePiece(r.p)) continue;
      if (r.p.line !== lastLine) { lastLine = r.p.line; host.append(el('h3', { style: `color:${lineOf(r.p.line).color}` }, lineOf(r.p.line).name)); }
      host.append(el('div', { class: 'iss', onclick: () => { select([r.p.id]); frameSelection(); setTab('insp'); } }, el('span', { class: 'dot ' + r.l }), el('span', {}, r.t, el('small', {}, r.p.name))));
    }
  }

  // ---------------------------------------------------------------- profile chart
  const pc = $('#pc');
  let profileMap = null;
  function lineRoute(focusId) {
    const p = byId(focusId); if (!p) return null;
    const starts = park.pieces.filter(q => q.line === p.line && (q.type === 'rollin' || q.start));
    const nexts = id => (byId(id) || { next: [] }).next || [];
    for (const s of starts) {      // a path from a start through the focus piece
      const stack = [[s.id]];
      let found = null, guard = 0;
      while (stack.length && guard++ < 5000) {
        const path = stack.pop(), last = path[path.length - 1];
        if (last === focusId) { found = path; break; }
        for (const n of nexts(last)) if (!path.includes(n)) stack.push(path.concat(n));
      }
      if (found) { let cur = found[found.length - 1]; const seen = new Set(found); while (nexts(cur).length && !seen.has(nexts(cur)[0])) { cur = nexts(cur)[0]; found.push(cur); seen.add(cur); } return found; }
    }
    const path = [focusId], seen = new Set(path); let cur = focusId;
    while (nexts(cur).length && !seen.has(nexts(cur)[0])) { cur = nexts(cur)[0]; path.push(cur); seen.add(cur); }
    return path;
  }
  function drawProfile() {
    const box = $('#profile'); if (box.classList.contains('closed')) return;
    const w = pc.clientWidth, h = pc.clientHeight; if (!w || !h) return;
    pc.width = w * devicePixelRatio; pc.height = h * devicePixelRatio;
    const ctx = pc.getContext('2d'); ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0); ctx.clearRect(0, 0, w, h);
    profileMap = null;
    const focus = sel.size ? [...sel][sel.size - 1] : null;
    if (!focus || !park) { $('#ptitle').textContent = 'Line profile'; $('#pinfo').textContent = 'Select a piece to see its line from the roll-in: riding height, ground and speed.'; return; }
    const route = lineRoute(focus); if (!route) return;
    const L = lineOf(byId(focus).line);
    const pts = []; let D = 0;
    for (const id of route) {
      const b = built.get(id), p = byId(id); if (!b || !b.stations.length) continue;
      const r = sim && sim.res.get(id);
      let prevD = null;
      for (let i = 0; i < b.stations.length; i++) {
        const s = b.stations[i];
        if (prevD !== null) D += Math.abs(s.d - prevD) || 0;
        const air = p.type === 'jump' && b.segs[1] && i === b.segs[1][0];
        pts.push({ D, y: s.y, g: groundAt(s.x, s.z), v: r && r.vst ? r.vst[i] : NaN, id, air });
        prevD = s.d;
      }
    }
    if (pts.length < 2) return;
    let ymin = Infinity, ymax = -Infinity;
    for (const q of pts) { ymin = Math.min(ymin, q.y, q.g ?? q.y); ymax = Math.max(ymax, q.y, q.g ?? q.y); }
    const pad = 22, X = d => pad + d / D * (w - pad * 2), Y = y => h - 14 - (y - ymin) / Math.max(1, ymax - ymin) * (h - 26), V = v => h - 14 - v / 35 * (h - 26);
    // ground
    ctx.fillStyle = 'rgba(140,115,80,.35)'; ctx.beginPath(); ctx.moveTo(X(0), h);
    for (const q of pts) if (q.g !== null) ctx.lineTo(X(q.D), Y(q.g)); ctx.lineTo(X(D), h); ctx.fill();
    // selected range
    const fs = pts.filter(q => sel.has(q.id));
    if (fs.length) { ctx.fillStyle = 'rgba(224,103,44,.13)'; ctx.fillRect(X(fs[0].D), 0, X(fs[fs.length - 1].D) - X(fs[0].D), h); }
    // riding line
    ctx.strokeStyle = L.color; ctx.lineWidth = 2; ctx.beginPath();
    pts.forEach((q, i) => { if (i === 0 || q.air) ctx.moveTo(X(q.D), Y(q.y)); else ctx.lineTo(X(q.D), Y(q.y)); }); ctx.stroke();
    // speed
    ctx.strokeStyle = 'rgba(232,228,220,.7)'; ctx.setLineDash([4, 3]); ctx.lineWidth = 1; ctx.beginPath(); let on = false;
    for (const q of pts) { if (Number.isFinite(q.v)) { on ? ctx.lineTo(X(q.D), V(q.v)) : ctx.moveTo(X(q.D), V(q.v)); on = true; } else on = false; }
    ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle = '#9aa0a8'; ctx.font = '10px ui-monospace, Menlo, monospace';
    ctx.fillText(`${fmt(ymax + LIFT, 0)} m`, 2, 10); ctx.fillText(`${fmt(ymin + LIFT, 0)} m`, 2, h - 3);
    ctx.textAlign = 'right'; ctx.fillText('35 m/s', w - 2, 10); ctx.fillText('0', w - 2, h - 3); ctx.textAlign = 'left';
    profileMap = { pts, X, D, pad, w };
    $('#ptitle').textContent = `${L.name} profile`;
    $('#pinfo').textContent = `${fmt(D, 0)} m · line = riding surface, brown = ground, dashed = speed (0–35 m/s) · click to go to a piece`;
  }
  pc.addEventListener('click', e => {
    if (!profileMap) return;
    const r = pc.getBoundingClientRect(), x = e.clientX - r.left, d = (x - profileMap.pad) / (profileMap.w - profileMap.pad * 2) * profileMap.D;
    let best = null; for (const q of profileMap.pts) if (!best || Math.abs(q.D - d) < Math.abs(best.D - d)) best = q;
    if (best) { select([best.id]); frameSelection(); }
  });
  $('#pride').addEventListener('click', startRide);
  $('#ptoggle').addEventListener('click', () => { const b = $('#profile'); b.classList.toggle('closed'); $('#ptoggle').textContent = b.classList.contains('closed') ? '▸' : '▾'; resize(); drawProfile(); });

  // ---------------------------------------------------------------- ride preview
  let ride = null;
  const rider = new THREE.Mesh(new THREE.SphereGeometry(1.4, 16, 12), new THREE.MeshBasicMaterial({ color: 0xffe14d }));
  rider.visible = false; scene.add(rider);
  function startRide() {
    if (ride) { stopRide(); return; }
    const focus = sel.size ? [...sel][sel.size - 1] : null;
    if (!focus) { toast('Select a piece of the line you want to ride'); return; }
    const route = lineRoute(focus);
    const pts = [];
    const push = (x, y, z, v) => pts.push({ x, y: y + 1.4, z, v: Number.isFinite(v) && v > 0 ? Math.max(3, v) : 10, real: v });
    for (const id of route) {
      const p = byId(id), b = built.get(id), r = sim && sim.res.get(id); if (!b || !b.stations.length) continue;
      const st = b.stations, vst = r && r.vst;
      if (p.type === 'jump' && r && r.jump && Number.isFinite(r.jump.vlip[0])) {
        const lip = b.info.lip, s0 = st[lip.i], v = r.jump.vlip[0];
        for (let i = 0; i <= lip.i; i++) push(st[i].x, st[i].y, st[i].z, vst && vst[i]);
        const fl = P.flightOnProfile(v, lip, lip.a - b.info.lift, b.info.recv, b.info.slopeEnd);
        const ang = (lip.a - b.info.lift) * D2R, h = s0.h * D2R, T = fl.t || 2.5;
        for (let t = 0.04; t < T; t += 0.04) { const d = v * Math.cos(ang) * t, vy = v * Math.sin(ang) - 9.81 * t; push(s0.x + d * Math.cos(h), lip.y + v * Math.sin(ang) * t - 4.905 * t * t, s0.z + d * Math.sin(h), Math.hypot(v * Math.cos(ang), vy)); }
        const i0 = fl.idx ? Math.min(st.length - 1, b.segs[1][0] + fl.idx) : b.segs[1][0];
        for (let i = i0; i < st.length; i++) push(st[i].x, st[i].y, st[i].z, vst && vst[i]);
      } else if (p.type !== 'bowl' || b.info.through) for (let i = 0; i < st.length; i++) push(st[i].x, st[i].y, st[i].z, vst && vst[i]);
    }
    if (pts.length < 2) { toast('Nothing to ride from here'); return; }
    let D = 0; pts[0].D = 0;
    for (let i = 1; i < pts.length; i++) { D += Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y, pts[i].z - pts[i - 1].z); pts[i].D = D; }
    ride = { pts, i: 0, f: 0, D: 0, last: performance.now() };
    rider.visible = true; $('#pride').textContent = '■ Stop';
    toast(`Riding ${lineOf(byId(focus).line).name} from ${byId(route[0]).name} (slowest rider). Esc stops.`);
  }
  function stopRide() { ride = null; rider.visible = false; $('#pride').textContent = '▶ Ride'; }
  function stepRide(now) {
    if (!ride) return;
    const dt = Math.min(0.1, (now - ride.last) / 1000); ride.last = now;
    const pts = ride.pts;
    let a = pts[ride.i], b = pts[ride.i + 1];
    if (!b) { stopRide(); toast('Ride finished'); return; }
    ride.D += a.v * dt;
    while (b && b.D < ride.D) { ride.i++; a = pts[ride.i]; b = pts[ride.i + 1]; }
    if (!b) { stopRide(); toast('Ride finished'); return; }
    const t = (ride.D - a.D) / Math.max(1e-6, b.D - a.D);
    rider.position.set(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, a.z + (b.z - a.z) * t);
    if ($('#pfollow').checked) {
      const ahead = pts[Math.min(pts.length - 1, ride.i + 25)], dir = new THREE.Vector3(ahead.x - rider.position.x, 0, ahead.z - rider.position.z);
      if (dir.lengthSq() > 1) {
        dir.normalize();
        const want = rider.position.clone().addScaledVector(dir, -28).add(new THREE.Vector3(0, 12, 0));
        camera.position.lerp(want, 0.08); controls.target.lerp(rider.position.clone().addScaledVector(dir, 15), 0.15);
      }
    }
    const rv = Number.isFinite(a.real) ? a.real : a.v;
    hud(`riding ${fmt(rv, 1)} m/s (${fmt(rv * 3.6, 0)} km/h) · ${fmt(ride.D, 0)} of ${fmt(pts[pts.length - 1].D, 0)} m · height ${fmt(rider.position.y - 1.4 + LIFT, 0)} m`);
  }

  // ---------------------------------------------------------------- misc UI
  function toast(t) { const d = el('div', {}, t); $('#toast').append(d); setTimeout(() => d.remove(), 3800); }
  function hud(t) { $('#hud').textContent = t; }
  function updateHint() {
    const f = $('#hint'); f.innerHTML = '';
    const k = s => el('kbd', {}, s);
    const items = sel.size
      ? [['Drag', ' move'], ['Alt-drag', ' raise'], ['Q/E', ' rotate'], ['Arrows', ' nudge'], ['G', ' ground'], ['⌘D', ' copy'], ['Del', ' delete'], ['F', ' frame'], ['Esc', ' deselect']]
      : [['Click', ' select'], ['Double-click', ' select line'], ['Drag', ' orbit'], ['Right-drag', ' pan'], ['T / V', ' top / 3D'], ['⌘Z', ' undo'], ['?', ' all controls']];
    for (const [a, b] of items) f.append(el('span', {}, k(a), b));
  }
  function toggleSetting(k) {
    settings[k] = !settings[k];
    const id = { speed: '#tspeed', arcs: '#tarcs', labels: '#tlabels', snap: '#tsnap', xray: '#txray' }[k];
    $(id).classList.toggle('on', settings[k]);
    if (k === 'xray') setGroundSeeThrough(settings.xray);
    if (k === 'speed') for (const p of park.pieces) rebuildMesh(p.id);
    refreshOverlays();
  }
  function openModal(id) { $('#' + id).classList.add('open'); }
  document.querySelectorAll('.modal').forEach(m => m.addEventListener('click', e => { if (e.target === m || e.target.hasAttribute('data-close')) m.classList.remove('open'); }));
  async function openHistory() {
    openModal('history');
    const host = $('#vlist'); host.innerHTML = 'Loading…';
    const vs = await (await fetch('api/versions')).json();
    host.innerHTML = '';
    for (const v of vs) {
      const t = v.saved_at ? new Date(v.saved_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : v.file;
      host.append(el('div', { class: 'v' }, el('span', {}, el('b', {}, v.label || 'autosave'), el('small', { style: 'color:var(--muted);margin-left:8px' }, `${v.pieces ?? '?'} pieces`)), el('span', { style: 'color:var(--muted)' }, t),
        el('button', { onclick: async () => { const d = await (await fetch('api/version?f=' + encodeURIComponent(v.file))).json(); pushUndo(); park.pieces = d.pieces; park.lines = d.lines; restore(snapshot()); changed(); $('#history').classList.remove('open'); toast(`Restored “${v.label || 'autosave'}” (${t}). Undo brings back what you had.`); } }, 'Restore')));
    }
  }
  function askVersion() {
    const host = $('#save'); host.className = ''; host.innerHTML = '';
    const inp = el('input', { type: 'text', placeholder: 'Name this version', style: 'width:180px' });
    const ok = el('button', { class: 'primary', onclick: () => save(inp.value.trim() || 'named version') }, 'Save');
    inp.addEventListener('keydown', e => { if (e.key === 'Enter') ok.click(); if (e.key === 'Escape') setSaveText(saveState === 'saved' ? 'All changes saved' : 'Unsaved changes…'); });
    host.append(inp, ' ', ok); inp.focus();
  }

  $('#undo').onclick = undo; $('#redo').onclick = redo;
  $('#v3d').onclick = () => setView('3d'); $('#vtop').onclick = () => setView('top'); $('#vfocus').onclick = frameSelection;
  $('#tspeed').onclick = () => toggleSetting('speed'); $('#tarcs').onclick = () => toggleSetting('arcs'); $('#tlabels').onclick = () => toggleSetting('labels'); $('#tsnap').onclick = () => toggleSetting('snap'); $('#txray').onclick = () => toggleSetting('xray');
  $('#terrain').onchange = () => { terrain.active = $('#terrain').value; park.terrain = terrain.active; buildTerrain(); for (const p of park.pieces) rebuildMesh(p.id); scheduleSim(); changed(); };
  $('#bhelp').onclick = () => openModal('help'); $('#bhistory').onclick = openHistory; $('#bversion').onclick = askVersion;
  $('#tinsp').onclick = () => setTab('insp'); $('#tiss').onclick = () => setTab('iss'); $('#tnotes').onclick = () => setTab('notes'); $('#bnote').onclick = startNote;
  $('#showall').onclick = () => { hidden.clear(); solo = null; applyVisibility(); };
  $('#addline').onclick = () => {
    pushUndo();
    const cols = ['#d94f8a', '#20a39e', '#c9a227', '#6c8ebf', '#b5651d'];
    let n = 1; while (park.lines.some(l => l.id === 'L' + n)) n++;
    park.lines.splice(park.lines.length - (park.lines.some(l => l.id === 'S') ? 1 : 0), 0, { id: 'L' + n, name: 'Line ' + n, color: cols[n % cols.length], role: 'new line' });
    activeLine = 'L' + n; changed(); renderLines(); toast(`New line “Line ${n}”: pick a Roll-in on the left and click the crater to start it`);
  };

  // ---------------------------------------------------------------- live channel with Claude
  // The server pushes {type:'park'} after any save (Claude edits park.json through the same API) and
  // {type:'cmd', op} commands; this editor reports what it shows (camera, selection, hover) and can send a snapshot.
  function rebuildAll() {
    for (const id of [...sel]) if (!byId(id)) sel.delete(id);
    built = new Map(); for (const id of [...meshes.keys()]) removeMesh(id);
    relayout(null); select([...sel]); renderLines(); rebuildLabels();
  }
  let pulling = false;
  async function pullRemote(ev) {
    if (pulling) return; pulling = true;
    try {
      if (saveState === 'pending') await save();
      const d = await (await fetch('api/park')).json();
      if (d.rev <= rev) return;
      undoStack.push(snapshot()); if (undoStack.length > 150) undoStack.shift(); redoStack.length = 0; updateUndoButtons();
      park.pieces = d.pieces; park.lines = d.lines; park.notes = d.notes || []; rev = d.rev; park.rev = d.rev;
      if (d.terrain && d.terrain !== terrain.active) { terrain.active = d.terrain; park.terrain = d.terrain; $('#terrain').value = d.terrain; buildTerrain(); }
      applyingRemote = true; rebuildAll(); applyingRemote = false;
      const t = new Date(d.saved_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      setSaveText(`All changes saved · ${t}`);
      toast(ev.by === 'claude' ? `Claude changed the park${ev.label ? ': ' + ev.label : ''} (⌘Z undoes it)` : 'Updated from another window');
    } finally { pulling = false; }
  }
  // view-only lock while Claude edits (auto-expires so a lost unlock never strands the owner)
  let lockedUntil = 0, lockText = '';
  const isLocked = () => Date.now() < lockedUntil;
  function showLock() {
    const on = isLocked(); document.body.classList.toggle('locked', on);
    let bar = $('#lockbar');
    if (on && !bar) { bar = el('div', { id: 'lockbar' }); document.body.append(bar); }
    if (bar) { if (on) bar.textContent = `🔒 Claude is editing${lockText ? ': ' + lockText : ''}. You can look around; editing is paused.`; else bar.remove(); }
  }
  setInterval(showLock, 1000);
  async function runCmd(c) {
    const ids = (c.ids || []).filter(id => byId(id));
    switch (c.op) {
      case 'select': select(ids); if (c.frame !== false) frameSelection(); break;
      case 'selectLine': selectLine(c.line); if (c.frame !== false) frameSelection(); break;
      case 'frame': if (ids.length) select(ids); frameSelection(); break;
      case 'view': setView(c.mode === 'top' ? 'top' : '3d'); break;
      case 'camera': if (c.target) controls.target.set(...c.target); if (c.pos) camera.position.set(...c.pos); controls.update(); break;
      case 'solo': solo = c.line || null; if (solo) hidden.delete(solo); applyVisibility(); break;
      case 'show': hidden.clear(); solo = null; applyVisibility(); break;
      case 'toast': toast('Claude: ' + c.text); break;
      case 'setParam': { const p = byId(c.id); if (p) setParam(p, c.key, c.value, true); break; }
      case 'fit': { const p = byId(c.id); if (p) { select([p.id]); fitJumpUI(p, false); } break; }
      case 'transform': if (ids.length) select(ids); transformSelection(c.dx || 0, c.dz || 0, c.dy || 0, c.dh || 0); break;
      case 'ride': if (ids.length) select(ids); startRide(); break;
      case 'setting': if (c.key in settings && settings[c.key] !== !!c.value) toggleSetting(c.key); break;
      case 'snapshot': await sendSnapshot(c.req); break;
      case 'reload': location.reload(); break;
      case 'lock': lockedUntil = Date.now() + 1000 * (c.seconds || 600); lockText = c.text || ''; cancelMode(); if (drag) drag = null; showLock(); break;
      case 'unlock': lockedUntil = 0; showLock(); if (c.text) toast('Claude: ' + c.text); break;
    }
    reportView(true);
  }
  async function pollLoop() {
    let seq = 0;
    try { seq = (await (await fetch(`api/poll?init=1&tab=${TAB}`)).json()).seq; } catch (e) { /* server restarting: start from 0 */ }
    for (;;) {
      try {
        // a long-poll through the tailnet proxy can hang forever if the server restarts: give up after 35 s and re-poll
        const ac = new AbortController(), timer = setTimeout(() => ac.abort(), 35000);
        const r = await fetch(`api/poll?since=${seq}&tab=${TAB}`, { signal: ac.signal }).finally(() => clearTimeout(timer));
        const d = await r.json();
        if (d.seq < seq) seq = 0;
        for (const ev of d.events) {
          seq = Math.max(seq, ev.seq);
          if (ev.type === 'park' && ev.tab !== TAB && ev.rev > rev) await pullRemote(ev);
          else if (ev.type === 'cmd') { try { await runCmd(ev); } catch (e) { toast('Could not run ' + ev.op + ': ' + e.message); } }
        }
        seq = Math.max(seq, d.seq);
      } catch (e) { await new Promise(r => setTimeout(r, 3000)); }
    }
  }
  // what this editor shows, for Claude
  let lastViewJson = '', cursorWorld = null;
  function viewState() {
    const pieceInfo = id => { const p = byId(id); if (!p) return null; const b = built.get(id), r = sim && sim.res.get(id);
      return { id, name: p.name, type: p.type, line: lineOf(p.line).name, x: +p.x.toFixed(1), z: +p.z.toFixed(1), alt: +(p.y + LIFT).toFixed(1),
        issues: r ? [...r.issues.keys()] : [] }; };
    const w = canvas.clientWidth, h = canvas.clientHeight;
    const corners = [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([x, y]) => { raycaster.setFromCamera(new THREE.Vector2(x, y), camera); const pl = new THREE.Plane(new THREE.Vector3(0, 1, 0), -controls.target.y), o = new THREE.Vector3(); return raycaster.ray.intersectPlane(pl, o) ? [+o.x.toFixed(0), +o.z.toFixed(0)] : null; });
    const onScreen = [];
    for (const p of park.pieces) { if (!visiblePiece(p)) continue; const b = built.get(p.id); if (!b) continue; const s = b.stations.length ? b.stations[Math.floor(b.stations.length / 2)] : b.pose; tmpV.set(s.x, s.y, s.z).project(camera); if (tmpV.z < 1 && Math.abs(tmpV.x) < 1 && Math.abs(tmpV.y) < 1) onScreen.push(p.id); }
    return {
      tab: TAB, active_at: activeAt, url: location.href, viewport: [w, h], view: settings.view,
      camera: { pos: camera.position.toArray().map(v => +v.toFixed(1)), target: controls.target.toArray().map(v => +v.toFixed(1)), fov: camera.fov },
      ground_footprint: corners, selection: [...sel].slice(0, 60).map(pieceInfo), selection_count: sel.size,
      hover: hoverId ? pieceInfo(hoverId) : null, cursor: cursorWorld, solo, hidden: [...hidden], settings: { ...settings },
      inspector_tab: inspTab, on_screen: onScreen.length > 80 ? onScreen.length : onScreen, rev, unsaved: saveState !== 'saved', mode: mode ? mode.kind : null,
    };
  }
  async function reportView(force) {
    if (!park) return;
    const v = viewState(), j = JSON.stringify({ ...v, active_at: 0 });
    if (!force && j === lastViewJson) return;
    lastViewJson = j;
    try { localStorage.setItem('cpe-view', JSON.stringify({ at: Date.now(), pos: v.camera.pos, target: v.camera.target, view: v.view, solo, hidden: [...hidden], sel: [...sel] })); } catch (e) { /* storage blocked */ }
    try { await fetch('api/viewstate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(v) }); } catch (e) { /* offline */ }
  }
  async function sendSnapshot(req) {
    renderer.render(scene, camera);
    const src = canvas, W = Math.min(1600, src.width), H = Math.round(src.height * W / src.width);
    const c2 = document.createElement('canvas'); c2.width = W; c2.height = H;
    const g = c2.getContext('2d'); g.drawImage(src, 0, 0, W, H);
    const k = W / canvas.clientWidth;
    g.font = `${Math.round(11 * k)}px -apple-system, sans-serif`; g.textBaseline = 'middle';
    for (const L of labels) {      // the HTML labels, drawn where the owner sees them
      if (L.e.style.display === 'none') continue;
      const x = parseFloat(L.e.style.left) * k, y = parseFloat(L.e.style.top) * k, t = L.e.textContent.replace(/^▶\s*▶/, '▶'), tw = g.measureText(t).width + 10 * k, th = 16 * k;
      g.fillStyle = 'rgba(20,22,25,.85)'; g.fillRect(x - tw / 2, y - th * 1.2, tw, th);
      g.strokeStyle = L.e.style.borderColor || '#555'; g.strokeRect(x - tw / 2, y - th * 1.2, tw, th);
      g.fillStyle = '#e8e4dc'; g.fillText(t, x - tw / 2 + 5 * k, y - th * 0.7);
    }
    await fetch('api/snapshot', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ req: req || 'latest', png: c2.toDataURL('image/png'), view: viewState() }) });
  }

  // ---------------------------------------------------------------- notes (pins the owner or Claude can leave on the park)
  function startNote() { cancelMode(); mode = { kind: 'note' }; showMode('Click where the note goes · Esc cancels'); }
  function placeNote(e) {
    const hit = pickPiece(e), pt = hit ? hit.point : rayGround(e);
    cancelMode(); if (!pt) return;
    const r = main.getBoundingClientRect();
    const box = el('div', { style: `position:absolute;left:${e.clientX - r.left}px;top:${e.clientY - r.top}px;z-index:5;background:var(--panel);border:1px solid var(--accent);border-radius:8px;padding:6px;display:flex;gap:4px` });
    const inp = el('input', { type: 'text', placeholder: 'Note for Claude (Enter to pin)', style: 'width:260px' });
    box.append(inp); main.append(box); inp.focus();
    const done = ok => {
      if (ok && inp.value.trim()) {
        pushUndo(); park.notes = park.notes || [];
        park.notes.push({ id: 'n' + Date.now().toString(36), x: +pt.x.toFixed(1), y: +pt.y.toFixed(1), z: +pt.z.toFixed(1), text: inp.value.trim(), piece: hit ? hit.id : null, author: 'owner', at: new Date().toISOString() });
        changed(); rebuildLabels(); renderNotes(); toast('Note pinned. Claude can read it.');
      }
      box.remove();
    };
    inp.addEventListener('keydown', k => { if (k.key === 'Enter') done(true); if (k.key === 'Escape') done(false); k.stopPropagation(); });
    inp.addEventListener('blur', () => setTimeout(() => box.isConnected && done(true), 100));
  }
  function renderNotes() {
    const host = $('#notes'); if (!host) return; host.innerHTML = '';
    const ns = park.notes || [];
    host.append(el('p', { class: 'note' }, 'Pin a note on anything with ', el('b', {}, 'N'), ' (or the 📌 button): Claude sees it. Click a note to go to it.'));
    for (const n of ns) {
      host.append(el('div', { class: 'iss', onclick: () => { frameBox([new THREE.Vector3(n.x - 40, n.y, n.z - 40), new THREE.Vector3(n.x + 40, n.y, n.z + 40)]); if (n.piece && byId(n.piece)) select([n.piece]); } },
        el('span', { class: 'dot ' + (n.author === 'claude' ? 'ok' : 'warn') }),
        el('span', { style: 'flex:1' }, n.text, el('small', {}, `${n.author === 'claude' ? 'Claude' : 'You'} · ${n.piece && byId(n.piece) ? byId(n.piece).name : 'on the ground'}`)),
        el('button', { class: 'x', title: 'Delete note', onclick: ev => { ev.stopPropagation(); pushUndo(); park.notes = park.notes.filter(m => m.id !== n.id); changed(); rebuildLabels(); renderNotes(); } }, '×')));
    }
  }

  // ---------------------------------------------------------------- render loop
  function resize() {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (canvas.width !== Math.floor(w * renderer.getPixelRatio()) || canvas.height !== Math.floor(h * renderer.getPixelRatio())) { renderer.setSize(w, h, false); camera.aspect = w / Math.max(1, h); camera.updateProjectionMatrix(); }
  }
  new ResizeObserver(() => { resize(); drawProfile(); }).observe(canvas);
  function loop(now) { requestAnimationFrame(loop); resize(); stepRide(now || performance.now()); controls.update(); renderer.render(scene, camera); placeLabels(); }

  // ---------------------------------------------------------------- boot
  async function boot() {
    try {
      await loadTerrain();
      park = await (await fetch('api/park')).json();
    } catch (e) { $('#loading').textContent = 'Could not load the park: ' + e.message; return; }
    rev = park.rev || 0;
    terrain.active = park.terrain === 'natural' ? 'natural' : 'dug'; $('#terrain').value = terrain.active;
    activeLine = (park.lines[0] || {}).id || 'L1';
    buildTerrain();
    renderPalette();
    relayout(null);
    sim = P.simulate(park, built, { groundAt });
    refreshOverlays(); renderIssues(); renderLines(); renderInspector(); updateHint(); updateUndoButtons();
    const t = park.saved_at ? new Date(park.saved_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : null;
    setSaveText(t ? `Saved · ${t}` : 'Loaded');
    // come back exactly as the owner left it (camera, solo, hidden lines, selection): survives Claude's reloads
    let restored = false;
    try {
      const sv = JSON.parse(localStorage.getItem('cpe-view') || 'null');
      if (sv && Date.now() - sv.at < 7 * 864e5 && sv.pos && sv.target) {
        if (sv.view === 'top') setView('top');
        camera.position.set(...sv.pos); controls.target.set(...sv.target); controls.update();
        solo = sv.solo && park.lines.some(l => l.id === sv.solo) ? sv.solo : null;
        hidden.clear(); for (const h of sv.hidden || []) if (park.lines.some(l => l.id === h)) hidden.add(h);
        applyVisibility();
        const ids = (sv.sel || []).filter(id => byId(id)); if (ids.length) select(ids);
        restored = true;
      }
    } catch (e) { /* storage blocked or stale: start from the overview */ }
    if (!restored) {
      camera.position.set(1300, 900, 1900); controls.target.set(1300, -20, 1020); controls.update();
      frameBox(selectionPoints(park.pieces.map(p => p.id)));
    }
    $('#loading').remove();
    let seen = false; try { seen = localStorage.getItem('cpe-help') === '1'; localStorage.setItem('cpe-help', '1'); } catch (e) { /* storage blocked */ }
    if (!seen) openModal('help');
    park.notes = park.notes || [];
    pollLoop();
    setInterval(() => reportView(false), 1000);
    setInterval(() => reportView(true), 10000);
    // test hook (used by the automated checks; harmless for users)
    window.__cpe = { get park() { return park; }, get sel() { return [...sel]; }, get sim() { return sim; }, select, selectLine, frameSelection, setView,
      setParam: (id, k, v) => setParam(byId(id), k, v, true), save, undo, scene, meshes, get innerMesh() { return innerMesh; }, get outerMesh() { return outerMesh; }, camera, controls,
      screenOf: id => { const b = built.get(id); const s = b.stations.length ? b.stations[Math.floor(b.stations.length / 2)] : { x: b.pose.x, y: b.pose.y, z: b.pose.z };
        const v = new THREE.Vector3(s.x, s.y + 0.3, s.z).project(camera); const r = canvas.getBoundingClientRect(); return { x: r.left + (v.x + 1) / 2 * r.width, y: r.top + (1 - v.y) / 2 * r.height }; } };
    loop();
  }
  boot();
})();
