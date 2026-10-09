// The scripted park run of ski_sim_test.cpp's `trace`, through the browser lab's sim.js, in the same format.
import { INPUT, createSkier, advance } from '../../../../../web/ski-lab/sim.js';
import { makePark } from '../../../../../web/ski-lab/terrain.js';

const park = makePark();
const st = createSkier(park, park.start, 0, 3);
const lines = [];
for (let tick = 0; tick < 60; tick++) {
  const t = tick * 0.1;
  const input = {
    ...INPUT,
    steer: t < 2 ? 0.4 : t < 3 ? -0.6 : 0,
    lean: t < 1 ? 0.3 : 0,
    crouch: t >= 3.5 && t < 4.2,
    spin: t >= 3.5 && t < 4.3 ? 1 : 0,
    grab: t >= 4.5 && t < 5 ? 2 : 0,
  };
  advance(st, input, park, 0.1);
  const f = (x) => x.toFixed(9);
  lines.push([(t + 0.1).toFixed(1), ...st.p.map(f), ...st.v.map(f), ...st.q.map(f), st.grounded ? 1 : 0].join(' '));
}
console.log(lines.join('\n'));
