import { retargetMotion } from "./retarget.js";
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { GLTFExporter } from "three/addons/exporters/GLTFExporter.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { clone } from "three/addons/utils/SkeletonUtils.js";

const $ = (id) => document.getElementById(id);
let results = [],
  presets = [],
  authored = [],
  source = "generated",
  filter = "All",
  current = null;
let model, mixer, action, comparison, comparisonMixer, rigHelper;
let comparisonDuration = 1;
let rootBoneName;
let rest = new Map(),
  playing = true,
  looping = true,
  clockTime = 0,
  speed = 1,
  busy = false,
  engineReady = false;
let selectedClip,
  activeJob,
  sequence = [];
let displayScale = 1;
const cache = new Map();
const icons = { Attacks: "↗", Movement: "↝", Custom: "✳", Original: "◇" };
const renderer = new THREE.WebGLRenderer({
  antialias: true,
  alpha: true,
  preserveDrawingBuffer: true,
});
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFShadowMap;
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.4;
$("viewport").prepend(renderer.domElement);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(35, 1, 0.01, 100);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.minDistance = 1.6;
controls.maxDistance = 12;
controls.maxPolarAngle = Math.PI * 0.52;
function resetCamera() {
  camera.position.set(3.5, 1.8, 3.2);
  controls.target.set(0, 0.85, 0);
  controls.update();
}
resetCamera();
scene.add(new THREE.HemisphereLight(0xeef3df, 0x69795a, 2.1));
const key = new THREE.DirectionalLight(0xfff4de, 3.8);
key.position.set(3, 5, 4);
key.castShadow = true;
key.shadow.mapSize.set(2048, 2048);
key.shadow.camera.left = -4;
key.shadow.camera.right = 4;
key.shadow.camera.top = 4;
key.shadow.camera.bottom = -4;
key.shadow.bias = -0.001;
scene.add(key);
const rim = new THREE.DirectionalLight(0xc8e7a0, 2.8);
rim.position.set(-3, 3, -2);
scene.add(rim);
const ground = new THREE.Mesh(
  new THREE.PlaneGeometry(200, 200),
  new THREE.ShadowMaterial({ opacity: 0.3 }),
);
ground.rotation.x = -Math.PI / 2;
ground.receiveShadow = true;
ground.position.y = -0.01;
scene.add(ground);
const grid = new THREE.GridHelper(12, 48, 0x899774, 0x59684a);
grid.material.transparent = true;
grid.material.opacity = 0.17;
scene.add(grid);
const ring = new THREE.Mesh(
  new THREE.RingGeometry(1.0, 1.008, 96),
  new THREE.MeshBasicMaterial({
    color: 0x9aaa7b,
    transparent: true,
    opacity: 0.3,
    side: THREE.DoubleSide,
  }),
);
ring.rotation.x = -Math.PI / 2;
ring.position.y = 0.002;
scene.add(ring);
new ResizeObserver(() => {
  const el = $("viewport");
  renderer.setSize(el.clientWidth, el.clientHeight);
  camera.aspect = el.clientWidth / el.clientHeight;
  camera.updateProjectionMatrix();
}).observe($("viewport"));
function toast(message) {
  $("toast").textContent = message;
  $("toast").hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => ($("toast").hidden = true), 4500);
}
async function api(path, options) {
  const r = await fetch(path, options);
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || "Request failed");
  return data;
}
function escape(text) {
  return String(text).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
}

function generatedClip(motion, name) {
  return retargetMotion(motion, name, rest);
}

async function loadModel() {
  const gltf = await new GLTFLoader().loadAsync("/assets/fox.glb");
  model = gltf.scene;
  model.updateMatrixWorld(true);
  model.traverse((o) => {
    if (o.isBone) {
      const original = o.userData.name || o.name; // GLTFLoader sanitizes colons.
      const record = {
        name: o.name,
        localQ: o.quaternion.clone(),
        worldQ: o.getWorldQuaternion(new THREE.Quaternion()),
        worldPos: o.getWorldPosition(new THREE.Vector3()),
        parentInverse: o.parent.matrixWorld.clone().invert(),
      };
      rest.set(original, record);
      rest.set(o.name.replace("mixamorig", "mixamorig:"), record);
    }
    if (o.isMesh) {
      o.castShadow = true;
      o.receiveShadow = true;
      o.material.side = THREE.DoubleSide;
    }
  });
  const box = new THREE.Box3().setFromObject(model);
  rootBoneName = rest.get("mixamorig:Hips").name;
  const scale = 1.7 / box.getSize(new THREE.Vector3()).y;
  displayScale = scale;
  model.scale.multiplyScalar(scale);
  model.position.y -= box.min.y * scale;
  scene.add(model);
  mixer = new THREE.AnimationMixer(model);
  comparison = clone(model);
  comparison.traverse((o) => {
    if (o.isMesh) {
      o.material = o.material.clone();
      o.material.color.setHex(0xa4b89b);
      o.material.transparent = true;
      o.material.opacity = 0.46;
    }
  });
  comparison.visible = false;
  scene.add(comparison);
  comparisonMixer = new THREE.AnimationMixer(comparison);
  rigHelper = new THREE.SkeletonHelper(model);
  rigHelper.visible = false;
  rigHelper.material.depthTest = false;
  scene.add(rigHelper);
  authored = gltf.animations.map((clip) => ({
    id: clip.name,
    title: clip.name
      .replace("Fox_", "")
      .replace(/([a-z])([A-Z])/g, "$1 $2")
      .replaceAll("_", " "),
    category: /Attack|Kick/.test(clip.name)
      ? "Attacks"
      : /Idle|Hurt|Death/.test(clip.name)
        ? "Custom"
        : "Movement",
    authored: true,
    clip,
    frames: Math.round(clip.duration * 30) + 1,
    seed: "—",
  }));
  $("loading-view").hidden = true;
  await selectClip(results[0] || authored.find((x) => x.id === "Fox_Idle"));
  renderLibrary();
}
function makeCard(item) {
  const button = document.createElement("button");
  button.className = "clip-card" + (current?.id === item.id ? " selected" : "");
  button.dataset.id = item.id;
  button.innerHTML = `<span class="clip-icon">${icons[item.category] || "◇"}</span><span><strong>${escape(item.title)}</strong><small>${item.authored ? "AUTHORED" : `SEED ${item.seed}`} <span>·</span> ${((item.frames || 60) / 30).toFixed(1)}s</small></span><span class="arrow">↗</span>`;
  button.addEventListener("click", () =>
    selectClip(item).catch((e) => toast(e.message)),
  );
  const wrapper = document.createElement("div");
  wrapper.setAttribute("role", "listitem");
  wrapper.append(button);
  return wrapper;
}
function renderLibrary() {
  $("generated-count").textContent = results.length;
  $("result-count").textContent = `${results.length + authored.length} clips`;
  const list = $("clip-list");
  list.replaceChildren();
  const items = (source === "generated" ? results : authored).filter(
    (x) => filter === "All" || x.category === filter,
  );
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "empty-library";
    empty.innerHTML =
      source === "generated"
        ? "Your next move starts with a sentence.<br>Generate an experiment below or write your own prompt."
        : "No motions in this category.";
    list.append(empty);
  }
  for (const item of items) list.append(makeCard(item));
}
function renderRecipes() {
  $("recipes").replaceChildren();
  presets.forEach((p, i) => {
    const b = document.createElement("button");
    b.className = "recipe";
    b.dataset.slug = p.slug;
    b.innerHTML = `<span class="recipe-index">${String(i + 1).padStart(2, "0")}</span><span><strong>${escape(p.title)}</strong><small>${p.category} / seed ${p.seed}</small></span><span class="arrow">↗</span>`;
    b.onclick = () => {
      fillPrompt(p);
      const found = results.find(
        (r) => r.title === p.title && r.seed === p.seed,
      );
      if (found) selectClip(found).catch((e) => toast(e.message));
      else toast("Prompt loaded. Generate to try this motion.");
    };
    $("recipes").append(b);
  });
}
function fillPrompt(p) {
  $("prompt").value = p.prompt;
  $("seed").value = p.seed;
}
async function selectClip(item) {
  if (!model || !item) return;
  let clip = item.clip;
  if (!clip) {
    if (!cache.has(item.id)) cache.set(item.id, await api(item.motion));
    clip = generatedClip(cache.get(item.id), item.title);
  }
  mixer.stopAllAction();
  current = item;
  selectedClip = clip;
  action = mixer.clipAction(clip);
  action.play();
  clockTime = 0;
  setComparison();
  $("clip-title").textContent = item.title;
  $("clip-source").textContent = item.authored
    ? "ORIGINAL"
    : "UNIMATE / EXPERIMENT";
  $("stage-label").textContent = item.authored
    ? "Fox hunter / authored baseline"
    : "Fox hunter / in-place UniMate preview";
  $("frames").textContent = item.frames || 60;
  $("clip-seed").textContent = item.seed;
  $("duration").textContent = `${clip.duration.toFixed(2)}s`;
  $("travel").textContent = item.diagnostics
    ? `${(item.diagnostics.root_travel_m * displayScale).toFixed(2)} m`
    : "—";
  $("export").disabled = false;
  $("provenance").hidden = !item.provenance;
  if (item.provenance) $("provenance").href = item.provenance;
  $("review-note").textContent = item.authored
    ? "Authored animation from the current fox hunter rig. Use Compare to inspect the reference alongside a generated take."
    : `${item.prompt} · ${item.seconds}s inference. Experimental take: inspect foot contact and balance.`;
  if (!item.authored) {
    $("prompt").value = item.prompt;
    $("seed").value = item.seed;
    $("guidance").value = item.guidance;
    $("steps").value = item.steps;
    updateOutputs();
  }
  renderLibrary();
}
function setComparison() {
  if (!comparison) return;
  comparisonMixer.stopAllAction();
  if (current) {
    const reference =
      authored.find(
        (a) =>
          a.id ===
          (current.category === "Attacks" ? "Fox_AttackR_A" : "Fox_Run"),
      ) || authored[0];
    if (reference) {
      comparisonDuration = reference.clip.duration;
      comparisonMixer.clipAction(reference.clip).play();
    }
  }
  comparison.visible = $("compare").classList.contains("active");
  comparison.position.z = comparison.visible ? 1.35 : 0;
  model.position.z = comparison.visible ? -0.55 : 0;
  $("comparison-label").hidden = !comparison.visible;
}
function updateOutputs() {
  $("guidance-value").textContent = Number($("guidance").value).toFixed(1);
  $("steps-value").textContent = $("steps").value;
}
$("guidance").oninput = updateOutputs;
$("steps").oninput = updateOutputs;
$("random-seed").onclick = () => {
  $("seed").value = crypto.getRandomValues(new Uint32Array(1))[0] % 2147483648;
};
$("reset-camera").onclick = resetCamera;
$("compare").onclick = () => {
  $("compare").classList.toggle("active");
  setComparison();
};
$("skeleton").onclick = () => {
  $("skeleton").classList.toggle("active");
  if (rigHelper) rigHelper.visible = $("skeleton").classList.contains("active");
};
$("play").onclick = () => {
  playing = !playing;
  $("play").textContent = playing ? "Ⅱ" : "▶";
  $("play").setAttribute(
    "aria-label",
    playing ? "Pause animation" : "Play animation",
  );
};
$("loop").onclick = () => {
  looping = !looping;
  $("loop").classList.toggle("active", looping);
  $("loop").setAttribute("aria-pressed", String(looping));
};
$("speed").onchange = () => (speed = Number($("speed").value));
$("scrub").oninput = () => {
  if (action) clockTime = Number($("scrub").value) * selectedClip.duration;
};
document.querySelectorAll("[data-filter]").forEach(
  (b) =>
    (b.onclick = () => {
      filter = b.dataset.filter;
      document
        .querySelectorAll("[data-filter]")
        .forEach((x) => x.classList.toggle("selected", x === b));
      renderLibrary();
    }),
);
document.querySelectorAll("[data-source]").forEach(
  (b) =>
    (b.onclick = () => {
      source = b.dataset.source;
      document
        .querySelectorAll("[data-source]")
        .forEach((x) => x.classList.toggle("selected", x === b));
      renderLibrary();
    }),
);
document
  .querySelectorAll("[data-prompt]")
  .forEach(
    (b) =>
      (b.onclick = () =>
        fillPrompt(presets.find((p) => p.slug === b.dataset.prompt))),
  );
function setBusy(value) {
  busy = value;
  $("generate").disabled = busy || !engineReady;
  $("generate-presets").disabled = busy || !engineReady;
  $("generate").firstChild.textContent = busy
    ? "✳ Generating… "
    : "✳ Generate animation ";
}
async function generate(params) {
  setBusy(true);
  $("job-status").textContent = "Encoding prompt…";
  $("job-progress").hidden = false;
  $("job-progress").value = 0;
  try {
    const job = await api("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
    });
    activeJob = job.id;
    await pollJob();
  } catch (e) {
    setBusy(false);
    $("job-progress").hidden = true;
    $("job-status").textContent = e.message;
    sequence = [];
    toast(e.message);
  }
}
async function pollJob() {
  const job = await api(`/api/jobs/${activeJob}`);
  $("job-progress").value = job.progress;
  if (job.status === "complete") {
    results = [job, ...results.filter((r) => r.id !== job.id)];
    source = "generated";
    filter = "All";
    document
      .querySelectorAll("[data-source]")
      .forEach((b) =>
        b.classList.toggle("selected", b.dataset.source === source),
      );
    document
      .querySelectorAll("[data-filter]")
      .forEach((b) =>
        b.classList.toggle("selected", b.dataset.filter === filter),
      );
    await selectClip(job);
    $("job-status").textContent = `Ready in ${job.seconds}s · seed ${job.seed}`;
    activeJob = null;
    setBusy(false);
    $("job-progress").hidden = true;
    if (sequence.length) {
      const next = sequence.shift();
      await generate({ ...next, steps: 32, guidance: 3 });
    }
  } else if (job.status === "failed") {
    throw new Error(job.message);
  } else {
    $("job-status").textContent = `Sampling motion · ${job.progress}%`;
    setTimeout(
      () =>
        pollJob().catch((e) => {
          setBusy(false);
          sequence = [];
          toast(e.message);
          $("job-status").textContent = e.message;
        }),
      1000,
    );
  }
}
$("prompt-form").onsubmit = (e) => {
  e.preventDefault();
  sequence = [];
  generate({
    prompt: $("prompt").value,
    seed: Number($("seed").value),
    guidance: Number($("guidance").value),
    steps: Number($("steps").value),
  });
};
$("generate-presets").onclick = () => {
  sequence = presets.filter(
    (p) => !results.some((r) => r.title === p.title && r.seed === p.seed),
  );
  if (!sequence.length)
    return toast("All eight experiments are already in the library.");
  const first = sequence.shift();
  generate({ ...first, steps: 32, guidance: 3 });
};
async function download(blob, name, file, id) {
  const r = await fetch(`/api/save/${id}/${file}`, {
    method: "POST",
    headers: { "Content-Type": blob.type },
    body: blob,
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || "Unable to save artifact");
  const a = document.createElement("a");
  a.href = data.url;
  a.download = name;
  a.click();
}
$("snapshot").onclick = () => {
  const item = current;
  if (!item) return;
  const canvas = document.createElement("canvas");
  canvas.width = renderer.domElement.width;
  canvas.height = renderer.domElement.height;
  const context = canvas.getContext("2d");
  context.fillStyle = "#252d21";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(renderer.domElement, 0, 0);
  canvas.toBlob((blob) =>
    download(blob, `fox-${item.title}.png`, "pose.png", item.id).catch(
      (e) => toast(e.message),
    ),
  );
};
$("export").onclick = async () => {
  try {
    const item = current;
    const clip = selectedClip;
    const copy = clone(model);
    copy.position.set(0, model.position.y, 0); // Exclude comparison layout.
    const target = new THREE.AnimationMixer(copy);
    target.clipAction(clip).play();
    target.setTime(0);
    copy.updateMatrixWorld(true);
    const data = await new GLTFExporter().parseAsync(copy, {
      binary: true,
      animations: [clip],
      onlyVisible: true,
    });
    await download(
      new Blob([data], { type: "model/gltf-binary" }),
      `fox-${item.title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.glb`,
      "fox.glb",
      item.id,
    );
    toast("Animated fox GLB exported and saved locally.");
  } catch (e) {
    toast(`Export failed: ${e.message}`);
  }
};
let lastTime = performance.now();
// Keep locomotion in the review frame. The clip and exported GLB retain travel.
function centerPreview(character, side) {
  character.position.x = 0;
  character.position.z = side;
  character.updateMatrixWorld(true);
  const hips = character.getObjectByName(rootBoneName);
  const point = hips.getWorldPosition(new THREE.Vector3());
  const origin = rest.get("mixamorig:Hips").worldPos;
  character.position.x -= point.x - origin.x * displayScale;
  character.position.z -= point.z - (origin.z * displayScale + side);
}
renderer.setAnimationLoop((now) => {
  const dt = Math.min((now - lastTime) / 1000, 0.05);
  lastTime = now;
  if (action) {
    if (playing) clockTime += dt * speed;
    const duration = selectedClip.duration;
    if (clockTime > duration)
      clockTime = looping ? clockTime % duration : duration;
    action.setLoop(THREE.LoopOnce, 1);
    action.clampWhenFinished = true;
    action.paused = false;
    mixer.setTime(clockTime);
    centerPreview(model, comparison.visible ? -0.55 : 0);
    if (comparison.visible)
      comparisonMixer.setTime(clockTime % Math.max(comparisonDuration, 0.1));
    if (comparison.visible) centerPreview(comparison, 1.35);
    $("scrub").value = duration ? clockTime / duration : 0;
    $("time").textContent = `${clockTime.toFixed(2)}s`;
  }
  controls.update();
  renderer.render(scene, camera);
});
async function status() {
  try {
    const s = await api("/api/status");
    engineReady = s.status === "ready";
    $("model-status").classList.toggle("error", s.status === "error");
    $("model-status").innerHTML =
      `<i></i>${s.status === "ready" ? `UniMate ready · ${escape(s.device.toUpperCase())}` : s.status === "error" ? "Model unavailable" : "Loading model"}`;
    if (!busy) {
      setBusy(false);
      $("job-status").textContent =
        s.status === "ready" ? "Ready for your next move." : s.message;
    }
    // Recover an in-flight local job after a page reload.
    if (s.active && !activeJob) {
      activeJob = s.active;
      setBusy(true);
      pollJob().catch((e) => toast(e.message));
    }
  } catch (e) {
    $("model-status").innerHTML = "<i></i> Server disconnected";
    engineReady = false;
    setBusy(busy);
  }
}
try {
  const library = await api("/api/library");
  results = library.results;
  presets = library.presets;
  renderRecipes();
  renderLibrary();
  await loadModel();
} catch (e) {
  $("loading-view").textContent = `Unable to load viewer: ${e.message}`;
  toast(e.message);
}
await status();
setInterval(status, 5000);
