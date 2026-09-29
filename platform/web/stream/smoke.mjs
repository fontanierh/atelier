// Shared by the games' browser smoke tests (node games/<game>/<page>/<name>-smoke.mjs): the browser driver from
// platform/web's packages, the stream's address and the game's build folder for reports and screenshots.
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
export {chromium} from 'playwright-core';
const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
/** STREAM_URL, or the stream server on this machine. */
export const STREAM_URL = process.env.STREAM_URL || 'http://127.0.0.1:8080';
/** The installed Chrome (the tests drive a real browser with H.264). */
export const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
/** build/<game>/ as a file URL with a trailing slash (ATELIER_BUILD_ROOT moves build/). */
export function buildDir(game) {
    return pathToFileURL(path.join(path.resolve(process.env.ATELIER_BUILD_ROOT || path.join(repo, 'build')), game) + '/');
}
