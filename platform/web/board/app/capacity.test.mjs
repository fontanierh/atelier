import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {test} from 'node:test';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {buildSync} from 'esbuild';

// Render the actual component without a browser, server binary or generated asset changes.
const {outputFiles} = buildSync({entryPoints: ['src/ui/Capacity.tsx'], bundle: true, write: false,
  platform: 'node', format: 'cjs', packages: 'external', jsx: 'automatic'});
const loaded = {exports: {}};
new Function('require', 'module', 'exports', outputFiles[0].text)(createRequire(import.meta.url), loaded, loaded.exports);
const {Capacity} = loaded.exports;
const vector = (io_slots = 0) => ({memory_mib: 1024, cpu_millis: 1000, temp_mib: 1024, gpu_mib: 0, io_slots});
const job = (changes = {}) => ({id: 'job', owner: 'builder', purpose: 'City export', state: 'uncertain', charged: true,
  resources: vector(), locks: [], first_ready: 90, sequence: 1, bypasses: 0, retained: 2, witnessed: 1,
  wait_reason: '', ancestry_unknown: false, ...changes});
const snapshot = (changes = {}) => ({epoch: 1, boot_id: 'fixture', mode: 'capacity', cutover: true,
  observed_at: 100, recovering: false, total: vector(), reserve: vector(), charged_resources: vector(),
  charged_count: 0, waiting_count: 0, total_records: 0, returned_records: 0, records: [], truncated: false, ...changes});
function render(value, props = {}) {
  return renderToStaticMarkup(createElement(Capacity, {connected: true, bridge: false, serverTime: 100,
    status: {configuration: 'configured', availability: 'available', fresh: true, snapshot: value}, ...props}));
}

test('zero I/O budgets and per-job zero requests are omitted', () => {
  const html = render(snapshot({records: [job()], charged_count: 1}));
  assert.doesNotMatch(html, /I\/O|0 slots/);
});

test('every nonzero I/O accounting dimension remains visible', () => {
  for (const key of ['total', 'reserve', 'charged_resources']) {
    const html = render(snapshot({[key]: vector(2)}));
    assert.match(html, /I\/O contention budget/);
    assert.match(html, /2 slots/);
  }
  assert.match(render(snapshot({records: [job({resources: vector(3)})]})), /3 I\/O contention budget slots/);
});

test('uncertain recovery names the job and owner and waits for verified exits', () => {
  const html = render(snapshot({recovering: true, records: [job()], charged_count: 1}));
  assert.match(html, /capacity-tag warning">Capacity recovery/);
  assert.match(html, /waiting for verified process exits: City export \(builder\)/);
});

test('compatibility recovery and truncated unknown recovery are distinct', () => {
  const html = render(snapshot({recovering: true}));
  assert.match(html, /broker compatibility is verified/);
  assert.doesNotMatch(html, /waiting for verified process exits/);
  assert.match(render(snapshot({recovering: true, truncated: true})), /uncertain reservations outside this visible list/);
});

test('bridge recovery remains a bridge until actual cutover', () => {
  const html = render(snapshot({mode: 'legacy-bridge', cutover: false, recovering: true, records: [job()]}));
  assert.match(html, /capacity-tag warning">Capacity bridge recovery/);
  assert.match(html, /Extra concurrency is not enabled/);
  assert.doesNotMatch(html, /Capacity admission|Legacy mutexes remain sealed/);
});

test('stale, disconnected and missing observations never claim current admission', () => {
  for (const html of [render(snapshot({observed_at: 80})), render(snapshot(), {connected: false}), render(null)]) {
    assert.match(html, /capacity-tag warning">Capacity status unavailable/);
    assert.doesNotMatch(html, />Capacity admission</);
  }
  assert.match(render(snapshot({observed_at: 80})), /These figures are stale/);
  assert.match(render(null), /Capacity availability is unknown/);
});
