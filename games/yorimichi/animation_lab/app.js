import { retargetMotion } from "../../../platform/web/motion/retarget.js";
import { closeLoop } from "../../../platform/web/motion/loop.js";
import * as THREE from "three";
import { GIFEncoder, quantize, applyPalette } from "gifenc";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { GLTFExporter } from "three/addons/exporters/GLTFExporter.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { clone } from "three/addons/utils/SkeletonUtils.js";

const $ = (id) => document.getElementById(id);
let generator = "UniMate";
let results = [],
  presets = [],
  authored = [],
  mode = "compare",
  reference = null,
  originalMetadata = [],
  filter = "All",
  current = null;
let model,
  mixer,
  action,
  comparison,
  comparisonMixer,
  comparisonAction,
  rigHelper,
  comparisonRigHelper;
let comparisonDuration = 1;
let rootBoneName;
let selectionRequest = 0;
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
let exportingPreview = false;
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
  camera.position.set(
    ...(mode === "compare" ? [4.4, 2.1, 4] : [3.5, 1.8, 3.2]),
  );
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
  return retargetMotion(THREE, motion, name, rest);
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
  comparison.visible = false;
  scene.add(comparison);
  comparisonMixer = new THREE.AnimationMixer(comparison);
  rigHelper = new THREE.SkeletonHelper(model);
  rigHelper.visible = false;
  rigHelper.material.depthTest = false;
  scene.add(rigHelper);
  comparisonRigHelper = new THREE.SkeletonHelper(comparison);
  comparisonRigHelper.visible = false;
  comparisonRigHelper.material.depthTest = false;
  scene.add(comparisonRigHelper);
  authored = gltf.animations.map((loaded) => {
    const meta = originalMetadata.find((m) => m.id === loaded.name);
    const clip =
      meta?.kind === "loop" ? closeLoop(THREE, loaded, meta.seconds) : loaded;
    return {
      id: clip.name,
      title:
        clip.name === "Fox_Run"
          ? "Forward sprint"
          : clip.name
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
      prompt: meta?.prompt,
      travel_speed: meta?.travel_speed_units_per_s,
    };
  });
  $("loading-view").hidden = true;
  await selectOriginal(authored.find((x) => x.id === "Fox_Run") || authored[0]);
  updateMode();
  renderLibrary();
}
function makeCard(item) {
  const button = document.createElement("button");
  button.className =
    "clip-card" +
    ((mode === "compare" ? reference?.id : current?.id) === item.id
      ? " selected"
      : "");
  button.dataset.id = item.id;
  const copies = results.filter((r) => r.reference_clip === item.id).length;
  const subtitle = item.authored
    ? `ORIGINAL · ${copies} counterpart${copies === 1 ? "" : "s"}`
    : `${(item.generator || generator).toUpperCase()} ONLY · SEED ${item.seed}`;
  button.innerHTML = `<span class="clip-icon">${icons[item.category] || "◇"}</span><span><strong>${escape(item.title)}</strong><small>${subtitle}</small><small>${(item.clip?.duration || (item.frames - 1) / (item.fps || 30)).toFixed(2)}s${!item.authored && !item.conditioning_version ? " · earlier conditioning" : ""}</small></span><span class="arrow">↗</span>`;
  button.addEventListener("click", () =>
    (item.authored ? selectOriginal(item) : selectClip(item)).catch((e) =>
      toast(e.message),
    ),
  );
  const wrapper = document.createElement("div");
  wrapper.setAttribute("role", "listitem");
  wrapper.append(button);
  return wrapper;
}
function renderLibrary() {
  const standalone = results.filter((r) => !r.reference_clip);
  $("result-count").textContent =
    mode === "compare"
      ? `${authored.length} originals`
      : `${standalone.length} motions`;
  const list = $("clip-list");
  list.replaceChildren();
  const items = (mode === "compare" ? authored : standalone).filter(
    (x) => filter === "All" || x.category === filter,
  );
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "empty-library";
    empty.innerHTML =
      mode === "create"
        ? "Your next move starts with a sentence.<br>Generate an experiment below or write your own prompt."
        : "No motions in this category.";
    list.append(empty);
  }
  for (const item of items) list.append(makeCard(item));
  const selected = list.querySelector(".selected");
  if (selected)
    list.scrollTop = Math.max(
      0,
      selected.offsetTop -
        list.offsetTop -
        list.clientHeight / 2 +
        selected.offsetHeight / 2,
    );
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
        (r) => !r.reference_clip && r.title === p.title && r.seed === p.seed,
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
function updateMode() {
  document.querySelectorAll("[data-mode]").forEach((b) => {
    const selected = b.dataset.mode === mode;
    b.classList.toggle("selected", selected);
    b.setAttribute("aria-pressed", String(selected));
  });
  $("library-title").textContent =
    mode === "compare" ? "Original animations" : `${generator}-only motions`;
  $("library-help").textContent =
    mode === "compare"
      ? "Pick an original. Its counterparts stay grouped with it."
      : "Independent generations, with no original attached.";
  $("comparison-tools").hidden = mode !== "compare";
  $("recipe-section").hidden = mode !== "create";
  $("prompt-suggestions").hidden = mode !== "create";
  $("motion-name-field").hidden = mode !== "create";
  $("prompt-title").textContent =
    mode === "compare" ? "Generate a counterpart" : "Create a new animation";
  $("prompt-help").textContent =
    mode === "create"
      ? "Describe a new motion. It will be saved independently in this library."
      : generator === "UniMate" && reference?.id === "Fox_Run"
        ? "Reference: Forward sprint. Keep its gait, or uncheck the option for prompt-only generation."
        : `Reference: ${reference?.title || "—"}. Generate a prompt-only counterpart for side-by-side review.`;
  $("guided-field").hidden = generator !== "UniMate" || mode !== "compare" || reference?.id !== "Fox_Run";
  setBusy(busy);
  renderLibrary();
}
async function selectOriginal(item, preferred) {
  reference = item;
  const variants = results.filter((r) => r.reference_clip === item.id);
  $("variant").replaceChildren();
  for (const take of variants) {
    const option = document.createElement("option");
    option.value = take.id;
    const title = take.title.replace(/(?: ·| \/) seed \d+$/, "");
    option.textContent = `${take.guided ? "HYBRID" : "PROMPT ONLY"} · ${title} · seed ${take.seed}${!take.conditioning_version ? " · earlier conditioning" : ""}`;
    $("variant").append(option);
  }
  if (!variants.length) {
    const option = document.createElement("option");
    option.textContent = "No counterpart yet";
    option.value = "";
    $("variant").append(option);
  }
  $("variant").disabled = !variants.length;
  const take = variants.find((r) => r.id === preferred) || variants[0];
  if (take) $("variant").value = take.id;
  const selected = await selectClip(take || item);
  if (!selected || reference !== item) return;
  if (!take) {
    $("prompt").value = item.prompt;
    $("guidance").value = 2;
    $("steps").value = generator === "Kimodo" ? 100 : 32;
    updateOutputs();
  }
  $("guided-sprint").checked = generator === "UniMate" && (take ? !!take.guided : item.id === "Fox_Run");
  updateMode();
}
$("variant").onchange = () => {
  const take = results.find((r) => r.id === $("variant").value);
  $("guided-sprint").checked = !!take.guided;
  selectClip(take).catch((e) => toast(e.message));
  setBusy(busy);
};
$("comparison-view").onchange = () => {
  setComparison();
  resetCamera();
};
$("guided-sprint").onchange = () => setBusy(busy);
document.querySelectorAll("[data-mode]").forEach(
  (b) =>
    (b.onclick = async () => {
      const previousMode = mode;
      mode = b.dataset.mode;
      if (mode === "compare" && mode !== previousMode)
        $("comparison-view").value = "both";
      filter = "All";
      document
        .querySelectorAll("[data-filter]")
        .forEach((x) =>
          x.classList.toggle("selected", x.dataset.filter === "All"),
        );
      if (mode === "compare")
        await selectOriginal(
          reference || authored.find((a) => a.id === "Fox_Run"),
        );
      else {
        reference = null;
        const standalone = results.find((r) => !r.reference_clip);
        if (standalone) await selectClip(standalone);
        else {
          current = null;
          selectionRequest++;
          action = null;
          model.visible = false;
          comparison.visible = false;
          $("clip-title").textContent = "Your next motion";
          $("clip-source").textContent = `${generator.toUpperCase()} ONLY`;
          $("export").disabled = true;
        }
        updateMode();
        setComparison();
      }
      resetCamera();
    }),
);
async function selectClip(item) {
  if (!model || !item) return false;
  const request = ++selectionRequest;
  let clip = item.clip;
  if (!clip) {
    if (!cache.has(item.id)) cache.set(item.id, await api(item.motion));
    clip = generatedClip(cache.get(item.id), item.title);
  }
  if (request !== selectionRequest) return false;
  mixer.stopAllAction();
  current = item;
  selectedClip = clip;
  action = mixer.clipAction(clip);
  action.play();
  clockTime = 0;
  setComparison();
  $("clip-title").textContent =
    mode === "compare" ? reference.title : item.title;
  $("clip-source").textContent =
    mode === "compare" ? `ORIGINAL ↔ ${generator.toUpperCase()}` : `${generator.toUpperCase()} ONLY / NEW MOTION`;
  $("stage-label").textContent = item.authored
    ? "Fox hunter / authored baseline"
    : `Fox hunter / in-place ${generator} preview`;
  $("frames").textContent = item.frames || 60;
  $("clip-seed").textContent = item.seed;
  $("duration").textContent = `${clip.duration.toFixed(2)}s`;
  $("travel-label").textContent = item.travel_speed
    ? "IN-PLACE SPEED"
    : "ROOT TRAVEL";
  $("travel").textContent = item.travel_speed
    ? `${(item.travel_speed * displayScale).toFixed(2)} m/s`
    : item.diagnostics
      ? `${(item.diagnostics.root_travel_m * displayScale).toFixed(2)} m`
      : "—";
  $("provenance").hidden = !item.provenance;
  if (item.provenance) $("provenance").href = item.provenance;
  const variation = item.guided?.actual_max_joint_change_degrees;
  const kind = item.guided
    ? `HYBRID: authored gait + UniMate arm variation${variation ? ` (up to ${variation.toFixed(1)}°)` : ""}. `
    : "PROMPT ONLY: generated motion. ";
  $("review-note").textContent = item.authored
    ? `The original is ready. Generate its first ${generator} counterpart.`
    : `${kind}${item.prompt} · ${item.seconds}s inference.${generator === "UniMate" && !item.conditioning_version ? " Earlier conditioning; generate again with the corrected vocabulary." : ""}`;
  if (!item.authored) {
    $("prompt").value = item.prompt;
    $("seed").value = item.seed;
    $("guidance").value = item.guidance;
    $("steps").value = item.steps;
    if (generator === "Kimodo") $("motion-duration").value = item.frames / item.fps;
    updateOutputs();
  }
  renderLibrary();
  return true;
}
function setComparison() {
  if (!comparison) return;
  comparisonMixer.stopAllAction();
  if (mode === "compare" && reference) {
    comparisonDuration = reference.clip.duration;
    comparisonAction = comparisonMixer.clipAction(reference.clip);
    comparisonAction.setLoop(THREE.LoopOnce, 1);
    comparisonAction.clampWhenFinished = true;
    comparisonAction.play();
  }
  const view = $("comparison-view").value;
  $("viewport").dataset.view = view;
  comparison.visible = mode === "compare" && view !== "generated";
  model.visible =
    !!current &&
    !current.authored &&
    (mode === "create" || view !== "original");
  $("comparison-label").hidden = mode !== "compare";
  $("missing-counterpart").hidden =
    mode !== "compare" || !current?.authored || view === "original";
  $("original-label").textContent = reference?.title || "—";
  $("generated-label").textContent = current?.authored
    ? "Not generated"
    : current?.title || "—";
  $("generated-kind").textContent = current?.authored
    ? "NO COUNTERPART"
    : current?.guided
      ? "HYBRID · AUTHORED GAIT + UNIMATE ARMS"
      : `${generator.toUpperCase()} · PROMPT ONLY`;
  $("stage-label-wrap").hidden = mode === "compare";
  $("export").disabled = !current || (current.authored && view !== "original");
  $("export").textContent =
    mode === "compare" && view === "original"
      ? "↓ Export original"
      : `↓ Export ${generator}`;
  updateSkeletons();
}
function updateSkeletons() {
  const show = $("skeleton").classList.contains("active");
  if (rigHelper) rigHelper.visible = show && model.visible;
  if (comparisonRigHelper)
    comparisonRigHelper.visible = show && comparison.visible;
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
$("skeleton").onclick = () => {
  $("skeleton").classList.toggle("active");
  updateSkeletons();
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
  $("generate").textContent = busy
    ? "✳ Generating…"
    : mode === "create"
      ? "✳ Generate new motion ↗"
      : reference?.id === "Fox_Run" && $("guided-sprint").checked
        ? "✳ Generate guided sprint ↗"
        : "✳ Generate counterpart ↗";
  $("generation-duration").textContent =
    mode === "compare" &&
    reference?.id === "Fox_Run" &&
    $("guided-sprint").checked
      ? "0.6-second loop"
      : generator === "Kimodo" ? `${$("motion-duration").value} seconds` : "2 seconds";
}
async function generate(params) {
  if (generator === "Kimodo") params.duration = Number($("motion-duration").value);
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
    filter = "All";
    document.querySelectorAll("[data-filter]").forEach((b) =>
      b.classList.toggle("selected", b.dataset.filter === "All"),
    );
    mode = job.reference_clip ? "compare" : "create";
    if (job.reference_clip)
      await selectOriginal(
        authored.find((a) => a.id === job.reference_clip),
        job.id,
      );
    else await selectClip(job);
    updateMode();
    resetCamera();
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
    title:
      mode === "compare"
        ? `${reference.title} · seed ${$("seed").value}`
        : $("motion-name").value.trim() ||
          $("prompt").value.trim().slice(0, 60),
    category: mode === "compare" ? reference.category : "Custom",
    reference_clip: mode === "compare" ? reference.id : null,
    guided_sprint:
      generator === "UniMate" &&
      mode === "compare" &&
      reference.id === "Fox_Run" &&
      $("guided-sprint").checked,
  });
};
$("generate-presets").onclick = () => {
  sequence = presets.filter(
    (p) =>
      !results.some(
        (r) => !r.reference_clip && r.title === p.title && r.seed === p.seed,
      ),
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
function capturePose(item, width = renderer.domElement.width) {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = Math.round(
    width * renderer.domElement.height / renderer.domElement.width,
  );
  const context = canvas.getContext("2d");
  context.fillStyle = "#252d21";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(renderer.domElement, 0, 0, canvas.width, canvas.height);
  // Keep exported comparisons as legible as the viewer: preserve source labels.
  const ratio = canvas.width / renderer.domElement.clientWidth;
  context.textAlign = "center";
  context.font = `${11 * ratio}px sans-serif`;
  const drawLabel = (text, x, color) => {
    context.fillStyle = color;
    context.fillText(text, canvas.width * x, 28 * ratio);
  };
  const view = $("comparison-view").value;
  if (mode === "compare") {
    if (view !== "generated")
      drawLabel("ORIGINAL · AUTHORED", view === "both" ? 0.25 : 0.5, "#eff0e5");
    if (view !== "original")
      drawLabel(
        item.authored
          ? "NO COUNTERPART"
          : item.guided
            ? "HYBRID · ORIGINAL GAIT + UNIMATE ARMS"
            : `${generator.toUpperCase()} · PROMPT ONLY`,
        view === "both" ? 0.75 : 0.5,
        "#d2e59c",
      );
  } else drawLabel(generator.toUpperCase() + " ONLY · " + item.title, 0.5, "#d2e59c");
  return canvas;
}
$("snapshot").onclick = () => {
  const item = current;
  if (!item) return;
  capturePose(item).toBlob((blob) =>
    download(blob, `fox-${item.title}.png`, "pose.png", item.id).catch((e) =>
      toast(e.message),
    ),
  );
};
$("export").onclick = async () => {
  try {
    const original =
      mode === "compare" && $("comparison-view").value === "original";
    const item = original ? reference : current;
    const clip = original ? reference.clip : selectedClip;
    const copy = clone(original ? comparison : model);
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
  const right = new THREE.Vector3(
    camera.position.z - controls.target.z,
    0,
    -(camera.position.x - controls.target.x),
  )
    .normalize()
    .multiplyScalar(side);
  character.position.x = right.x;
  character.position.z = right.z;
  character.updateMatrixWorld(true);
  const hips = character.getObjectByName(rootBoneName);
  const point = hips.getWorldPosition(new THREE.Vector3());
  const origin = rest.get("mixamorig:Hips").worldPos;
  character.position.x -= point.x - (origin.x * displayScale + right.x);
  character.position.z -= point.z - (origin.z * displayScale + right.z);
}
function renderPose() {
  if (action) {
    const duration = selectedClip.duration;
    if (clockTime > duration)
      clockTime = looping ? clockTime % duration : duration;
    action.setLoop(THREE.LoopOnce, 1);
    action.clampWhenFinished = true;
    action.paused = false;
    mixer.setTime(clockTime);
    const both = mode === "compare" && $("comparison-view").value === "both";
    centerPreview(model, both ? 0.78 : 0);
    if (comparison.visible) {
      comparisonAction.paused = false;
      comparisonMixer.setTime(
        $("phase-sync").checked
          ? (clockTime / Math.max(duration, 0.1)) * comparisonDuration
          : clockTime % Math.max(comparisonDuration, 0.1),
      );
    }
    if (comparison.visible) centerPreview(comparison, both ? -0.78 : 0);
    $("scrub").value = duration ? clockTime / duration : 0;
    $("time").textContent = `${clockTime.toFixed(2)}s`;
  }
  controls.update();
  renderer.render(scene, camera);
}
renderer.setAnimationLoop((now) => {
  const dt = Math.min((now - lastTime) / 1000, 0.05);
  lastTime = now;
  if (exportingPreview) return;
  if (action && playing) clockTime += dt * speed;
  renderPose();
});
// Sample the selected clip deterministically at its native rate, independent of
// playback speed. GIF time is quantized to centiseconds, with accumulated rounding.
$("preview-gif").onclick = async () => {
  if (!current || !selectedClip || exportingPreview) return;
  const item = current;
  const originalTime = clockTime;
  const fps = item.fps || 30;
  const count = Math.round(selectedClip.duration * fps) + 1;
  const button = $("preview-gif");
  exportingPreview = true;
  document.body.inert = true;
  button.disabled = true;
  button.textContent = "Encoding…";
  try {
    const frames = [];
    for (let f = 0; f < count; f++) {
      clockTime = Math.min(f / fps, selectedClip.duration);
      renderPose();
      const canvas = capturePose(item, 640);
      frames.push(
        canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height),
      );
      // Let the browser paint progress while preserving the captured clip time.
      if (f % 10 === 0) await new Promise(requestAnimationFrame);
    }
    // One palette across evenly spaced frames avoids color flicker.
    const samples = frames.filter((_, i) => i % 5 === 0);
    const rgba = new Uint8Array(samples.length * samples[0].data.length);
    samples.forEach((frame, i) => rgba.set(frame.data, i * frame.data.length));
    const palette = quantize(rgba, 256);
    const gif = GIFEncoder();
    frames.forEach((frame, i) =>
      gif.writeFrame(
        applyPalette(frame.data, palette), frame.width, frame.height,
        {
          ...(i === 0 ? { palette } : {}),
          delay: 10 * (Math.round((i + 1) * 100 / fps) - Math.round(i * 100 / fps)),
          repeat: 0,
        },
      ),
    );
    gif.finish();
    await download(
      new Blob([gif.bytes()], { type: "image/gif" }),
      `fox-${item.title}.gif`, "preview.gif", item.id,
    );
    toast("GIF saved locally at the clip's original speed.");
  } catch (e) {
    toast(`GIF export failed: ${e.message}`);
  } finally {
    clockTime = originalTime;
    exportingPreview = false;
    document.body.inert = false;
    button.disabled = false;
    button.textContent = "↓ Preview GIF";
    renderPose();
  }
};
async function status() {
  try {
    const s = await api("/api/status");
    engineReady = s.status === "ready";
    $("model-status").classList.toggle("error", s.status === "error");
    $("model-status").innerHTML =
      `<i></i>${s.status === "ready" ? `${generator} ready · ${escape(s.device.toUpperCase())}` : s.status === "error" ? "Model unavailable" : "Loading model"}`;
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
  originalMetadata = library.originals;
  generator = library.generator || "UniMate";
  $("model-link").textContent = `Powered by ${generator} ↗`;
  $("model-link").href = generator === "Kimodo" ? "https://research.nvidia.com/labs/sil/projects/kimodo/" : "https://github.com/Friedrich-M/UniMate";
  $("duration-field").hidden = generator !== "Kimodo";
  if (generator === "Kimodo") {
    $("steps").max = 250; $("steps").min = 10; $("steps").step = 10; $("steps").value = 100;
    $("guidance").value = 2;
    $("model-provenance").textContent = "Kimodo SOMA RP v1.1. Headless local diffusion with cached, layer-streamed LLM2Vec text encoding in full precision. SOMA body motion retargets to the fox. No authored clip constraints; fingers retain the rest pose. Native foot-skate cleanup is disabled.";
  }
  $("motion-duration").oninput = () => setBusy(busy);
  updateOutputs();
  renderRecipes();
  renderLibrary();
  await loadModel();
} catch (e) {
  $("loading-view").textContent = `Unable to load viewer: ${e.message}`;
  toast(e.message);
}
await status();
setInterval(status, 5000);
