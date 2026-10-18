// Run against a served, populated review bank: AUDIO_REVIEW_URL=https://... node ...
// Uses the existing platform/web Playwright dependency and the installed Chrome.
import { createRequire } from "node:module";
const { chromium, webkit } = createRequire(import.meta.url)("playwright-core");
import assert from "node:assert/strict";
const base = process.env.AUDIO_REVIEW_URL;
assert(
  base,
  "Set AUDIO_REVIEW_URL to the listening site with prepared samples",
);
const engine = process.env.AUDIO_REVIEW_BROWSER || "chromium";
assert(["chromium", "webkit"].includes(engine));
const browser = await (engine === "webkit" ? webkit : chromium).launch({
  ...(engine === "chromium"
    ? {
        channel: "chrome",
        args: ["--autoplay-policy=document-user-activation-required"],
      }
    : {}),
  headless: true,
});
try {
  const page = await browser.newPage({ hasTouch: true });
  page.setDefaultTimeout(15000);
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const instrumentAudio = () => {
    window.audioProbe = { starts: 0, stops: 0, active: 0, rms: 0, peakRms: 0 };
    // Chromium lacks the iOS API. Model its category there; WebKit uses its
    // actual audio session when available. Neither case bypasses audio unlock.
    if (!navigator.audioSession)
      Object.defineProperty(navigator, "audioSession", {
        value: { type: "auto" },
      });
    const NativeContext = window.AudioContext;
    window.AudioContext = class extends NativeContext {
      get state() {
        return window.audioProbe.blockResume ? "suspended" : super.state;
      }
      resume() {
        window.audioProbe.resumeSession = navigator.audioSession.type;
        window.audioProbe.resumeGesture = navigator.userActivation?.isActive;
        if (window.audioProbe.blockResume) return Promise.resolve();
        return super.resume();
      }
      createGain() {
        const gain = super.createGain();
        if (!window.audioProbe.master) {
          window.audioProbe.master = gain;
          const analyser = this.createAnalyser();
          analyser.fftSize = 2048;
          const connect = gain.connect.bind(gain);
          gain.connect = (destination, ...args) => {
            const result = connect(destination, ...args);
            // Observe the final gain after it is connected to the real output.
            // master.disconnect() during startup must not remove this probe.
            if (destination === this.destination) connect(analyser);
            return result;
          };
          const samples = new Float32Array(analyser.fftSize);
          setInterval(() => {
            analyser.getFloatTimeDomainData(samples);
            const rms = Math.sqrt(
              samples.reduce((sum, x) => sum + x * x, 0) / samples.length,
            );
            window.audioProbe.rms = rms;
            window.audioProbe.peakRms = Math.max(
              window.audioProbe.peakRms,
              rms,
            );
          }, 10);
        }
        return gain;
      }
      createBufferSource() {
        const source = super.createBufferSource();
        const start = source.start.bind(source),
          stop = source.stop.bind(source);
        let stopped = false;
        source.start = (...args) => {
          window.audioProbe.starts++;
          window.audioProbe.active++;
          source.addEventListener("ended", () => {
            window.audioProbe.active--;
          });
          return start(...args);
        };
        source.stop = (...args) => {
          if (!stopped) window.audioProbe.stops++;
          stopped = true;
          return stop(...args);
        };
        return source;
      }
    };
  };
  await page.addInitScript(instrumentAudio);
  await page.goto(base + "?bank=samples");
  await page.waitForFunction(
    () => !document.getElementById("audition-play").disabled,
  );
  await page.waitForSelector(".card audio");
  // Keep the control-ownership tour on one contact while the independent
  // phone smoke below exercises the unfiltered library and a fresh gesture.
  await page.locator("#search").fill("Walking · asphalt · Hit 1");
  const loop = page.locator(".clip-loop input").first();
  await loop.check();
  assert.equal(
    await page
      .locator(".card audio")
      .first()
      .evaluate((a) => a.loop),
    true,
  );
  await loop.uncheck();
  assert.equal(
    await page
      .locator(".card audio")
      .first()
      .evaluate((a) => a.loop),
    false,
  );
  await page.locator("#audition-play").tap();
  await page.waitForFunction(() => window.audioProbe.starts >= 3);
  await page.waitForFunction(() => window.audioProbe.peakRms > 0.001);
  assert.equal(
    await page.evaluate(() => window.audioProbe.resumeSession),
    "playback",
  );
  if (await page.evaluate(() => Boolean(navigator.userActivation)))
    assert.equal(
      await page.evaluate(() => window.audioProbe.resumeGesture),
      true,
    );
  assert.match(await page.locator("#audition-now").innerText(), /Walking/);
  console.log(
    `${engine}: real tap unlocked audio; measured footstep output`,
    await page.evaluate(() => window.audioProbe.peakRms),
  );
  await page.locator("#audition-stop").click();
  await page.waitForFunction(() => window.audioProbe.active === 0);
  const count = await page.evaluate(() => window.audioProbe.starts);
  await page.waitForTimeout(650);
  assert.equal(await page.evaluate(() => window.audioProbe.starts), count);
  // A browser may resolve resume without actually running the context. It must
  // remain retryable, and must never claim playback or schedule silent sources.
  await page.evaluate(() => {
    window.audioProbe.blockResume = true;
  });
  await page.locator("#audition-play").tap();
  await page.waitForFunction(() =>
    document
      .getElementById("audition-status")
      .textContent.startsWith("Preview unavailable"),
  );
  assert.equal(await page.evaluate(() => window.audioProbe.starts), count);
  assert.equal(await page.locator("#audition-play").isEnabled(), true);
  await page.evaluate(() => {
    window.audioProbe.blockResume = false;
  });
  // Directly audition one selected prepared contact from its card.
  await page.locator(".clip-audition").first().click();
  await page.waitForFunction((n) => window.audioProbe.starts > n, count);
  assert.notEqual(await page.locator("#audition-variant").inputValue(), "");
  await page.locator("#audition-stop").click();
  await page.waitForFunction(() => window.audioProbe.active === 0);
  // A fixed variation remains the audible contact at a faster cadence.
  const variant = await page
    .locator("#audition-variant option")
    .nth(1)
    .getAttribute("value");
  const label = await page
    .locator("#audition-variant option")
    .nth(1)
    .innerText();
  await page.locator("#audition-variant").selectOption(variant);
  await page.locator("#audition-cadence").fill("240");
  await page.locator("#audition-play").click();
  await page.waitForFunction((n) => window.audioProbe.starts >= n + 4, count);
  assert.equal(await page.locator("#audition-now").innerText(), label);
  await page
    .locator(".card audio")
    .first()
    .evaluate((a) => a.play());
  await page.waitForFunction(() => window.audioProbe.active === 0);
  await page
    .locator(".card audio")
    .first()
    .evaluate((a) => a.pause());
  await page.locator("#audition-mode").selectOption("skate");
  await page.locator("#audition-surface").selectOption("concrete");
  await page.locator("#audition-play").click();
  await page.waitForFunction(
    () => document.getElementById("audition-pulse").textContent === "Rolling",
  );
  await page.waitForFunction(() => window.audioProbe.rms > 0.001);
  console.log(`${engine}: measured rolling output and volume recovery`);
  await page.locator("#audition-volume").fill("0");
  await page.waitForFunction(() => window.audioProbe.rms < 0.00001);
  await page.locator("#audition-volume").fill("75");
  await page.waitForFunction(() => window.audioProbe.rms > 0.001);
  await page.locator("#audition-speed").fill("0");
  await page.waitForFunction(
    () =>
      document.getElementById("audition-pulse").textContent === "Stationary",
  );
  await page.locator("#audition-speed").fill("8");
  await page.locator("#audition-slide").check();
  await page.waitForFunction(
    () =>
      document.getElementById("audition-pulse").textContent === "Powerslide",
  );
  await page.locator("#audition-land").click();
  assert.match(await page.locator("#audition-now").innerText(), /Landing/);
  await page.locator("#audition-surface").selectOption("wood");
  await page.waitForFunction(() => window.audioProbe.active === 0);
  // Cancel while a fresh surface is loading: late responses must stay silent.
  await page.route("**/samples/**/*.wav", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 350));
    await route.continue();
  });
  await page.locator("#audition-mode").selectOption("footstep");
  await page.locator("#audition-surface").selectOption("grass");
  const before = await page.evaluate(() => window.audioProbe.starts);
  await page.locator("#audition-play").click({ noWaitAfter: true });
  await page.locator("#audition-stop").click({ noWaitAfter: true });
  await page.waitForTimeout(1000);
  assert.equal(await page.evaluate(() => window.audioProbe.starts), before);
  await page.unroute("**/samples/**/*.wav");
  console.log(`${engine}: delayed-load cancellation passed; retrying`);
  await page.locator("#audition-play").click({ noWaitAfter: true });
  await page.waitForFunction((n) => window.audioProbe.starts > n, before);
  await page.locator("#bank").selectOption("manifest.json");
  await page.waitForFunction(() => window.audioProbe.active === 0);
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    true,
  );
  await page.locator("#audition-play").click();
  await page.waitForFunction(() => window.audioProbe.active > 0);
  await page.evaluate(() => {
    Object.defineProperty(document, "hidden", {
      configurable: true,
      value: true,
    });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await page.waitForFunction(() => window.audioProbe.active === 0);
  const phone = await browser.newPage({
    viewport: { width: 390, height: 844 },
    hasTouch: true,
    isMobile: true,
  });
  phone.setDefaultTimeout(15000);
  phone.on("pageerror", (error) => errors.push(error.message));
  await phone.addInitScript(instrumentAudio);
  await phone.goto(base + "?bank=samples");
  await phone.waitForFunction(
    () => !document.getElementById("audition-play").disabled,
  );
  await phone.locator("#audition-play").tap();
  await phone.waitForFunction(() => window.audioProbe.peakRms > 0.001);
  assert.equal(
    await phone.evaluate(() => window.audioProbe.resumeSession),
    "playback",
  );
  console.log(
    `${engine}: fresh phone-sized tap produced output`,
    await phone.evaluate(() => window.audioProbe.peakRms),
  );
  await phone.locator("#audition-stop").tap();
  await phone.waitForFunction(() => window.audioProbe.active === 0);
  await phone.close();
  assert.deepEqual(errors, []);
  console.log(
    `PASS ${engine}: touch unlock/playback session, measured nonzero output and volume, suspended-resume recovery, clip loops, cadence/variation, stop, individual playback, roll/speed/slide/landing, selection/load/bank/visibility cancellation, mobile width, no JS errors`,
  );
} finally {
  await browser.close();
}
