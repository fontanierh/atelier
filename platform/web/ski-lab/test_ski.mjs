// node --test platform/web/ski-lab/test_ski.mjs
import assert from 'node:assert/strict';
import test from 'node:test';
import { SETTINGS, INPUT, createSkier, advance, report, curvature, angularVelocity } from './sim.js';
import { makePark, makeSlope, touchdown } from './terrain.js';

const ride = (st, terrain, seconds, input = {}) => advance(st, { ...INPUT, ...input }, terrain, seconds);
const crashed = (st) => st.events.some((e) => e.type === 'crash');

test('a straight run accelerates on its skis and loads them with the slope normal', () => {
  const slope = makeSlope(15);
  const st = createSkier(slope, [0, 0], 0, 5);
  ride(st, slope, 4);
  assert.equal(st.mode, 'ride');
  assert.ok(report(st).speed > 10);
  assert.ok(Math.abs(st.groundForce / (SETTINGS.mass * SETTINGS.gravity) - Math.cos(15 * Math.PI / 180)) < 0.05);
  assert.ok(Math.abs(st.p[1]) < 0.05, 'runs straight');
});

test('an edged ski carves the arc its sidecut and edge angle give', () => {
  const flat = makeSlope(0.0001);
  for (const steer of [0.5, 1]) {
    const st = createSkier(flat, [0, 0], 0, 6);
    ride(st, flat, 1.2, { steer });
    const r = report(st);
    const path = Math.abs(r.yawRate) / r.speed;
    assert.ok(Math.abs(path / Math.abs(curvature(st.edge)) - 1) < 0.2, `path ${path} vs sidecut ${curvature(st.edge)}`);
    assert.ok(r.yawRate < 0, 'turns right');
  }
});

test('the rider leans into turns at speed and stays up', () => {
  const flat = makeSlope(0.0001);
  for (const steer of [0.25, 0.5, 1, -1]) {
    const st = createSkier(flat, [0, 0], 0, 12);
    ride(st, flat, 1.5, { steer });
    assert.ok(!crashed(st), `steer ${steer}`);
    assert.ok(Math.sign(report(st).rollDeg) === Math.sign(steer) && Math.abs(report(st).rollDeg) > 10);
  }
});

test('with no balance assist, leaning hard while nearly stopped tips the rider over', () => {
  const flat = makeSlope(0.0001);
  const s = { ...SETTINGS, balanceAssist: 0 };
  const st = createSkier(flat, [0, 0], 0, 1, s);
  advance(st, { ...INPUT, steer: 1 }, flat, 3, s);
  assert.ok(crashed(st));
});

test('a hockey stop stops without tripping over the edges', () => {
  const flat = makeSlope(0.0001);
  const st = createSkier(flat, [0, 0], 0, 12);
  ride(st, flat, 4, { brake: true });
  assert.ok(!crashed(st));
  assert.ok(report(st).speed < 1);
});

test('crouching and extending pops the skis off the snow', () => {
  const flat = makeSlope(0.0001);
  const st = createSkier(flat, [0, 0], 0, 8);
  ride(st, flat, 0.6, { crouch: true });
  let air = 0;
  for (let i = 0; i < 100; i++) { ride(st, flat, 0.01); if (!st.grounded) air += 0.01; }
  assert.ok(air > 0.3, `air ${air}`);
  assert.ok(!crashed(st));
});

test('winding up before the pop launches a spin, and tucking spins faster', () => {
  const flat = makeSlope(0.0001);
  const s = { ...SETTINGS, airAssist: 0, spinAssist: 0 };
  const st = createSkier(flat, [0, 0], 0, 8, s);
  advance(st, { ...INPUT, crouch: true, spin: 1 }, flat, 0.6, s);
  advance(st, { ...INPUT, spin: 1 }, flat, 0.3, s);
  assert.ok(!st.grounded);
  const open = Math.abs(angularVelocity(st, s)[2]);
  assert.ok(open > 2, `spin ${open}`);
  const momentum = st.L.slice();
  advance(st, { ...INPUT, grab: 1 }, flat, 0.15, s);
  assert.ok(!st.grounded);
  assert.ok(Math.abs(angularVelocity(st, s)[2]) > open * 1.2, 'tuck speeds the spin up');
  assert.deepEqual(st.L.map((x) => x.toFixed(6)), momentum.map((x) => x.toFixed(6)), 'no torque in the air');
});

test('jumps are built for their speed window: the slowest clears the knuckle, the fastest reaches the landing', () => {
  for (const jump of makePark().jumps) {
    const p = jump.profile;
    const [slow, fast] = jump.speeds;
    assert.ok(touchdown(p, slow) >= p.tableEnd - 0.01, jump.name);
    assert.ok(touchdown(p, fast) <= p.landingEnd - 3, jump.name);
  }
});

test('a straight run down the park lands every jump on its landing and rides away', () => {
  const park = makePark();
  const st = createSkier(park, park.start, 0, 3);
  const landings = [];
  let wasGrounded = true;
  while (st.p[0] < park.park.finishX - 20 && st.time < 60) {
    ride(st, park, 0.01);
    if (!wasGrounded && st.grounded && st.events.at(-1)?.type === 'land') landings.push(st.p[0]);
    wasGrounded = st.grounded;
  }
  assert.ok(!crashed(st));
  assert.equal(landings.length, park.jumps.length);
  park.jumps.forEach((jump, i) => {
    const u = landings[i] - jump.x;
    assert.ok(u > jump.profile.tableEnd && u < jump.profile.landingEnd, `${jump.name} landed at ${u}`);
  });
});
