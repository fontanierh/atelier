// Shared by the games' browser smoke tests (node games/<game>/<page>/<name>-smoke.mjs): the browser driver from
// platform/web's packages, the stream's address, the game's build folder for reports and screenshots, and a touch page
// opened as a phone and started.
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {chromium} from 'playwright-core';
export {chromium};
const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
/** STREAM_URL, or the stream server on this machine. */
export const STREAM_URL = process.env.STREAM_URL || 'http://127.0.0.1:8080';
/** The installed Chrome (the tests drive a real browser with H.264). */
export const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
/** build/<game>/ as a file URL with a trailing slash (ATELIER_BUILD_ROOT moves build/). */
export function buildDir(game) {
    return pathToFileURL(path.join(path.resolve(process.env.ATELIER_BUILD_ROOT || path.join(repo, 'build')), game) + '/');
}
/** Chrome as a landscape phone (844x390, touch): {browser, context, page}. `args` are Chrome's (default: play sound
 * without a gesture). Chrome closes again when the page cannot be made. */
export async function openTouchPage({args = ['--autoplay-policy=no-user-gesture-required']} = {}) {
    const browser = await chromium.launch({executablePath: CHROME, headless: true, args});
    try {
        const context = await browser.newContext({viewport: {width: 844, height: 390}, hasTouch: true, isMobile: true});
        return {browser, context, page: await context.newPage()};
    } catch (e) { await browser.close(); throw e; }
}
/** Loads STREAM_URL, waits up to `ready` ms for the game's window[telemetry].state.ready, taps #play and, given `video`,
 * waits up to `video.timeout` ms (Playwright's default without one) for the stream's video to have a frame size
 * (`size`) and to be playing (`time`); both by default. */
export async function playTouchPage(page, {telemetry, ready = 60000, video} = {}) {
    await page.goto(STREAM_URL);
    await page.waitForFunction(name => window[name]?.state?.ready, telemetry, {timeout: ready});
    await page.locator('#play').click();
    if (video) await page.waitForFunction(({size, time}) => {
        const v = document.querySelector('video');
        return !!v && (!size || v.videoWidth > 0) && (!time || v.currentTime > 0);
    }, {size: video.size ?? true, time: video.time ?? true}, {timeout: video.timeout});
}
