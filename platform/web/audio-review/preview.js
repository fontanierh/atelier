"use strict";
// Audition prepared samples only. Each playback session owns every source it
// creates; stopping or superseding a loading session cannot leave audio behind.
(() => {
  const $ = (id) => document.getElementById(`audition-${id}`);
  const status = (text) => {
    $("status").textContent = text;
  };
  let clips = [],
    context,
    master,
    timer,
    generation = 0,
    running = false;
  let nextStep = 0,
    foot = 0,
    loopSource,
    loopCue;
  const buffers = new Map(),
    sources = new Set(),
    bags = new Map();
  const prefix = () =>
    $("mode").value === "footstep" ? "footstep" : "skate.roll";
  const pool = (cue) =>
    clips.filter((c) => c.cue === `${cue}.${$("surface").value}`);
  function choose(cue, variation = true) {
    const candidates = pool(cue);
    if (variation && $("variant").value)
      return candidates.find((c) => c.id === $("variant").value);
    if (!candidates.length) return;
    let bag = bags.get(cue);
    if (!bag?.length) {
      bag = [...candidates];
      for (let i = bag.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [bag[i], bag[j]] = [bag[j], bag[i]];
      }
      bags.set(cue, bag);
    }
    return bag.pop();
  }
  function stop(
    message = "Stopped · Choose a surface and press Start preview.",
  ) {
    generation++;
    running = false;
    clearInterval(timer);
    for (const source of sources) source.stop();
    sources.clear();
    loopSource = undefined;
    loopCue = undefined;
    $("play").disabled = !clips.length;
    $("stop").disabled = true;
    $("land").disabled = true;
    $("pulse").textContent = "L · R";
    $("now").textContent = "";
    status(message);
  }
  function variants() {
    $("variant").replaceChildren(new Option("Shuffle all takes", ""));
    for (const c of pool(prefix()))
      $("variant").append(new Option(c.label, c.id));
  }
  function configure() {
    stop();
    bags.clear();
    const old = $("surface").value;
    const surfaces = [
      ...new Set(
        clips
          .filter((c) => c.cue.startsWith(`${prefix()}.`))
          .map((c) => c.surface),
      ),
    ].sort();
    $("surface").replaceChildren(
      ...surfaces.map((s) => new Option(s.replaceAll("_", " "), s)),
    );
    if (surfaces.includes(old)) $("surface").value = old;
    $("surface").disabled = !surfaces.length;
    $("play").disabled = !surfaces.length;
    variants();
    const skate = $("mode").value === "skate";
    document.getElementById("cadence-control").hidden = skate;
    document.getElementById("speed-control").hidden = !skate;
    document.getElementById("slide-control").hidden = !skate;
    $("land").hidden = !skate;
    $("slide").checked = false;
    $("slide").disabled = !pool("skate.skid").length;
    status(
      skate
        ? `Ready · ${pool("skate.roll").length} rolling takes; ${pool("skate.skid").length} slide takes; ${pool("skate.land").length} landing hits.`
        : `Ready · ${pool("footstep").length} isolated footfalls, shuffled without replacement.`,
    );
  }
  async function load(clip) {
    if (!buffers.has(clip.file)) {
      const pending = fetch(clip.file)
        .then((response) => {
          if (!response.ok) throw new Error("Sample unavailable");
          return response.arrayBuffer();
        })
        .then((bytes) => context.decodeAudioData(bytes));
      buffers.set(clip.file, pending);
      pending.catch(() => buffers.delete(clip.file));
    }
    return buffers.get(clip.file);
  }
  function emit(clip, when, rate = 1, volume = 1, loop = false) {
    if (!clip) return;
    $("now").textContent = clip.label;
    const source = context.createBufferSource(),
      gain = context.createGain();
    source.buffer = clip.buffer;
    source.loop = loop;
    source.playbackRate.value = rate;
    gain.gain.value = volume;
    source.connect(gain).connect(master);
    source.onended = () => {
      sources.delete(source);
      source.disconnect();
      gain.disconnect();
    };
    sources.add(source);
    source.start(when);
    return { source, gain };
  }
  function tick() {
    const now = context.currentTime;
    if ($("mode").value === "footstep") {
      // A browser cadence stand-in for animation foot-plant events, not baked rhythm.
      const cadence = Number($("cadence").value);
      // Drop missed plants after a stalled tab rather than replaying a burst.
      nextStep = Math.max(nextStep, now);
      while (nextStep < now + 0.1) {
        const rate = 0.96 + Math.max(0, (cadence - 100) / 140) * 0.1;
        emit(choose("footstep"), Math.max(now, nextStep), rate, 0.7);
        nextStep += 60 / cadence;
        $("pulse").textContent = foot++ % 2 ? "L · ●" : "● · R";
      }
    } else {
      const cue = $("slide").checked ? "skate.skid" : "skate.roll";
      const speed = Number($("speed").value);
      if (cue !== loopCue) {
        if (loopSource) {
          const previous = loopSource;
          previous.gain.gain.setTargetAtTime(0, now, 0.03);
          previous.source.stop(now + 0.15);
        }
        loopSource = emit(choose(cue, cue === "skate.roll"), now, 1, 0, true);
        loopCue = cue;
      }
      if (loopSource) {
        // Same speed-response ranges as the game, with full-angle slide audition.
        const slide = cue === "skate.skid";
        const volume = slide
          ? 0.9 * Math.min(speed / 4, 1)
          : 0.85 * Math.min(speed / 4.5, 1);
        const rate = slide
          ? 0.9 + 0.3 * Math.min(speed / 8, 1)
          : 0.75 + 0.45 * Math.min(speed / 10, 1);
        loopSource.gain.gain.setTargetAtTime(volume, now, 0.04);
        loopSource.source.playbackRate.setTargetAtTime(rate, now, 0.04);
      }
      $("pulse").textContent =
        speed === 0
          ? "Stationary"
          : $("slide").checked
            ? "Powerslide"
            : "Rolling";
    }
  }
  async function start() {
    stop("Loading selected samples…");
    const token = generation;
    $("play").disabled = true;
    $("stop").disabled = false;
    try {
      // iOS otherwise treats Web Audio as ambient/game audio, which the
      // phone's silent switch can mute even while the context is running.
      if (navigator.audioSession && navigator.audioSession.type !== "playback")
        navigator.audioSession.type = "playback";
      if (!context) {
        context = new AudioContext();
        context.addEventListener("statechange", () => {
          if (context.state !== "running" && running)
            stop(
              "Audio paused by the browser · Press Start preview to resume.",
            );
        });
      }
      master ??= context.createGain();
      master.disconnect();
      master.connect(context.destination);
      master.gain.value = Number($("volume").value) / 100;
      // Call resume in the original tap, before fetching/decoding any WAVs.
      await context.resume();
      if (token !== generation) return;
      if (context.state !== "running") throw new Error("Audio did not start");
      const selected =
        $("mode").value === "footstep"
          ? pool("footstep")
          : [
              ...pool("skate.roll"),
              ...pool("skate.skid"),
              ...pool("skate.land"),
            ];
      await Promise.all(
        selected.map(async (clip) => {
          clip.buffer = await load(clip);
        }),
      );
      if (token !== generation) return;
      if (context.state !== "running")
        throw new Error("Audio was interrupted while loading");
      document.querySelectorAll("audio").forEach((a) => a.pause());
      running = true;
      bags.clear();
      foot = 0;
      nextStep = context.currentTime;
      $("land").disabled = !pool("skate.land").length;
      status(
        "Playing · Browser audition. Stop before comparing another activity or surface.",
      );
      tick();
      timer = setInterval(tick, 25);
    } catch {
      if (token === generation)
        stop(
          "Preview unavailable · Check media volume and connection, then tap Start preview again.",
        );
    }
  }
  $("play").onclick = start;
  $("stop").onclick = () => stop();
  $("mode").onchange = configure;
  $("surface").onchange = configure;
  $("variant").onchange = () =>
    stop("Variation selected · Press Start preview to hear it.");
  $("land").onclick = () => {
    if (running) emit(choose("skate.land", false), context.currentTime);
  };
  for (const [name, suffix] of [
    ["cadence", ""],
    ["speed", ""],
    ["volume", "%"],
  ]) {
    $(name).oninput = () => {
      document.getElementById(`${name}-value`).textContent =
        $(name).value + suffix;
      if (name === "volume" && master)
        master.gain.setTargetAtTime(
          Number($(name).value) / 100,
          context.currentTime,
          0.02,
        );
    };
  }
  document.addEventListener("audition-select", (event) => {
    const clip = clips.find(
      (c) => c.id === event.detail.id && c.file === event.detail.file,
    );
    if (!clip) return;
    $("mode").value = clip.cue.startsWith("footstep.") ? "footstep" : "skate";
    configure();
    $("surface").value = clip.surface;
    configure();
    $("variant").value = clip.id;
    document
      .querySelector(".audition")
      .scrollIntoView({ behavior: "smooth", block: "start" });
    start();
  });
  document.addEventListener("audition-stop", () => stop());
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stop();
  });
  window.addEventListener("pagehide", () => stop());
  fetch("prepared.json", { cache: "no-store" })
    .then((r) => {
      if (!r.ok) throw new Error("Prepared bank unavailable");
      return r.json();
    })
    .then((data) => {
      clips = data.clips.filter(
        (c) =>
          c.status === "ready" &&
          /^samples\/([0-9a-f]{64}\/)?sample-\d+\.wav$/.test(c.file) &&
          /^(footstep|skate\.(roll|skid|land))\.[a-z_]+$/.test(c.cue) &&
          c.cue.endsWith(`.${c.surface}`),
      );
      if (!clips.length) throw new Error("No usable prepared samples");
      configure();
    })
    .catch(() =>
      status(
        "Prepared samples unavailable · You can still listen to raw takes below. Reload when the sample bank is ready.",
      ),
    );
})();
