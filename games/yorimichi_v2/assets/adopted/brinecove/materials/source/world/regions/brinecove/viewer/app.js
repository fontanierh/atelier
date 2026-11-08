import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

// Keep a hard failure visible instead of leaving the loading veil up.
window.addEventListener('error', (event) => {
  const el = document.querySelector('#loading-text');
  if (el) el.textContent = 'Viewer error: ' + (event.message || 'unknown error');
});
window.addEventListener('unhandledrejection', (event) => {
  const el = document.querySelector('#loading-text');
  if (el) el.textContent = 'Viewer error: ' + (event.reason?.message || event.reason || 'unknown error');
});

const MODULES = [
  { file: '01_terrain.glb', label: 'Terrain, coast & headlands', colour: '#6f8245' },
  { file: '02_harbor.glb', label: 'Quay, piers & shipyard', colour: '#9a8c72' },
  { file: '03_town_lower.glb', label: 'Rum Row & lower town', colour: '#c08a62' },
  { file: '04_market.glb', label: 'Market square & mast', colour: '#d6a357' },
  { file: '05_town_upper.glb', label: 'Upper terraces & stair', colour: '#7fa192' },
  { file: '06_landmarks.glb', label: 'Lighthouse, statue, waterfall', colour: '#e1d3b3' },
  { file: '07_ships.glb', label: 'Galleons & sloop', colour: '#4f7f79' },
  { file: '08_props.glb', label: 'Barrels, cranes & lanterns', colour: '#95704b' },
  { file: '09_vegetation.glb', label: 'Palms, jungle & vines', colour: '#4d6a36' },
  { file: '10_hero_assets.glb', label: 'TRELLIS hero assets', colour: '#caa15b' },
];
const VIEWS = {
  harbor: { label: 'Harbor mouth', pos: [-120, 30, 360], target: [0, 14, 10], fov: 52 },
  aerial: { label: 'Aerial', pos: [-300, 240, 560], target: [0, 18, 20], fov: 45 },
  market: { label: 'Market', pos: [0, 7.6, -118], target: [20, 9, -212], fov: 50 },
  upper: { label: 'Upper town', pos: [20, 54, -330], target: [-20, 2, -30], fov: 55 },
  rum: { label: 'Rum Row', pos: [-296, 7, -94], target: [-250, 10, -130], fov: 38 },
  lighthouse: { label: 'Lighthouse', pos: [-480, 108, 300], target: [-618, 70, 38], fov: 50 },
  shipyard: { label: 'Shipyard', pos: [290, 24, 200], target: [380, 14, -105], fov: 50 },
  waterfall: { label: 'Waterfall', pos: [360, 24, 70], target: [466, 26, -34], fov: 42 },
  cliff: { label: 'Cliff shacks', pos: [-430, 32, 170], target: [-512, 34, -10], fov: 48 },
  top: { label: 'Plan', pos: [0, 1780, 30], target: [0, 0, 20], fov: 52 },
  forest: { label: 'East canopy', pos: [470, 86, -140], target: [660, 52, -330], fov: 40 },
  cliffFace: { label: 'West cliff', pos: [-380, 12, 150], target: [-505, 30, 50], fov: 42 },
};
// Blender coordinates (x east, y north, z up); the scene is converted to
// three.js x east, y up, z south when these are projected.
const LABELS = [
  ['Harbor statue', [-120, -220, 30]],
  ['Market square', [0, 160, 13]],
  ['Rum Row', [-120, 122, 14]],
  ['Upper terrace', [0, 340, 30]],
  ['Watchtower', [-120, 470, 66]],
  ['Lighthouse', [-618, -38, 100]],
  ['Waterfall', [448, 30, 34]],
  ['Shipyard', [355, 92, 24]],
];
const REFS = [
  ['01-aerial-hero', 'Aerial hero: the defining layout'],
  ['02-harbor-approach', 'Harbor approach and statue'],
  ['03-market-square', 'Market square'],
  ['04-upper-terrace', 'Upper terrace looking down'],
  ['05-lighthouse-headland', 'Lighthouse headland'],
  ['06-shipyard', 'East shipyard and waterfall'],
  ['07-waterfall-bridge', 'Waterfall and rope bridge'],
  ['08-night-harbor', 'Harbor at blue hour'],
  ['09-rum-row', 'Rum Row taverns'],
  ['10-cliff-shacks', 'Cliffside shacks'],
  ['11-building-kit', 'Building kit'],
  ['12-prop-kit', 'Prop kit'],
  ['13-map', 'Painted plan'],
];
const BRIDGE_REFS = [
  ['02-harbor-approach', 'Harbor approach: buildable target'],
  ['03-market-square', 'Market square: buildable target'],
  ['04-upper-terrace', 'Upper terrace: buildable target'],
  ['09-rum-row', 'Rum Row: buildable target'],
];
const PROP_REFS = [
  ['pirate-queen-statue', 'Pirate queen statue'],
  ['galleon-figurehead', 'Galleon figurehead'],
  ['harbor-cannon', 'Harbor cannon'],
  ['ship-anchor', 'Ship anchor'],
  ['harbor-capstan', 'Harbor capstan'],
  ['ships-wheel', "Ship's wheel"],
];

const canvas = document.querySelector('#view');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight, false);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.12;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

const scene = new THREE.Scene();
scene.fog = new THREE.FogExp2(0xa7c5cb, 0.00035);
const camera = new THREE.PerspectiveCamera(48, innerWidth / innerHeight, 1, 6000);
camera.position.set(-120, 30, 360);
const controls = new OrbitControls(camera, canvas);
controls.target.set(0, 14, 10);
controls.enableDamping = true;
controls.dampingFactor = 0.06;
controls.maxPolarAngle = Math.PI * 0.495;
controls.minDistance = 18;
controls.maxDistance = 2500;
controls.screenSpacePanning = false;

// Sky dome: a readable painted gradient, with a soft sun disc.
const skyUniforms = {
  top: { value: new THREE.Color(0x3f7fa9) },
  horizon: { value: new THREE.Color(0xafd0da) },
  bottom: { value: new THREE.Color(0x8fb8c3) },
  sunColor: { value: new THREE.Color(0xffe3b0) },
  sunDir: { value: new THREE.Vector3(-0.45, 0.62, 0.35).normalize() },
};
const sky = new THREE.Mesh(
  new THREE.SphereGeometry(4200, 32, 18),
  new THREE.ShaderMaterial({
    side: THREE.BackSide, depthWrite: false, uniforms: skyUniforms,
    vertexShader: 'varying vec3 vDir; void main(){ vDir=normalize(position); gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }',
    fragmentShader: `
      float hash21(vec2 p){ p = fract(p*vec2(123.34,456.21)); p += dot(p,p+45.32); return fract(p.x*p.y); }
      float vnoise(vec2 p){ vec2 i=floor(p), f=fract(p); f=f*f*(3.0-2.0*f);
        return mix(mix(hash21(i),hash21(i+vec2(1,0)),f.x),mix(hash21(i+vec2(0,1)),hash21(i+vec2(1,1)),f.x),f.y); }
      float fbm(vec2 p){ float v=0.0, a=0.55; for(int i=0;i<4;i++){ v+=a*vnoise(p); p*=2.03; a*=0.48; } return v; }
      uniform vec3 top, horizon, bottom, sunColor, sunDir; varying vec3 vDir;
      void main(){
        float h = clamp(vDir.y*0.5+0.5,0.0,1.0);
        vec3 c = mix(bottom, horizon, smoothstep(0.28,0.46,h));
        c = mix(c, top, smoothstep(0.40,0.78,h));
        vec3 d = normalize(vDir);
        if (d.y > 0.01) {
          vec2 cp = d.xz / (d.y + 0.16);
          float cloud = smoothstep(0.44, 0.69, fbm(cp*1.28 + vec2(3.2,1.7)));
          cloud = max(cloud, smoothstep(0.56, 0.80, fbm(cp*2.7 + vec2(9.1,4.3)))*0.72);
          cloud *= smoothstep(0.02, 0.16, d.y);
          c = mix(c, vec3(0.98,0.95,0.88), cloud*0.82);
          float under = smoothstep(0.48, 0.72, fbm(cp*1.7 + vec2(8.0,2.0)));
          c = mix(c, vec3(0.72,0.78,0.80), under*cloud*0.18);
        }
        float s = max(dot(normalize(vDir), normalize(sunDir)), 0.0);
        c += sunColor * (pow(s, 900.0)*1.2 + pow(s, 12.0)*0.12);
        gl_FragColor = vec4(c,1.0);
      }`
  })
);
scene.add(sky);

// Water: a gentle vertex wave plus a warm specular glint. The shader uses no textures.
const waterUniforms = {
  uTime: { value: 0 },
  uMap: { value: new THREE.TextureLoader().load('textures/water.jpg') },
  uShallow: { value: new THREE.Color(0x3bb7c2) },
  uDeep: { value: new THREE.Color(0x248fa8) },
  uSunColor: { value: new THREE.Color(0xffd7a1) },
  uSunDir: { value: new THREE.Vector3(-0.45, 0.62, 0.35).normalize() },
  uNight: { value: 0 },
};
waterUniforms.uMap.value.colorSpace = THREE.SRGBColorSpace;
waterUniforms.uMap.value.wrapS = waterUniforms.uMap.value.wrapT = THREE.RepeatWrapping;
const water = new THREE.Mesh(
  new THREE.PlaneGeometry(5200, 5200, 180, 180),
  new THREE.ShaderMaterial({
    uniforms: waterUniforms, transparent: true, opacity: 0.96, depthWrite: true,
    vertexShader: `
      uniform float uTime; varying vec3 vWorld; varying float vWave;
      void main(){
        vec3 p = position;
        float w = sin(p.x*0.020 + uTime*0.75)*0.38 + sin(p.y*0.031 - uTime*0.55)*0.26
                + sin((p.x+p.y)*0.010 + uTime*0.32)*0.18;
        p.z += w; vWave = w;
        vec4 wp = modelMatrix * vec4(p,1.0); vWorld = wp.xyz;
        gl_Position = projectionMatrix * viewMatrix * wp;
      }`,
    fragmentShader: `
      uniform vec3 uShallow, uDeep, uSunColor, uSunDir; uniform float uTime, uNight; uniform sampler2D uMap;
      varying vec3 vWorld; varying float vWave;
      void main(){
        float depth = smoothstep(-100.0, 680.0, vWorld.z);
        vec2 uv1 = vWorld.xz * 0.018 + vec2(uTime*0.0009, uTime*0.0012);
        vec2 uv2 = vWorld.xz * 0.008 - vec2(uTime*0.0005, -uTime*0.0007);
        vec3 tex = texture2D(uMap, uv1).rgb*0.62 + texture2D(uMap, uv2).rgb*0.38;
        vec3 c = mix(uShallow, uDeep, depth*0.5 + 0.06) * (0.55 + 0.8*tex);
        c += vec3(0.07,0.13,0.11) * tex.g * 0.45;
        c += vec3(0.06,0.11,0.10) * sin(vWorld.x*0.014 + uTime*0.25 + vWorld.z*0.01);
        c *= 0.88 + vWave*0.035;
        vec3 n = normalize(vec3(sin(vWorld.x*0.07+uTime)*0.09, 1.0, cos(vWorld.z*0.06-uTime)*0.07));
        vec3 view = normalize(cameraPosition-vWorld);
        float spec = pow(max(dot(reflect(-normalize(uSunDir), n), view),0.0), 90.0);
        c += uSunColor * spec * (1.0-uNight) * 0.95;
        float fres = pow(1.0-max(dot(view,n),0.0), 3.0);
        c += vec3(0.16,0.24,0.28)*fres*0.35;
        gl_FragColor = vec4(c,0.96);
      }`
  })
);
water.rotation.x = -Math.PI / 2;
water.position.y = 0.0;
scene.add(water);

// Animated fall surface over the modelled rock chute.  The exported geometry
// supplies the cliff and the dark backing; this layer gives the fall moving
// ribbons, spray and a bright lip so it reads as water rather than a dam.
const fallUniforms = {
  uTime: { value: 0 },
  uMap: { value: new THREE.TextureLoader().load('textures/water.jpg') },
};
fallUniforms.uMap.value.colorSpace = THREE.SRGBColorSpace;
fallUniforms.uMap.value.wrapS = fallUniforms.uMap.value.wrapT = THREE.RepeatWrapping;
const fall = new THREE.Mesh(
  new THREE.PlaneGeometry(33, 49, 1, 36),
  new THREE.ShaderMaterial({
    uniforms: fallUniforms, transparent: true, depthWrite: false,
    side: THREE.DoubleSide, blending: THREE.NormalBlending,
    vertexShader: `
      uniform float uTime; varying vec2 vUv; varying vec3 vWorld;
      void main(){
        vUv = uv;
        vec3 p = position;
        p.x += sin(uv.y*22.0 + uTime*1.7) * 0.32 * smoothstep(0.0, 0.18, uv.y);
        vec4 wp = modelMatrix * vec4(p,1.0); vWorld = wp.xyz;
        gl_Position = projectionMatrix * viewMatrix * wp;
      }`,
    fragmentShader: `
      uniform float uTime; uniform sampler2D uMap;
      varying vec2 vUv; varying vec3 vWorld;
      void main(){
        vec2 uv = vec2(vUv.x*2.3, vUv.y*5.0 - uTime*0.52);
        vec3 a = texture2D(uMap, uv).rgb;
        vec3 b = texture2D(uMap, uv*1.7 + vec2(0.31, -uTime*0.31)).rgb;
        float streak = smoothstep(0.42, 0.72, a.g*0.55 + b.b*0.45);
        float edge = smoothstep(0.0, 0.08, vUv.x) * smoothstep(1.0, 0.92, vUv.x);
        float lip = smoothstep(0.93, 1.0, vUv.y);
        float plunge = smoothstep(0.16, 0.0, vUv.y);
        vec3 c = mix(vec3(0.45,0.72,0.76), vec3(0.94,0.98,0.96), streak*0.82);
        c = mix(c, vec3(0.99,0.99,0.96), lip*0.72);
        c = mix(c, vec3(0.85,0.94,0.92), plunge*0.55);
        float alpha = edge * (0.26 + 0.58*streak) * (1.0 - plunge*0.35);
        gl_FragColor = vec4(c, alpha);
      }`,
  })
);
fall.position.set(448, 28.0, -27.0);
scene.add(fall);

// Soft foam lines along the two bay walls.
function bayHalf(y) { return y >= 60 ? 2000 : Math.min(620, 430 + 0.28 * (60 - y)); }
const foamPoints = [];
for (let y = -620; y <= 64; y += 3) {
  const hw = bayHalf(y);
  for (const side of [-1, 1]) foamPoints.push(new THREE.Vector3(side * hw, 0.15, -y));
}
const foamGeo = new THREE.BufferGeometry().setFromPoints(foamPoints);
const foam = new THREE.Points(foamGeo, new THREE.PointsMaterial({
  color: 0xf0ead6, size: 2.6, transparent: true, opacity: 0.28, depthWrite: false,
  blending: THREE.AdditiveBlending, sizeAttenuation: true,
}));
scene.add(foam);

// Broken foam collars where the hulls and rocks meet the water.
const collarMat = new THREE.MeshBasicMaterial({
  color: 0xe8f0e7, transparent: true, opacity: 0.28, side: THREE.DoubleSide, depthWrite: false,
});
for (const [x, z, sx, sz] of [[-34, 84, 18, 34], [34, 142, 16, 30], [252, 72, 8, 12],
                               [-332, 322, 12, 12], [368, 300, 15, 15], [160, 412, 10, 10]]) {
  const collar = new THREE.Mesh(new THREE.RingGeometry(0.72, 1.0, 28), collarMat);
  collar.rotation.x = -Math.PI / 2;
  collar.scale.set(sx, sz, 1);
  collar.position.set(x, 0.07, z);
  scene.add(collar);
}

const hemi = new THREE.HemisphereLight(0xd2e6ee, 0x344e38, 1.25);
scene.add(hemi);
const sun = new THREE.DirectionalLight(0xffd2a0, 2.7);
sun.position.set(-520, 720, 430);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
sun.shadow.camera.left = -900; sun.shadow.camera.right = 900;
sun.shadow.camera.top = 900; sun.shadow.camera.bottom = -900;
sun.shadow.camera.near = 1; sun.shadow.camera.far = 2200;
sun.shadow.bias = -0.0004;
scene.add(sun);
scene.add(sun.target);
const fill = new THREE.DirectionalLight(0x8fb6ca, 0.42);
fill.position.set(500, 280, -600);
scene.add(fill);
const ambient = new THREE.AmbientLight(0x6f8f8b, 0.22);
scene.add(ambient);

// Warm lantern pools and glow sprites, hidden through the day.
const lanternPositions = [
  [-320, 8, -88], [-190, 8, -88], [-60, 8, -88], [70, 8, -88], [200, 8, -88], [330, 8, -88],
  [-200, 9, -155], [0, 10, -160], [200, 9, -155], [-120, 27, -338], [110, 27, -338],
  [-618, 100, 38], [355, 16, -92],
];
const lanternLights = lanternPositions.map(([x, y, z]) => {
  const light = new THREE.PointLight(0xffb45e, 0, 115, 2);
  light.position.set(x, y, z);
  light.castShadow = false;
  scene.add(light);
  return light;
});
function glowTexture() {
  const c = document.createElement('canvas'); c.width = c.height = 64;
  const g = c.getContext('2d');
  const gr = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  gr.addColorStop(0, 'rgba(255,224,166,1)'); gr.addColorStop(0.25, 'rgba(255,183,92,.8)');
  gr.addColorStop(1, 'rgba(255,150,50,0)');
  g.fillStyle = gr; g.fillRect(0, 0, 64, 64);
  return new THREE.CanvasTexture(c);
}
const glowMat = new THREE.PointsMaterial({
  map: glowTexture(), color: 0xffc36e, size: 7.5, transparent: true, opacity: 0,
  blending: THREE.AdditiveBlending, depthWrite: false, sizeAttenuation: true,
});
const glows = new THREE.Points(new THREE.BufferGeometry().setFromPoints(
  lanternPositions.map(([x, y, z]) => new THREE.Vector3(x, y, z))), glowMat);
scene.add(glows);

// Waterfall mist: a small animated particle cloud at the foot of the fall.
const mistCount = 180;
const mistPos = new Float32Array(mistCount * 3);
for (let i = 0; i < mistCount; i++) {
  mistPos[i * 3] = 448 + (Math.random() - 0.5) * 30;
  mistPos[i * 3 + 1] = 5 + Math.random() * 12;
  mistPos[i * 3 + 2] = -30 + (Math.random() - 0.5) * 18;
}
const mistGeo = new THREE.BufferGeometry();
mistGeo.setAttribute('position', new THREE.BufferAttribute(mistPos, 3));
const mistMat = new THREE.PointsMaterial({
  map: glowTexture(), color: 0xd9eef0, size: 5.5, transparent: true, opacity: 0.32,
  blending: THREE.AdditiveBlending, depthWrite: false,
});
const mist = new THREE.Points(mistGeo, mistMat);
scene.add(mist);

// A slow lighthouse beam gives the night view its landmark.
const beamGroup = new THREE.Group();
beamGroup.position.set(-618, 100, 38);
const beamMat = new THREE.MeshBasicMaterial({
  color: 0xffe6b0, transparent: true, opacity: 0.0, blending: THREE.AdditiveBlending,
  depthWrite: false, side: THREE.DoubleSide,
});
const beam = new THREE.Mesh(new THREE.ConeGeometry(16, 620, 20, 1, true), beamMat);
beam.rotation.z = -Math.PI / 2;
beam.position.x = 310;
beamGroup.add(beam);
scene.add(beamGroup);

const groups = {};
// Instanced trees, palms and shrubs; the density slider draws a prefix of each (the scatter order is random).
const foliage = [];
const flowing = [];
const emissive = [];
const loader = new GLTFLoader();
let totalTris = 0;

function tuneMaterial(material, flat = true) {
  if (!material) return;
  if (Array.isArray(material)) { material.forEach((m) => tuneMaterial(m, flat)); return; }
  const name = (material.name || '').toLowerCase();
  material.flatShading = flat;
  material.side = THREE.DoubleSide;
  material.needsUpdate = true;
  if (name.includes('waterfall') || name.includes('mist')) {
    // Falling water scrolls down its streak texture; the alpha-clipped ribbons stay opaque where drawn.
    if (name.includes('waterfall') && material.map) flowing.push(material.map);
    material.depthWrite = true;
    return;
  }
  if (name.includes('water')) {
    material.transparent = true;
    material.opacity = 0.7;
    material.depthWrite = false;
    material.roughness = 0.2;
  }
  if (name.includes('lantern') || name.includes('glass_warm')) {
    material.emissive = new THREE.Color(material.color || 0xffc46b);
    material.emissiveIntensity = 0.6;
    emissive.push(material);
  }
  if (name.includes('metal') || name.includes('gold')) {
    material.metalness = 0.55;
    material.roughness = 0.42;
  }
}

async function loadModules() {
  const text = document.querySelector('#loading-text');
  for (let i = 0; i < MODULES.length; i++) {
    const mod = MODULES[i];
    text.textContent = `Loading ${mod.label}…`;
    let gltf;
    try {
      gltf = await loader.loadAsync(`models/${mod.file}`);
    } catch (error) {
      console.warn(`Skipping unavailable module ${mod.file}`, error);
      continue;
    }
    const group = new THREE.Group();
    group.name = mod.file;
    group.userData.module = mod.file;
    gltf.scene.traverse((obj) => {
      if (!obj.isMesh) return;
      obj.castShadow = !mod.file.includes('vegetation') && !mod.file.includes('terrain');
      obj.receiveShadow = true;
      obj.frustumCulled = true;
      // Hero assets and the instanced foliage carry their own normals; everything else is flat-shaded.
      tuneMaterial(obj.material, !mod.file.includes('10_hero_assets') && !mod.file.includes('vegetation'));
      const copies = obj.isInstancedMesh ? obj.count : 1;
      if (obj.isInstancedMesh) { obj.userData.fullCount = obj.count; foliage.push(obj); }
      if (obj.geometry.index) totalTris += copies * obj.geometry.index.count / 3;
      else if (obj.geometry.attributes.position) totalTris += copies * obj.geometry.attributes.position.count / 3;
    });
    group.add(gltf.scene);
    scene.add(group);
    groups[mod.file] = group;
  }
  renderer.shadowMap.needsUpdate = true;
}

function buildUI() {
  const views = document.querySelector('#views');
  Object.entries(VIEWS).forEach(([key, view], i) => {
    const button = document.createElement('button');
    button.textContent = view.label;
    button.dataset.view = key;
    if (i === 0) button.classList.add('active');
    button.addEventListener('click', () => { stopTour(); flyTo(view); });
    views.appendChild(button);
  });
  const layers = document.querySelector('#layers');
  MODULES.forEach((mod) => {
    const label = document.createElement('label');
    label.className = 'layer';
    label.innerHTML = `<input type="checkbox" checked data-module="${mod.file}">
      <i class="swatch" style="background:${mod.colour}"></i><span>${mod.label}</span><span class="tris"></span>`;
    label.querySelector('input').addEventListener('change', (event) => {
      if (groups[mod.file]) groups[mod.file].visible = event.target.checked;
    });
    layers.appendChild(label);
  });
  fetch('build.json').then((r) => r.json()).then((data) => {
    for (const mod of MODULES) {
      const tris = data[mod.file.replace('.glb', '')]?.triangles;
      const el = document.querySelector(`[data-module="${mod.file}"]`)?.closest('.layer')?.querySelector('.tris');
      if (el && tris) el.textContent = `${(tris / 1000).toFixed(1)}k`;
    }
    const totals = data._totals?.triangles || Object.values(data).reduce((a, b) => a + (b.triangles || 0), 0);
    document.querySelector('#fact-tris').textContent = `${(totals / 1000).toFixed(0)}k triangles`;
  }).catch(() => {});

  const labels = document.querySelector('#labels-layer');
  LABELS.forEach(([name, pos], i) => {
    const el = document.createElement('div');
    el.className = 'label';
    el.innerHTML = `<span>${name}</span>`;
    el.addEventListener('click', () => {
      const target = new THREE.Vector3(pos[0], pos[2], -pos[1]);
      flyTo({ pos: [target.x + 80, target.y + 45, target.z + 110], target: [target.x, target.y, target.z], fov: 44 });
    });
    labels.appendChild(el);
    el.world = new THREE.Vector3(pos[0], pos[2], -pos[1]);
  });

  const gallery = document.querySelector('#gallery-grid');
  REFS.forEach(([slug, title]) => {
    const figure = document.createElement('figure');
    figure.innerHTML = `<img loading="lazy" src="refs/${slug}.png" alt="${title}"><figcaption>${title}</figcaption>`;
    figure.addEventListener('click', () => openLightbox(`refs/${slug}.png`, title));
    gallery.appendChild(figure);
  });
  const bridgeTitle = document.createElement('div');
  bridgeTitle.className = 'eyebrow';
  bridgeTitle.style.marginTop = '22px';
  bridgeTitle.textContent = 'Middle-ground targets · current build guided toward the paintings';
  gallery.parentElement.insertBefore(bridgeTitle, gallery.nextSibling);
  const bridgeGrid = document.createElement('div');
  bridgeGrid.className = 'gallery-grid';
  BRIDGE_REFS.forEach(([slug, title]) => {
    const figure = document.createElement('figure');
    figure.innerHTML = '<img loading="lazy" src="refs/bridge/' + slug + '.png" alt="' + title + '"><figcaption>' + title + '</figcaption>';
    figure.addEventListener('click', () => openLightbox('refs/bridge/' + slug + '.png', title));
    bridgeGrid.appendChild(figure);
  });
  gallery.parentElement.insertBefore(bridgeGrid, bridgeTitle.nextSibling);
  const renderTitle = document.createElement('div');
  renderTitle.className = 'eyebrow';
  renderTitle.style.marginTop = '22px';
  renderTitle.textContent = 'Blender model renders';
  gallery.parentElement.insertBefore(renderTitle, gallery.nextSibling);
  const modelGrid = document.createElement('div');
  modelGrid.className = 'gallery-grid';
  ['01-aerial-hero', '02-harbor-approach', '03-market-square', '04-upper-terrace',
   '05-lighthouse-headland', '06-shipyard', '07-waterfall-bridge', '08-night-harbor',
   '09-rum-row', '10-topdown', '11-cliff-shacks'].forEach((slug) => {
    const figure = document.createElement('figure');
    const title = slug.replace(/^\d+-/, '').replaceAll('-', ' ');
    figure.innerHTML = `<img loading="lazy" src="${slug}.png" alt="Blender render: ${title}"><figcaption>Blender · ${title}</figcaption>`;
    figure.addEventListener('click', () => openLightbox(`${slug}.png`, `Blender render · ${title}`));
    modelGrid.appendChild(figure);
  });
  gallery.parentElement.insertBefore(modelGrid, renderTitle.nextSibling);
  const propTitle = document.createElement('div');
  propTitle.className = 'eyebrow';
  propTitle.style.marginTop = '22px';
  propTitle.textContent = 'TRELLIS hero asset references';
  gallery.parentElement.insertBefore(propTitle, modelGrid.nextSibling);
  const propGrid = document.createElement('div');
  propGrid.className = 'gallery-grid';
  PROP_REFS.forEach(([slug, title]) => {
    const figure = document.createElement('figure');
    figure.innerHTML = `<img loading="lazy" src="refs/props/${slug}.png" alt="${title}"><figcaption>${title}</figcaption>`;
    figure.addEventListener('click', () => openLightbox(`refs/props/${slug}.png`, title));
    propGrid.appendChild(figure);
  });
  const processed = document.createElement('figure');
  processed.innerHTML = `<img loading="lazy" src="refs/trellis-processed.jpg" alt="Processed TRELLIS assets"><figcaption>Processed TRELLIS models · reference, front, three-quarter, side</figcaption>`;
  processed.addEventListener('click', () => openLightbox('refs/trellis-processed.jpg', 'Processed TRELLIS models'));
  propGrid.appendChild(processed);
  const surface = document.createElement('figure');
  surface.innerHTML = `<img loading="lazy" src="textures/contact-sheet.jpg" alt="Painted Brinecove surfaces"><figcaption>Sunburst surface set</figcaption>`;
  surface.addEventListener('click', () => openLightbox('textures/contact-sheet.jpg', 'Sunburst surface set'));
  propGrid.appendChild(surface);
  gallery.parentElement.insertBefore(propGrid, propTitle.nextSibling);
}

let tween = null;
let tour = null;
function flyTo(view, duration = 1450) {
  tween = {
    p0: camera.position.clone(), p1: new THREE.Vector3(...view.pos),
    t0: controls.target.clone(), t1: new THREE.Vector3(...view.target),
    start: performance.now(), duration,
  };
  document.querySelectorAll('#views button').forEach((b) => b.classList.toggle('active',
    b.textContent === view.label));
}
function smooth(t) { return t * t * (3 - 2 * t); }
function stopTour() {
  if (tour) clearInterval(tour);
  tour = null;
  document.querySelector('#tour').textContent = 'Guided tour';
}
function startTour() {
  const order = ['harbor', 'rum', 'market', 'upper', 'shipyard', 'waterfall', 'lighthouse', 'aerial', 'harbor'];
  let i = 0;
  flyTo(VIEWS[order[i]]);
  tour = setInterval(() => { i = (i + 1) % order.length; flyTo(VIEWS[order[i]]); }, 4600);
  document.querySelector('#tour').textContent = 'Stop tour';
}

function openLightbox(src, caption) {
  document.querySelector('#lightbox-img').src = src;
  document.querySelector('#lightbox-caption').textContent = caption;
  document.querySelector('#lightbox').hidden = false;
}
document.querySelector('#gallery-open').addEventListener('click', () => { document.querySelector('#gallery').hidden = false; });
document.querySelector('#mini-map').addEventListener('click', () => openLightbox('refs/13-map.png', 'Painted plan · Brinecove'));
document.querySelector('#gallery-close').addEventListener('click', () => { document.querySelector('#gallery').hidden = true; });
document.querySelector('#lightbox-close').addEventListener('click', () => { document.querySelector('#lightbox').hidden = true; });
document.querySelector('#gallery').addEventListener('click', (e) => { if (e.target.id === 'gallery') e.target.hidden = true; });
document.querySelector('#lightbox').addEventListener('click', (e) => { if (e.target.id === 'lightbox') e.target.hidden = true; });
document.querySelector('#tour').addEventListener('click', () => { tour ? stopTour() : startTour(); });
document.querySelector('#fullscreen').addEventListener('click', () => {
  if (document.fullscreenElement) document.exitFullscreen();
  else document.documentElement.requestFullscreen?.();
});
document.querySelector('#panel-close').addEventListener('click', () => document.querySelector('#panel').classList.remove('open'));
document.querySelector('#panel-open').addEventListener('click', () => document.querySelector('#panel').classList.add('open'));
document.querySelector('#density').addEventListener('input', (e) => {
  const f = Number(e.target.value);
  foliage.forEach((mesh) => { mesh.count = Math.max(1, Math.round(mesh.userData.fullCount * f)); });
  document.querySelector('#density-label').textContent = f >= 0.99 ? 'All trees' : `${Math.round(f * 100)}% of trees`;
});
document.querySelector('#spin').addEventListener('change', (e) => { controls.autoRotate = e.target.checked; controls.autoRotateSpeed = 0.45; });
document.addEventListener('keydown', (event) => {
  if (event.key === 'h' || event.key === 'H') document.body.classList.toggle('ui-hidden');
  if (event.key === 'f' || event.key === 'F') {
    if (document.fullscreenElement) document.exitFullscreen();
    else document.documentElement.requestFullscreen?.();
  }
});
document.querySelector('#labels').addEventListener('change', (e) => {
  document.querySelector('#labels-layer').style.display = e.target.checked ? 'block' : 'none';
});

function applyMood(v) {
  const day = { top: 0x3f7fb8, horizon: 0xc9e6ef, bottom: 0xa9d0d8, fog: 0xb0cfd6, sun: 0xffcf9c,
                sunI: 3.15, hemiI: 1.05, ambI: 0.18, exposure: 1.18, shallow: 0x3bbfc6, deep: 0x1d6f9d };
  const gold = { top: 0x4e7e9f, horizon: 0xf0c496, bottom: 0xb0a98c, fog: 0xc7b9a3, sun: 0xffab63,
                 sunI: 2.25, hemiI: 1.0, ambI: 0.18, exposure: 1.04, shallow: 0x4aa7a7, deep: 0x2a7c8f };
  const night = { top: 0x0a1c2b, horizon: 0x294a59, bottom: 0x0d2c33, fog: 0x16313a, sun: 0x8fb6e0,
                  sunI: 0.35, hemiI: 0.34, ambI: 0.12, exposure: 0.9, shallow: 0x1e5f6c, deep: 0x0b2637 };
  const lerpColor = (a, b, t) => new THREE.Color(a).lerp(new THREE.Color(b), t);
  const lerpNum = (a, b, t) => a + (b - a) * t;
  let from, to, t;
  if (v <= 1) { from = day; to = gold; t = v; } else { from = gold; to = night; t = v - 1; }
  skyUniforms.top.value.copy(lerpColor(from.top, to.top, t));
  skyUniforms.horizon.value.copy(lerpColor(from.horizon, to.horizon, t));
  skyUniforms.bottom.value.copy(lerpColor(from.bottom, to.bottom, t));
  scene.fog.color.copy(lerpColor(from.fog, to.fog, t));
  sun.color.copy(lerpColor(from.sun, to.sun, t));
  sun.intensity = lerpNum(from.sunI, to.sunI, t);
  hemi.intensity = lerpNum(from.hemiI, to.hemiI, t);
  ambient.intensity = lerpNum(from.ambI, to.ambI, t);
  renderer.toneMappingExposure = lerpNum(from.exposure, to.exposure, t);
  waterUniforms.uShallow.value.copy(lerpColor(from.shallow, to.shallow, t));
  waterUniforms.uDeep.value.copy(lerpColor(from.deep, to.deep, t));
  waterUniforms.uSunColor.value.copy(sun.color);
  waterUniforms.uNight.value = Math.max(0, (v - 0.9) / 1.1);
  const nightAmount = Math.max(0, (v - 0.75) / 1.25);
  emissive.forEach((m) => { m.emissiveIntensity = 0.5 + 5.5 * nightAmount; });
  lanternLights.forEach((l) => { l.intensity = 90 * nightAmount; });
  glowMat.opacity = 0.9 * nightAmount;
  mistMat.opacity = 0.25 + 0.12 * (1 - nightAmount);
  const label = v < 0.3 ? 'Day' : v < 0.75 ? 'Late afternoon' : v < 1.15 ? 'Golden hour' : v < 1.6 ? 'Dusk' : 'Night';
  document.querySelector('#mood-label').textContent = label;
}
document.querySelector('#mood').addEventListener('input', (e) => applyMood(Number(e.target.value)));

const clock = new THREE.Clock();
let fpsFrames = 0, fpsLast = performance.now();
function animate() {
  const dt = clock.getDelta();
  flowing.forEach((map) => { map.offset.y += dt * 0.55; });
  const t = clock.elapsedTime;
  waterUniforms.uTime.value = t;
  fallUniforms.uTime.value = t;
  beamGroup.rotation.y = t * 0.22;
  const moodValue = Number(document.querySelector('#mood').value);
  beamMat.opacity = 0.12 * Math.max(0, (moodValue - 1.15) / 0.85);
  sun.target.position.set(0, 0, -20);
  if (tween) {
    const k = Math.min(1, (performance.now() - tween.start) / tween.duration);
    const s = smooth(k);
    camera.position.lerpVectors(tween.p0, tween.p1, s);
    controls.target.lerpVectors(tween.t0, tween.t1, s);
    if (k >= 1) tween = null;
  }
  controls.update();
  // Waterfall mist drifts down and resets.
  const pos = mist.geometry.attributes.position;
  for (let i = 0; i < mistCount; i++) {
    pos.array[i * 3 + 1] -= dt * (2.0 + (i % 7) * 0.18);
    if (pos.array[i * 3 + 1] < 1.0) {
      pos.array[i * 3 + 1] = 13 + Math.random() * 12;
      pos.array[i * 3] = 448 + (Math.random() - 0.5) * 30;
      pos.array[i * 3 + 2] = -30 + (Math.random() - 0.5) * 18;
    }
  }
  pos.needsUpdate = true;
  // Labels track their world anchors.
  const labelEls = document.querySelectorAll('.label');
  labelEls.forEach((el) => {
    const v = el.world.clone().project(camera);
    const visible = v.z < 1 && v.z > -1 && el.parentElement.style.display !== 'none';
    el.style.opacity = visible ? '1' : '0';
    el.style.left = `${(v.x * 0.5 + 0.5) * innerWidth}px`;
    el.style.top = `${(-v.y * 0.5 + 0.5) * innerHeight}px`;
  });
  renderer.render(scene, camera);
  fpsFrames++;
  const now = performance.now();
  if (now - fpsLast > 700) {
    document.querySelector('#fps').textContent = `${Math.round(fpsFrames * 1000 / (now - fpsLast))} fps`;
    fpsFrames = 0; fpsLast = now;
  }
}

addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight, false);
});

buildUI();
applyMood(Number(document.querySelector('#mood').value));
loadModules().then(() => {
  const params = new URLSearchParams(location.search);
  const start = params.get('view');
  if (start && VIEWS[start]) {
    const v = VIEWS[start];
    camera.position.set(...v.pos);
    controls.target.set(...v.target);
    camera.fov = v.fov;
    camera.updateProjectionMatrix();
    document.querySelectorAll('#views button').forEach((b) => b.classList.toggle('active', b.textContent === v.label));
  }
  if (params.get('ui') === '0') document.body.classList.add('ui-hidden');
  const moodParam = params.get('mood');
  if (moodParam !== null) {
    const value = Math.max(0, Math.min(2, Number(moodParam)));
    document.querySelector('#mood').value = String(value);
    applyMood(value);
  }
  document.querySelector('#loading').classList.add('done');
  document.querySelector('#fact-modules').textContent = String(MODULES.length);
  document.querySelector('#fact-tris').textContent = `${(totalTris / 1000).toFixed(0)}k triangles`;
  renderer.setAnimationLoop(animate);
}).catch((error) => {
  document.querySelector('#loading-text').textContent = `Could not load the proposal: ${error.message}`;
  console.error(error);
});
