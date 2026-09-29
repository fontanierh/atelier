// The plain player end to end: node platform/web/stream/player-smoke.mjs (a stream running, `atelier stream <game>
// start --local`). Opens /play/ in Chrome, waits for decoded video, holds W through Pixel Streaming's own keyboard
// input and checks through the live bridge (127.0.0.1:8830) that the player moved: the far device's input reaches the
// game as its own, with no touch page involved.
import {chromium, CHROME, STREAM_URL} from './smoke.mjs';
const LIVE = process.env.LIVE_URL || 'http://127.0.0.1:8830';
const player = async () => (await (await fetch(LIVE + '/state')).json()).player;
const browser = await chromium.launch({executablePath: CHROME, headless: true, args: ['--autoplay-policy=no-user-gesture-required']});
try {
    const page = await browser.newPage({viewport: {width: 1280, height: 720}});
    await page.goto(new URL('/play/', STREAM_URL).href);
    await page.waitForFunction(() => !document.getElementById('play').disabled, {}, {timeout: 90000});
    await page.click('#play');
    await page.waitForFunction(() => { const v = document.querySelector('video'); return v && v.videoWidth > 0 && v.currentTime > 0; }, {}, {timeout: 60000});
    await page.mouse.click(640, 360);   // focus the video, as a player would
    await page.waitForTimeout(500);
    const before = await player();
    await page.keyboard.down('KeyW'); await page.waitForTimeout(1500); await page.keyboard.up('KeyW');
    await page.waitForTimeout(500);
    const after = await player();
    const moved = Math.hypot(after[0] - before[0], after[1] - before[1]);
    const video = await page.evaluate(() => { const v = document.querySelector('video'); return `${v.videoWidth}x${v.videoHeight}`; });
    console.log(JSON.stringify({video, moved_cm: Math.round(moved)}));
    if (moved < 100) throw Error(`the player did not move with W held (${moved.toFixed(0)} cm)`);
    console.log('PLAYER PASS');
} finally { await browser.close(); }
