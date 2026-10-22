/* Crater Park editor: piece geometry, meshing and ride physics (no THREE dependency; also runs under node for tests).
   Frame: native metres, plan (x, z), y up, world altitude = y + 680. Heading in degrees from +x toward +z;
   a positive turn is a right turn for the rider. Slopes in degrees, negative = downhill.
   Vertical profiles use horizontal distance d along the plan path (as v4/check.py vprofile). */
(function (root) {
  'use strict';
  const D2R = Math.PI / 180, G = 9.81;
  const DRAG_V = [0, 8, 11, 12, 12.6, 13.4, 16, 18, 20, 22, 25, 28, 30, 40];
  const DRAG_A = [0, 0, .06, .15, .4, .75, .82, .95, 1.0, 1.08, 1.1, 1.2, 1.25, 1.4];
  const PHYS = { starts: [1, 4, 8], turn_loss_c: 0.015, qp_loss: 3.4, qp_window: [14, 21], lift_deg: 2, impact_max: 7,
    touch_min: 3, bowl_entry_max: 25 };

  const interp = (x, xs, ys) => {
    if (x <= xs[0]) return ys[0];
    for (let i = 1; i < xs.length; i++) if (x <= xs[i]) return ys[i - 1] + (ys[i] - ys[i - 1]) * (x - xs[i - 1]) / (xs[i] - xs[i - 1]);
    return ys[ys.length - 1];
  };
  const drag = v => interp(v, DRAG_V, DRAG_A);
  const wrap = a => ((a + 180) % 360 + 360) % 360 - 180;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const num = (v, d) => (v === undefined || v === null || Number.isNaN(+v) ? d : +v);

  function arcDx(R, a, b) { return R * Math.abs(Math.sin(b * D2R) - Math.sin(a * D2R)); }

  /* [[d, y, slope]] from ['line', L] / ['arc', R, to_deg] parts (same as check.py vprofile) */
  function vprofile(y0, a0, parts, step) {
    step = step || 0.5;
    let s = 0, y = y0, a = a0;
    const out = [[0, y, a]];
    for (const p of parts) {
      if (p[0] === 'line') {
        const L = Math.max(0, p[1]);
        if (L < 1e-9) continue;
        const n = Math.max(1, Math.ceil(L / step));
        for (let i = 0; i < n; i++) { s += L / n; y += L / n * Math.tan(a * D2R); out.push([s, y, a]); }
      } else {
        const R = p[1], to = p[2];
        if (Math.abs(to - a) < 1e-9) continue;
        if (R <= 1e-6) { a = to; out[out.length - 1][2] = a; continue; }
        const n = Math.max(1, Math.ceil(R * Math.abs(to - a) * D2R / step)), sg = to > a ? 1 : -1;
        for (let k = 1; k <= n; k++) {
          const b = a + (to - a) * k / n, pr = a + (to - a) * (k - 1) / n;
          s += R * Math.abs(Math.sin(b * D2R) - Math.sin(pr * D2R));
          y += sg * R * (Math.cos(pr * D2R) - Math.cos(b * D2R));
          out.push([s, y, b]);
        }
        a = to;
      }
    }
    return out;
  }
  const arcDy = (R, a, b) => { const p = vprofile(0, a, [['arc', R, b]]); return p[p.length - 1][1]; };

  function runProfile(y0, a0, L, slope, vR, endSlope) {
    const ends = endSlope !== null && endSlope !== undefined;
    let dx = arcDx(vR, a0, slope) + (ends ? arcDx(vR, slope, endSlope) : 0);
    if (dx > L && dx > 0) { vR *= L / dx; dx = L; }
    const parts = [['arc', vR, slope], ['line', Math.max(0, L - dx)]];
    if (ends) parts.push(['arc', vR, endSlope]);
    return vprofile(y0, a0, parts, 1.0);
  }

  /* ------------------------------------------------------------------ plan paths */
  function planPath(pose, L, turn) {
    const h0 = pose.h * D2R, k = L > 1e-9 ? turn * D2R / L : 0;
    if (Math.abs(k) < 1e-9) return d => ({ x: pose.x + d * Math.cos(h0), z: pose.z + d * Math.sin(h0), h: pose.h });
    return d => ({ x: pose.x + (Math.sin(h0 + k * d) - Math.sin(h0)) / k, z: pose.z + (Math.cos(h0) - Math.cos(h0 + k * d)) / k,
      h: pose.h + turn * d / L });
  }

  /* ------------------------------------------------------------------ piece types */
  const WALL = { h: 2.75, R: 3.0 };
  const P = (key, label, unit, min, max, step, help, extra) => Object.assign({ key, label, unit, min, max, step, help }, extra || {});
  const wallParams = [
    P('wl.h', 'Left wall height', 'm', 0, 30, 0.1, 'Rider’s left. 0 = no wall. Above the radius it goes vertical (vert).'),
    P('wl.R', 'Left wall radius', 'm', 0.5, 22, 0.1, 'Transition radius of the curved wall.'),
    P('wr.h', 'Right wall height', 'm', 0, 30, 0.1, 'Rider’s right. 0 = no wall.'),
    P('wr.R', 'Right wall radius', 'm', 0.5, 22, 0.1, ''),
    P('deck', 'Deck behind walls', 'm', 0, 6, 0.1, 'Flat coping deck on top of each wall.'),
  ];
  // jumps and kickers: empty = carry on the walls of the runway before, up the kicker to the lip (a halfpipe going up)
  const kickerWallParams = wallParams.map(d => ({ ...d, nullable: true, help: (d.help ? d.help + ' ' : '') + 'Empty = same as the runway before.' }));
  const receiverParams = [
    P('knuckle_R', 'Knuckle radius', 'm', 0, 40, 0.5, 'Rounding from the flat knuckle into the landing slope.'),
    P('land_deg', 'Landing angle', '°', 5, 88, 0.5, 'Steepness of the landing slope (45° and up: a vert landing).'),
    P('land_len', 'Landing length', 'm', 0, 80, 0.5, 'Straight part of the landing slope.'),
    P('out_R', 'Run-out radius', 'm', 2, 200, 1, 'Curve from the landing slope back to flat.'),
    P('mid_deg', 'Middle slope', '°', -80, 0, 0.5, 'Optional slope between landing and run-out: gentle for mega ramps, or steeper than the landing for a vert landing that steepens with the fall.'),
    P('mid_len', 'Middle length', 'm', 0, 80, 0.5, ''),
    P('end_deg', 'Exit slope', '°', -20, 5, 0.5, ''),
    P('out_len', 'Run-out length', 'm', 0, 120, 0.5, 'Flat after the landing.'),
    P('land_width', 'Landing width', 'm', 8, 50, 0.5, 'Receivers flare: 22 m medium, 28 m mega.'),
  ];

  const TEMPLATES = {
    med15: { kick_R: 22, lip_deg: 18, lip_len: 3, open: 15, drop: 1, knuckle_R: 4, land_deg: 30, land_len: 10.5, out_R: 10, mid_deg: 0, mid_len: 0, end_deg: 0, out_len: 25, width: 18, land_width: 22, lift: 1.5 },
    med20: { kick_R: 22, lip_deg: 14, lip_len: 3, open: 20, drop: 2.5, knuckle_R: 4, land_deg: 30, land_len: 11.5, out_R: 10, mid_deg: 0, mid_len: 0, end_deg: 0, out_len: 25, width: 18, land_width: 22, lift: 1.5 },
    med25: { kick_R: 40, lip_deg: 24, lip_len: 3, open: 25, drop: 3, knuckle_R: 4, land_deg: 35, land_len: 9, out_R: 10, mid_deg: 0, mid_len: 0, end_deg: 0, out_len: 25, width: 18, land_width: 22, lift: 1.5 },
    med30: { kick_R: 40, lip_deg: 24, lip_len: 3, open: 30, drop: 4, knuckle_R: 4, land_deg: 35, land_len: 9, out_R: 10, mid_deg: 0, mid_len: 0, end_deg: 0, out_len: 25, width: 18, land_width: 22, lift: 1.5 },
    mega42: { kick_R: 30, lip_deg: 16, lip_len: 3, open: 42, drop: 4, knuckle_R: 20, land_deg: 26, land_len: 34, out_R: 80, mid_deg: -5, mid_len: 25, end_deg: 0, out_len: 35, width: 18, land_width: 28, lift: 1.2 },
    mega55: { kick_R: 30, lip_deg: 18, lip_len: 3, open: 55, drop: 6, knuckle_R: 20, land_deg: 24, land_len: 34, out_R: 80, mid_deg: -5, mid_len: 25, end_deg: 0, out_len: 35, width: 18, land_width: 28, lift: 0.5 },
  };
  const TEMPLATE_NOTE = {
    med15: 'proven: 15 m gap, ~7 m net drop', med20: 'proven: 20 m gap, ~9.8 m net drop', med25: 'proven: 25 m gap, ~7.3 m net drop',
    med30: 'proven: 30 m gap, lip 18.2–19.2 m/s, lands ±7 m wide', mega42: 'proven: 42 m mega, 52–54 m air', mega55: 'proven: 55 m mega, lip 27.8–28.5 m/s, 63–68 m air',
  };

  const TYPES = {
    run: {
      label: 'Runway', ride: true,
      defaults: { len: 40, turn: 0, slope: -5, vR: 80, ease_end: false, end_slope: 0, bank: 0, width: 18, width_end: null, wl: { ...WALL }, wr: { ...WALL }, deck: 1.5, wall_blend: 12, dig: false },
      params: [
        P('len', 'Length', 'm', 1, 400, 0.5, 'Plan length along the centreline.'),
        P('turn', 'Turn', '°', -200, 200, 1, 'Plan turn over the piece. + right, − left. 0 = straight.'),
        P('slope', 'Slope', '°', -45, 30, 0.1, 'Target slope. Eases in from the previous piece with the vertical radius.'),
        P('ease_end', 'Ease to an end slope', '', 0, 1, 1, '', { kind: 'bool' }),
        P('end_slope', 'End slope', '°', -45, 30, 0.1, 'Slope at the end (used when easing).', { showIf: 'ease_end' }),
        P('vR', 'Vertical ease radius', 'm', 5, 400, 1, 'How gently the slope changes (80 m is comfortable at 25 m/s).'),
        P('bank', 'Bank', '°', -35, 35, 0.5, 'Tilts the floor across: + raises the rider’s left side (for right turns).'),
        P('width', 'Floor width', 'm', 4, 80, 0.5, 'Flat floor between the walls (18 m standard).'),
        P('width_end', 'Floor width at end', 'm', 4, 80, 0.5, 'Leave empty for constant width (use for flared mouths).', { nullable: true }),
        P('shift', 'Side shift', 'm', -40, 40, 0.5, 'Starts the piece this far to the rider’s left (+) or right (−) of its parent’s end: two half-width pieces side by side make split lanes.'),
        ...wallParams,
        P('wall_blend', 'Wall blend', 'm', 0, 80, 0.5, 'The walls grow or shrink smoothly from the piece before over this length, so they run on as one wall. 0 = sudden change.'),
        P('dig', 'Cut the ground under it', '', 0, 1, 1, 'Cuts the crater ground away: under the floor, just below each deck top out past the deck edge, then 40° rock banks up to the ground.', { kind: 'bool' }),
      ],
    },
    rollin: {
      label: 'Roll-in', ride: true, start: true,
      defaults: { drop: 30, steep_deg: 35, crest_R: 40, foot_R: 40, out_deg: -5, run: 10, turn: 0, bank: 0, width: 18, wl: { ...WALL }, wr: { ...WALL }, deck: 1.5, dig: false },
      params: [
        P('drop', 'Drop height', 'm', 2, 250, 0.5, 'Vertical drop from the top to the foot.'),
        P('steep_deg', 'Steepness', '°', 10, 88, 0.5, 'Angle of the steepest part (the incline).'),
        P('crest_R', 'Top curve radius', 'm', 2, 300, 1, 'How gradually it tips over at the top. Bigger = gentler.'),
        P('foot_R', 'Bottom curve radius', 'm', 2, 300, 1, 'How gradually it flattens at the bottom. Bigger = gentler, less compression.'),
        P('out_deg', 'Exit slope', '°', -30, 5, 0.5, 'Slope it hands over to the next piece.'),
        P('run', 'Run-out length', 'm', 0, 100, 0.5, ''),
        P('turn', 'Bend', '°', -180, 180, 1, 'Curves the whole roll-in in plan: + right, − left. Use a vert corner after it for a sharp elbow.'),
        P('bank', 'Bank', '°', -35, 35, 0.5, 'Tilts it across: + raises the rider’s left side.'),
        P('width', 'Width', 'm', 4, 60, 0.5, ''),
        ...wallParams,
        P('dig', 'Cut the ground under it', '', 0, 1, 1, 'Cuts the crater ground away: under the floor, just below each deck top out past the deck edge, then 40° rock banks up to the ground.', { kind: 'bool' }),
      ],
    },
    jump: {
      label: 'Gap jump', ride: true,
      defaults: { ...TEMPLATES.med25, template: 'med25', rail: false, run_in: 0, dig: false },
      params: [
        P('template', 'Proven module', '', 0, 0, 0, 'Load a physics-tested gap. Editing any value makes it custom.', { kind: 'template' }),
        P('open', 'Gap length', 'm', 3, 90, 0.5, 'Lip to knuckle, horizontal.'),
        P('drop', 'Knuckle below lip', 'm', -10, 30, 0.1, ''),
        P('kick_R', 'Kicker radius', 'm', 4, 80, 0.5, ''),
        P('lip_deg', 'Lip angle', '°', 0, 88, 0.5, ''),
        P('lip_len', 'Lip straight', 'm', 0, 10, 0.1, ''),
        P('run_in', 'Run-in before kicker', 'm', 0, 60, 0.5, ''),
        P('width', 'Kicker width', 'm', 4, 50, 0.5, ''),
        ...kickerWallParams,
        ...receiverParams,
        P('rail', 'Rainbow rail over the gap', '', 0, 1, 1, '', { kind: 'bool' }),
        P('dig', 'Cut the ground under it', '', 0, 1, 1, 'Cuts the crater ground away: under the floor, just below each deck top out past the deck edge, then 40° rock banks up to the ground.', { kind: 'bool' }),
      ],
    },
    kicker: {
      label: 'Kicker', ride: true, flies: true,
      defaults: { kick_R: 25, lip_deg: 20, lip_len: 2, run_in: 0, width: 18, lift: 1.5, dig: false },
      params: [
        P('kick_R', 'Radius', 'm', 3, 80, 0.5, ''), P('lip_deg', 'Lip angle', '°', 0, 60, 0.5, ''),
        P('lip_len', 'Lip straight', 'm', 0, 10, 0.1, ''), P('run_in', 'Run-in', 'm', 0, 60, 0.5, ''),
        P('width', 'Width', 'm', 4, 50, 0.5, ''),
        ...kickerWallParams,
        P('dig', 'Cut the ground under it', '', 0, 1, 1, 'Cuts the crater ground away: under the floor, just below each deck top out past the deck edge, then 40° rock banks up to the ground.', { kind: 'bool' }),
      ],
    },
    landing: {
      label: 'Landing', ride: true,
      defaults: { deck_len: 4, knuckle_R: 4, land_deg: 30, land_len: 12, out_R: 12, mid_deg: 0, mid_len: 0, end_deg: 0, out_len: 15, width: 18, land_width: 22, dig: false },
      params: [P('deck_len', 'Knuckle deck', 'm', 0, 30, 0.5, 'Flat top before the knuckle.'), ...receiverParams, P('width', 'Run-out width', 'm', 4, 50, 0.5, ''), ...kickerWallParams, P('dig', 'Cut the ground under it', '', 0, 1, 1, 'Cuts the crater ground away: under the floor, just below each deck top out past the deck edge, then 40° rock banks up to the ground.', { kind: 'bool' })],
    },
    qp: {
      label: 'Quarter pipe', ride: true,
      defaults: { approach: 6, h: 4, R: 3.5, deck: 3, width: 18, dig: false },
      params: [P('approach', 'Flat in front', 'm', 0, 40, 0.5, ''), P('h', 'Height', 'm', 0.5, 22, 0.1, 'Above the radius it goes vertical (vert).'),
        P('R', 'Transition radius', 'm', 0.5, 22, 0.1, ''), P('deck', 'Deck', 'm', 0, 10, 0.1, ''), P('width', 'Width', 'm', 2, 60, 0.5, ''), P('dig', 'Cut the ground under it', '', 0, 1, 1, 'Cuts the crater ground away: under the floor, just below each deck top out past the deck edge, then 40° rock banks up to the ground.', { kind: 'bool' })],
    },
    bowl: {
      label: 'Bowl', ride: true, terminal: true,
      defaults: { outline: circle(14, 24), wall_h: 3.2, wall_R: 2.5, deck: 2, through: false, mouth: 18, size: 60, flare: 20 },
      params: [P('through', 'Exit on the far side', '', 0, 1, 1, 'The line runs through: the rider comes in at the piece position and leaves on the opposite side.', { kind: 'bool' }),
        P('size', 'Bowl diameter', 'm', 16, 150, 0.5, 'The round part. The necks take the width and walls of the runway before, so the walls run on as one.', { showIf: 'through' }),
        P('flare', 'Flare radius', 'm', 2, 80, 0.5, 'How gradually the runway opens into the bowl: bigger = longer, rounder flare.', { showIf: 'through' }),P('wall_h', 'Wall height', 'm', 0.5, 15, 0.1, 'Floor to coping.'), P('wall_R', 'Transition radius', 'm', 0.5, 15, 0.1, ''),
        P('deck', 'Deck', 'm', 0, 8, 0.1, ''), P('outline', 'Shape', '', 0, 0, 0, 'Drag the white points on the rim. Click a small dot to add a point; Alt-click a point to remove it.', { kind: 'outline' })],
    },
    deck: {
      label: 'Deck / platform', ride: false,
      defaults: { len: 20, width: 20, thick: 2, solid: true },
      params: [P('len', 'Length', 'm', 1, 200, 0.5, ''), P('width', 'Width', 'm', 1, 200, 0.5, ''), P('thick', 'Thickness', 'm', 0.2, 10, 0.1, ''),
        P('solid', 'Solid down to the ground', '', 0, 1, 1, '', { kind: 'bool' })],
    },
    rail: {
      label: 'Rainbow rail', ride: false,
      defaults: { len: 30, rise: 4 },
      params: [P('len', 'Span', 'm', 2, 100, 0.5, ''), P('rise', 'Arch height', 'm', 0, 20, 0.1, '')],
    },
  };

  function circle(r, n) { const o = []; for (let i = 0; i < n; i++) { const t = i / n * 2 * Math.PI; o.push([+(r * Math.cos(t)).toFixed(2), +(r * Math.sin(t)).toFixed(2)]); } return o; }

  function getp(p, key) {
    const d = TYPES[p.type].defaults;
    if (key.includes('.')) { const [a, b] = key.split('.'); const o = (p.params || {})[a]; const od = d[a] || {}; return num(o && o[b], od[b]); }
    const v = (p.params || {})[key];
    return v === undefined ? d[key] : v;
  }

  /* receiver profile from the knuckle (level), d measured from the knuckle */
  function receiverProfile(p, y0) {
    const q = k => num(getp(p, k), 0);
    return vprofile(y0, 0, [['arc', q('knuckle_R'), -q('land_deg')], ['line', q('land_len')], ['arc', q('out_R'), q('mid_deg')],
      ['line', q('mid_len')], ['arc', q('out_R'), q('end_deg')], ['line', q('out_len')]], 0.5);
  }

  /* ------------------------------------------------------------------ build one piece
     returns { pose, stations: [{d,x,z,y,h,a,w,wl,wr,deck,seg}], segs:[[i0,i1]], exit, len, info } */
  function build(p, pose) {
    const t = p.type, q = k => num(getp(p, k), 0);
    const walls = () => ({ wl: { h: q('wl.h'), R: q('wl.R') }, wr: { h: q('wr.h'), R: q('wr.R') }, deck: q('deck') });
    const none = { wl: { h: 0, R: 1 }, wr: { h: 0, R: 1 }, deck: 0 };
    // jumps, kickers, landings: their own wall values where set, else the walls of the runway before
    const carriedWalls = () => {
      const inh = pose.walls || none;
      const own = k => { const o = p.params && p.params[k]; return o && o.h !== undefined && o.h !== null && o.h !== '' ? { h: num(o.h, 0), R: num(o.R, inh[k].R || WALL.R) } : null; };
      const ownDeck = p.params && p.params.deck !== undefined && p.params.deck !== null && p.params.deck !== '' ? num(p.params.deck, 0) : null;
      return { wl: own('wl') || inh.wl, wr: own('wr') || inh.wr, deck: ownDeck !== null ? ownDeck : inh.deck };
    };
    let prof, plan, L, sec, segs, info = {}, exit;
    if (t === 'run') {
      L = Math.max(0.5, q('len'));
      const end = getp(p, 'ease_end') ? q('end_slope') : null;
      prof = runProfile(pose.y, pose.a, L, q('slope'), Math.max(1, q('vR')), end);
      // a landing roller at the entry: a rise to a crest, then a straight
      // landing slope down to the original floor. The kicker lands on the
      // crest and the contact projects the rider down the run (fakie).
      const rise = q('entry_rise'), crest = q('entry_crest'), drop = q('entry_drop');
      if (rise > 0 && crest > 0 && drop > 0 && crest < L) {
        const endD = Math.min(L, crest + rise / Math.tan(drop * D2R));
        const t = Math.tan(drop * D2R), A = (-t - 2 * rise / crest) / (crest * crest), B = rise / (crest * crest) - A * crest;
        for (const point of prof) {
          const d = point[0];
          if (d > endD) continue;
          if (d <= crest) {
            point[1] += A * d * d * d + B * d * d;
            point[2] = Math.atan(3 * A * d * d + 2 * B * d) / D2R;
          } else {
            point[1] += rise - (d - crest) * Math.tan(drop * D2R);
            point[2] = -drop;
          }
        }
      }
      plan = planPath(pose, L, q('turn'));
      const w0 = q('width'), w1 = getp(p, 'width_end') === null || getp(p, 'width_end') === undefined || getp(p, 'width_end') === '' ? w0 : q('width_end');
      const W = walls(), inh = pose.walls && pose.walls.wl ? pose.walls : null, Lb = Math.min(q('wall_blend'), L);
      const bank = q('bank');
      // start with exactly the walls of the piece before and ease to this piece's own (smoothstep over the blend length)
      const lerpW = (a, b, t) => ({ h: a.h + (b.h - a.h) * t, R: a.R + (b.R - a.R) * t });
      const WA = d => { if (!inh || Lb <= 0 || d >= Lb) return W; const x = d / Lb, t = x * x * (3 - 2 * x); return { wl: lerpW(inh.wl, W.wl, t), wr: lerpW(inh.wr, W.wr, t), deck: num(inh.deck, W.deck) + (W.deck - num(inh.deck, W.deck)) * t }; };
      // a wall with `level: true` keeps its coping at the start height: it grows as the floor drops (beside a deck or infill)
      const lvl = k => !!(p.params && p.params[k] && p.params[k].level);
      const yAt = d => { for (let i = 1; i < prof.length; i++) if (prof[i][0] >= d) { const a = prof[i - 1], c = prof[i], t = (d - a[0]) / ((c[0] - a[0]) || 1); return a[1] + (c[1] - a[1]) * t; } return prof[prof.length - 1][1]; };
      const WAL = d => { const Wd = WA(d); if (!lvl('wl') && !lvl('wr')) return Wd; const out = { ...Wd }, drop = prof[0][1] - yAt(d);
        for (const k of ['wl', 'wr']) if (lvl(k)) out[k] = { ...Wd[k], h: Wd[k].h + drop }; return out; };
      // inside a tight turn the inner wall and deck may not reach the turn centre (they would fold over it)
      const Rc = Math.abs(q('turn')) > 0.5 ? L / Math.abs(q('turn') * D2R) : Infinity, inner = q('turn') > 0 ? 'wr' : 'wl';
      const trim = (Wd, w) => {
        if (!Number.isFinite(Rc)) return Wd;
        const room = Rc - 0.5 - w / 2, wl = Wd[inner], ext = wl.h >= wl.R ? wl.R : wl.R * Math.sin(Math.acos(1 - wl.h / wl.R));
        if (ext + Wd.deck <= room) return Wd;
        const out = { ...Wd, [inner]: { ...wl } };
        if (ext > room) { const r = Math.max(0, room); out[inner].h = r >= wl.R ? wl.h : wl.R * (1 - Math.cos(Math.asin(r / wl.R))); }
        out.deck = Math.max(0, Math.min(Wd.deck, room - Math.min(ext, Math.max(0, room))));
        return out;
      };
      // a tight turn after this piece lowers its inner wall from the start: ease into those walls over the last blend
      // length here (pose.endWalls), so the joint has no step
      const EW = pose.endWalls, Le = Math.min(q('wall_blend'), L / 2);
      const toEnd = (Wd, d) => {
        if (!EW || Le <= 0 || d <= L - Le) return Wd;
        const x = (d - (L - Le)) / Le, t = x * x * (3 - 2 * x);
        return { wl: lerpW(Wd.wl, EW.wl, t), wr: lerpW(Wd.wr, EW.wr, t), deck: Wd.deck + (EW.deck - Wd.deck) * t };
      };
      // the width also starts at the width of the piece before and eases to this piece's own over the blend length
      const wi = inh && Number.isFinite(inh.w) && inh.w > 0 ? inh.w : null;
      const WD = d => { const w = w0 + (w1 - w0) * d / L; if (wi === null || Lb <= 0 || d >= Lb) return w; const x = d / Lb; return wi + (w - wi) * x * x * (3 - 2 * x); };
      sec = d => { const w = WD(d); return { w, ...toEnd(trim(WAL(d), w), d), bank }; };
      info.needStart = trim(WAL(0), WD(0));
      info.ownEnd = trim(WAL(L), w1);
      segs = [[0, prof.length - 1]];
      const outer = q('turn') > 0 ? W.wl.h : W.wr.h;
      info.corner = Math.abs(q('turn')) >= 45 && Math.max(outer, 0) >= 5;
      info.kappa = Math.abs(q('turn') * D2R) / L;
    } else if (t === 'rollin') {
      const st = q('steep_deg'), cR = q('crest_R'), fR = q('foot_R'), out = q('out_deg'), drop = q('drop');
      const dArcs = -(arcDy(cR, 0, -st) + arcDy(fR, -st, out));
      const Ls = Math.max(0, (drop - dArcs) / Math.tan(st * D2R));
      prof = vprofile(pose.y, 0, [['arc', cR, -st], ['line', Ls], ['arc', fR, out], ['line', q('run')]], 0.5);
      L = prof[prof.length - 1][0];
      plan = planPath(pose, L, q('turn'));
      info.kappa = Math.abs(q('turn') * D2R) / Math.max(1, L);
      info.steepLen = Ls;
      const W = walls();
      const bank = q('bank');
      sec = () => ({ w: q('width'), ...W, bank });
      segs = [[0, prof.length - 1]];
    } else if (t === 'jump' || t === 'kicker') {
      const KW = carriedWalls();
      const kick = vprofile(pose.y, pose.a, [['line', q('run_in')], ['arc', q('kick_R'), q('lip_deg')], ['line', q('lip_len')]], 0.5);
      const lip = kick[kick.length - 1];
      info.lip = { d: lip[0], y: lip[1], a: lip[2], i: kick.length - 1 };
      info.lift = num(getp(p, 'lift'), t === 'jump' && TEMPLATES[getp(p, 'template')] ? TEMPLATES[getp(p, 'template')].lift : PHYS.lift_deg);
      prof = kick.slice();
      segs = [[0, kick.length - 1]];
      if (t === 'jump') {
        const dk = lip[0] + q('open');
        const rec = receiverProfile(p, lip[1] - q('drop'));
        info.knuckle = { d: dk, y: lip[1] - q('drop') };
        const kneeEnd = vprofile(0, 0, [['arc', q('knuckle_R'), -q('land_deg')]], 0.5);
        info.slopeEnd = dk + kneeEnd[kneeEnd.length - 1][0] + q('land_len');
        info.recv = rec.map(r => [r[0] + dk, r[1], r[2]]);
        // a receiver that steepens again (mid_deg steeper than the landing: a vert landing) lands all the way down
        if (-q('mid_deg') > q('land_deg')) for (const r of info.recv) if (r[2] <= -q('land_deg') + 0.01) info.slopeEnd = Math.max(info.slopeEnd, r[0]);
        const i0 = prof.length;
        for (const r of info.recv) prof.push(r);
        segs.push([i0, prof.length - 1]);
        const lw = q('land_width'), w = q('width'), dEnd = prof[prof.length - 1][0];
        sec = d => (d <= lip[0] + 1e-6 ? { w, ...KW } : { w: d <= info.slopeEnd ? lw : lw + (w - lw) * clamp((d - info.slopeEnd) / Math.max(1, dEnd - info.slopeEnd), 0, 1), ...KW });
      } else {
        sec = () => ({ w: q('width'), ...KW });
      }
      L = prof[prof.length - 1][0];
      plan = planPath(pose, L, 0);
      info.solidSegs = [0];
    } else if (t === 'landing') {
      const top = vprofile(pose.y, 0, [['line', q('deck_len')]], 0.5);
      const rec = receiverProfile(p, pose.y);
      prof = top.concat(rec.slice(1).map(r => [r[0] + q('deck_len'), r[1], r[2]]));
      L = prof[prof.length - 1][0];
      plan = planPath(pose, L, 0);
      const kneeEnd = vprofile(0, 0, [['arc', q('knuckle_R'), -q('land_deg')]], 0.5);
      const slopeEnd = q('deck_len') + kneeEnd[kneeEnd.length - 1][0] + q('land_len');
      const lw = q('land_width'), w = q('width'), LW = carriedWalls();
      sec = d => ({ w: d <= slopeEnd ? lw : lw + (w - lw) * clamp((d - slopeEnd) / Math.max(1, L - slopeEnd), 0, 1), ...LW });
      segs = [[0, prof.length - 1]];
      info.knuckle = { d: q('deck_len'), y: pose.y };
      info.solidSegs = [0];
    } else if (t === 'qp') {
      const h = q('h'), R = Math.max(0.3, q('R')), ap = q('approach');
      const tmax = h >= R ? 90 : Math.acos(1 - h / R) / D2R;
      prof = vprofile(pose.y, 0, [['line', ap]], 0.5);
      const n = Math.max(4, Math.ceil(R * tmax * D2R / 0.3));
      for (let k = 1; k <= n; k++) { const b = tmax * k / n; prof.push([ap + R * Math.sin(b * D2R), pose.y + R - R * Math.cos(b * D2R), b]); }
      if (h > R) prof.push([ap + R, pose.y + h, 90]);
      const top = prof[prof.length - 1];
      prof.push([top[0] + q('deck'), top[1], 0]);
      L = prof[prof.length - 1][0];
      plan = planPath(pose, L, 0);
      sec = () => ({ w: q('width'), ...none });
      segs = [[0, prof.length - 1]];
      info.solidSegs = [0];
      info.qp = { h, R };
      exit = { x: pose.x, z: pose.z, y: pose.y, h: wrap(pose.h + 180), a: 0 };
    } else if (t === 'bowl' && getp(p, 'through')) {
      // flow bowl: the line crosses the flat floor from the entry (piece position, on the coping line) to the far side
      const W = pose.walls && pose.walls.wl ? pose.walls : { wl: { ...WALL }, wr: { ...WALL }, deck: 1.5 };
      const fw = num(W.w, q('mouth'));
      // optional exit_wl / exit_wr ({h, R}): the walls the exit neck hands to the runway after (else the entry walls)
      const xw = k => { const o = p.params && p.params['exit_' + k]; return o && Number.isFinite(+o.h) ? { h: +o.h, R: num(o.R, W[k].R) } : W[k]; };
      const WX = { wl: xw('wl'), wr: xw('wr'), deck: W.deck };
      const K = keyholeOutline(fw, W, q('size'), q('flare'), WX);
      Object.assign(info, { through: true, outline: K.outline, mouthEdges: K.mouthEdges, neck: K.neck });
      L = K.Lt;
      prof = vprofile(pose.y, 0, [['line', L]], 0.5);
      plan = planPath(pose, L, 0);
      sec = () => ({ w: fw, ...none });
      segs = [[0, prof.length - 1]];
      const e = plan(L); exit = { x: e.x, z: e.z, y: pose.y, h: wrap(pose.h), a: 0, walls: { wl: WX.wl, wr: WX.wr, deck: W.deck, w: fw } };
    } else {
      // bowl / deck / rail: no swept surface (a pool bowl keeps its wall and coping line for flights landing in it)
      if (t === 'bowl') Object.assign(info, { wall: { h: q('wall_h'), R: Math.max(0.3, q('wall_R')) }, outlineLocal: getp(p, 'outline') || [], wallAt: bowlWalls(p) });
      L = 0; prof = [[0, pose.y, 0]]; plan = planPath(pose, 0, 0); sec = () => ({ w: 0, ...none }); segs = [];
    }
    const stations = prof.map(([d, y, a]) => { const pp = plan(d); const s = sec(d); return { d, x: pp.x, z: pp.z, y, h: pp.h, a, w: s.w, wl: s.wl, wr: s.wr, deck: s.deck, bank: s.bank || 0 }; });
    segs.forEach((sg, k) => { for (let i = sg[0]; i <= sg[1]; i++) stations[i].seg = k; });
    if (!exit && TYPES[t].ride && !TYPES[t].terminal && stations.length) {
      const e = stations[stations.length - 1];
      exit = { x: e.x, z: e.z, y: e.y, h: wrap(e.h), a: e.a, walls: { wl: e.wl, wr: e.wr, deck: e.deck, w: e.w } };
    }
    if (t === 'kicker') { const e = stations[info.lip.i]; exit = { x: e.x, z: e.z, y: e.y, h: wrap(e.h), a: e.a }; }
    return { id: p.id, type: t, pose, stations, segs, exit, len: L, info };
  }

  /* ------------------------------------------------------------------ layout: resolve attached poses */
  function poseOf(p) { return { x: +p.x, z: +p.z, y: +p.y, h: +p.heading, a: num(p.slope, 0) }; }

  // two passes: the second gives a run the lowered start walls of a tight turn after it (pose.endWalls)
  function layout(park, prevBuilt, dirty) {
    const prevEnds = new Map();
    if (prevBuilt) for (const [id, b] of prevBuilt) if (b.pose && b.pose.endWalls) prevEnds.set(id, b.pose.endWalls);
    let built = layoutPass(park, prevBuilt, dirty, prevEnds);
    const ends = new Map(), wEq = (a, c) => Math.abs(a.h - c.h) < 0.01 && Math.abs(a.R - c.R) < 0.01;
    const same = (a, c) => wEq(a.wl, c.wl) && wEq(a.wr, c.wr) && Math.abs(a.deck - c.deck) < 0.01;
    for (const p of park.pieces) {
      const b = built.get(p.id), pb = p.attach && built.get(p.attach);
      if (!b || !pb || b.type !== 'run' || pb.type !== 'run' || !b.info.needStart || !pb.info.ownEnd) continue;
      if (num((p.params || {}).shift, 0)) continue;   // split lanes carry only their own side's wall on: the parent keeps its own end
      if (!same(b.info.needStart, pb.info.ownEnd)) ends.set(pb.id, b.info.needStart);
    }
    const changed = [...new Set([...ends.keys(), ...prevEnds.keys()])].some(id => !ends.has(id) || !prevEnds.has(id) || !same(ends.get(id), prevEnds.get(id)));
    if (changed) built = layoutPass(park, built, new Set(), ends);
    markJoins(park, built);
    return built;
  }
  function layoutPass(park, prevBuilt, dirty, ends) {
    const byId = new Map(park.pieces.map(p => [p.id, p]));
    const built = new Map();
    const state = new Map();
    const visit = (p) => {
      if (built.has(p.id)) return built.get(p.id);
      if (state.get(p.id) === 1) { p.attach = null; }          // cycle: break it
      state.set(p.id, 1);
      let pose = poseOf(p);
      const par = p.attach ? byId.get(p.attach) : null;
      if (par) {
        const pb = visit(par);
        if (pb.exit) {
          pose = { x: pb.exit.x, z: pb.exit.z, y: pb.exit.y, h: pb.exit.h, a: TYPES[p.type].start || p.type === 'landing' || p.type === 'qp' || p.type === 'bowl' ? 0 : pb.exit.a, walls: pb.exit.walls };
          // a side shift starts the piece beside its parent's end (split lanes: half-width pieces side by side), walls its own
          const shift = num((p.params || {}).shift, 0);
          if (shift) { const hr = pose.h * D2R; pose.x += Math.sin(hr) * shift; pose.z -= Math.cos(hr) * shift; pose.walls = null; }
          p.x = +pose.x.toFixed(3); p.z = +pose.z.toFixed(3); p.y = +pose.y.toFixed(3); p.heading = +pose.h.toFixed(3); p.slope = +pose.a.toFixed(3);
        }
      } else if (p.attach) p.attach = null;
      if (ends.has(p.id)) pose.endWalls = ends.get(p.id);
      let b;
      const prev = prevBuilt && prevBuilt.get(p.id);
      if (prev && dirty && !dirty.has(p.id) && samePose(prev.pose, pose)) b = prev;
      else b = build(p, pose);
      built.set(p.id, b);
      state.set(p.id, 2);
      return b;
    };
    for (const p of park.pieces) visit(p);
    return built;
  }
  // a joint where a piece carries straight on from its parent (same place, slope and walls) is drawn without end faces,
  // so the two pieces read as one surface; b.joins = { start, end }
  function markJoins(park, built) {
    for (const b of built.values()) b.joins = { start: false, end: false };
    const wEq = (a, c) => a && c && Math.abs(a.h - c.h) < 0.05 && Math.abs(a.R - c.R) < 0.05;
    const lanes = new Map();          // parent id -> its split lanes' lateral spans
    for (const p of park.pieces) {
      const b = built.get(p.id), pb = p.attach && built.get(p.attach);
      if (!b || !pb) continue;
      if (pb.type === 'bowl' && pb.info.through && b.stations.length && b.segs.length && b.segs[0][0] === 0) { b.joins.start = true; continue; }
      if (b.type === 'bowl' && b.info.through && pb.stations.length && pb.segs.length) { pb.joins.end = true; continue; }
      if (!b.stations.length || !pb.stations.length || !b.segs.length || !pb.segs.length || b.segs[0][0] !== 0) continue;
      const s0 = b.stations[0], s1 = pb.stations[pb.segs[pb.segs.length - 1][1]];
      const shift = num((p.params || {}).shift, 0);
      if (shift && s1) {
        // a split lane: joined when it starts level on its parent's end and its outer edge and wall carry the parent's on
        // that side; the parent's end goes when its lanes cover its whole width
        const left = shift > 0, edge = Math.abs(shift) + s0.w / 2;
        if (Math.abs(s0.y - s1.y) > 0.05 || Math.abs(s0.a - s1.a) > 1 || Math.abs(edge - s1.w / 2) > 0.05) continue;
        if (!wEq(left ? s0.wl : s0.wr, left ? s1.wl : s1.wr) || Math.abs(s0.deck - s1.deck) > 0.05) continue;
        b.joins.start = true;
        (lanes.get(p.attach) || lanes.set(p.attach, { w: s1.w, spans: [] }).get(p.attach)).spans.push([shift - s0.w / 2, shift + s0.w / 2]);
        continue;
      }
      if (!s1 || Math.hypot(s0.x - s1.x, s0.z - s1.z, s0.y - s1.y) > 0.05 || Math.abs(s0.a - s1.a) > 1 || Math.abs(s0.w - s1.w) > 0.05) continue;
      if (!wEq(s0.wl, s1.wl) || !wEq(s0.wr, s1.wr) || Math.abs(s0.deck - s1.deck) > 0.05) continue;
      b.joins.start = true; pb.joins.end = true;
    }
    for (const [id, L] of lanes) {
      let reach = -L.w / 2;
      for (const [lo, hi] of L.spans.sort((a, c) => a[0] - c[0])) { if (lo > reach + 0.05) break; reach = Math.max(reach, hi); }
      if (reach >= L.w / 2 - 0.05) built.get(id).joins.end = true;
    }
  }
  const samePose = (a, b) => Math.abs(a.x - b.x) < 1e-6 && Math.abs(a.z - b.z) < 1e-6 && Math.abs(a.y - b.y) < 1e-6 && Math.abs(a.h - b.h) < 1e-6 && Math.abs(a.a - b.a) < 1e-6
    && JSON.stringify(a.walls || null) === JSON.stringify(b.walls || null) && JSON.stringify(a.endWalls || null) === JSON.stringify(b.endWalls || null);

  /* ------------------------------------------------------------------ meshing */
  // cross-section strips (u = lateral, + = rider's left; v = up from the floor). Each strip: [[u, v, nu, nv], ...]
  // fixed point count (1 vertical-top point + 10 arc points) whatever the wall height, so sections with walls that
  // blend from one height to another always stitch together (a changing count left holes)
  const WALL_ARC = 9;
  function wallStrip(side, w, wall, deck) {
    const sg = side === 'L' ? 1 : -1, pts = [];
    const h = Math.max(0, wall.h), R = Math.max(0.3, wall.R);
    if (h <= 0.05) {
      for (let k = 0; k <= WALL_ARC + 1; k++) pts.push([sg * w / 2, 0, 0, 1]);
      return { surf: pts, top: { u0: sg * w / 2, u1: sg * w / 2, v: 0 } };
    }
    const tmax = h >= R ? 90 : Math.acos(1 - h / R) / D2R;
    const tt = tmax * D2R;
    pts.push(h > R ? [sg * (w / 2 + R), h, -sg, 0] : [sg * (w / 2 + R * Math.sin(tt)), R - R * Math.cos(tt), -sg * Math.sin(tt), Math.cos(tt)]);
    for (let k = WALL_ARC; k >= 0; k--) {
      const t = tmax * k / WALL_ARC * D2R;
      pts.push([sg * (w / 2 + R * Math.sin(t)), R - R * Math.cos(t), -sg * Math.sin(t), Math.cos(t)]);
    }
    const uTop = sg * (w / 2 + (h >= R ? R : R * Math.sin(tt)));
    return { surf: pts, top: { u0: uTop, u1: uTop + sg * deck, v: h } };
  }
  function section(st) {
    const L = wallStrip('L', st.w, st.wl, st.deck), R = wallStrip('R', st.w, st.wr, st.deck);
    let surf = L.surf.concat([[0, 0, 0, 1]], R.surf.slice().reverse());
    let topL = L.top, topR = R.top;
    if (st.bank) {     // tilt the whole cross-section about the centreline
      const c = Math.cos(st.bank * D2R), sn = Math.sin(st.bank * D2R);
      const rot = (u, v) => [u * c - v * sn * 0, v * c + u * sn];
      surf = surf.map(([u, v, nu, nv]) => { const [a, b] = rot(u, v); return [a, b, nu * c - nv * sn, nv * c + nu * sn]; });
      if (topL) topL = { u0: topL.u0, u1: topL.u1, v: topL.v + topL.u0 * sn, v1: topL.v + topL.u1 * sn };
      if (topR) topR = { u0: topR.u0, u1: topR.u1, v: topR.v + topR.u0 * sn, v1: topR.v + topR.u1 * sn };
    }
    return { surf, topL, topR };
  }

  const COL = { ride: [0.86, 0.83, 0.77], side: [0.6, 0.58, 0.54], bottom: [0.45, 0.43, 0.4], buried: [0.86, 0.27, 0.2], steel: [0.62, 0.66, 0.7] };
  const hexRgb = h => [parseInt(h.slice(1, 3), 16) / 255, parseInt(h.slice(3, 5), 16) / 255, parseInt(h.slice(5, 7), 16) / 255];
  const mix = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];

  function speedColour(v) {
    const stops = [[0, [0.75, 0.1, 0.1]], [8, [0.9, 0.35, 0.15]], [13, [0.95, 0.75, 0.2]], [17, [0.35, 0.75, 0.35]], [24, [0.2, 0.65, 0.85]], [32, [0.35, 0.3, 0.9]]];
    for (let i = 1; i < stops.length; i++) if (v <= stops[i][0]) return mix(stops[i - 1][1], stops[i][1], (v - stops[i - 1][0]) / (stops[i][0] - stops[i - 1][0]));
    return stops[stops.length - 1][1];
  }

  /* mesh arrays for one built piece. opts: { lineColour, groundAt(x,z), speed: Float32Array|null } */
  function mesh(p, b, opts) {
    const M = { pos: [], nor: [], col: [], idx: [] };
    const lineC = hexRgb(opts.lineColour || '#888888');
    const deckC = mix(COL.ride, lineC, 0.75);
    const rideC = mix(COL.ride, lineC, 0.16);
    if (p.type === 'bowl') return bowlMesh(p, b, M, deckC, Object.assign({ rideC }, opts));
    if (p.type === 'deck') return deckMesh(p, b, M, deckC, opts);
    if (p.type === 'rail') return railMesh(p, b, M);
    const st = b.stations;
    for (let k = 0; k < b.segs.length; k++) {
      const [i0, i1] = b.segs[k];
      if (i1 <= i0) continue;
      const solid = (b.info.solidSegs || []).includes(k);
      let base = Infinity;
      for (let i = i0; i <= i1; i++) base = Math.min(base, st[i].y);
      base -= 1.0;
      const secs = [], frames = [];
      for (let i = i0; i <= i1; i++) {
        const s = st[i], h = s.h * D2R, a = Math.max(-80, Math.min(80, s.a)) * D2R;
        const fwd = [Math.cos(h), 0, Math.sin(h)], left = [Math.sin(h), 0, -Math.cos(h)];
        const up = [-Math.sin(a) * fwd[0], Math.cos(a), -Math.sin(a) * fwd[2]];
        frames.push({ s, fwd, left, up, bottom: solid ? base - s.y : -(p.type === 'run' || p.type === 'rollin' ? 0.8 : 1.5) });
        secs.push(section(s));
      }
      const vtx = (f, u, v, nu, nv, c) => {
        const s = f.s;
        M.pos.push(s.x + f.left[0] * u, s.y + v, s.z + f.left[2] * u);
        let nx = f.left[0] * nu + f.up[0] * nv, ny = f.up[1] * nv, nz = f.left[2] * nu + f.up[2] * nv;
        const l = Math.hypot(nx, ny, nz) || 1; M.nor.push(nx / l, ny / l, nz / l);
        M.col.push(c[0], c[1], c[2]);
        return M.pos.length / 3 - 1;
      };
      const strip = (getPts, colour) => {      // sweep a strip with a fixed point count across stations
        let prev = null;
        for (let j = 0; j < frames.length; j++) {
          const pts = getPts(j); if (!pts) { prev = null; continue; }
          const row = pts.map(q => vtx(frames[j], q[0], q[1], q[2], q[3], colour(j, q)));
          if (prev && prev.length === row.length) for (let m = 0; m + 1 < row.length; m++) M.idx.push(prev[m], prev[m + 1], row[m], prev[m + 1], row[m + 1], row[m]);
          prev = row;
        }
      };
      const rideCol = (j, q) => {
        const s = frames[j].s;
        if (opts.speed) { const v = opts.speed[i0 + j]; if (Number.isFinite(v)) return speedColour(v); }
        if (opts.groundAt && q[1] < 0.2) { const g = opts.groundAt(s.x + frames[j].left[0] * q[0], s.z + frames[j].left[2] * q[0]); if (g !== null && s.y + q[1] < g - 3.0) return COL.buried; }
        return rideC;
      };
      strip(j => secs[j].surf, rideCol);
      for (const side of ['topL', 'topR']) {
        // inner edge -> outer edge on the right, outer -> inner on the left: the same winding as the ride surface, so
        // both decks face up (the left one used to face down and showed dark brown)
        strip(j => { const t = secs[j][side]; if (!t) return null; const a = [t.u0, t.v, 0, 1], c = [t.u1, t.v1 ?? t.v, 0, 1]; return side === 'topL' ? [c, a] : [a, c]; }, () => deckC);
      }
      // outer sides and bottom
      const outerU = (j, sideSign) => {
        const sc = secs[j], t = sideSign > 0 ? sc.topL : sc.topR;
        if (t) return [t.u1, t.v1 ?? t.v];
        const e = sideSign > 0 ? sc.surf[0] : sc.surf[sc.surf.length - 1];
        return [e[0], e[1]];
      };
      strip(j => { const [u, v] = outerU(j, 1); return [[u, frames[j].bottom, 1, 0], [u, v, 1, 0]]; }, () => COL.side);
      strip(j => { const [u, v] = outerU(j, -1); return [[u, v, -1, 0], [u, frames[j].bottom, -1, 0]]; }, () => COL.side);
      strip(j => { const a = outerU(j, 1)[0], c = outerU(j, -1)[0]; return [[c, frames[j].bottom, 0, -1], [a, frames[j].bottom, 0, -1]]; }, () => COL.bottom);
      // end caps: vertical columns from the cross-section's top line down to the underside (an ear-clipped polygon
      // could bridge the open air between the walls when the section had repeated points)
      for (const j of [0, frames.length - 1]) {
        if (b.joins && ((j === 0 && k === 0 && b.joins.start) || (j > 0 && k === b.segs.length - 1 && b.joins.end))) continue;   // carries on into the next piece
        const sc = secs[j], f = frames[j], top = [];
        if (sc.topL) top.push([sc.topL.u1, sc.topL.v1 ?? sc.topL.v]);
        for (const q of sc.surf) top.push([q[0], q[1]]);
        if (sc.topR) top.push([sc.topR.u1, sc.topR.v1 ?? sc.topR.v]);
        const sgn = j === 0 ? -1 : 1;
        const put = (u, v) => { M.pos.push(f.s.x + f.left[0] * u, f.s.y + v, f.s.z + f.left[2] * u); M.nor.push(f.fwd[0] * sgn, 0, f.fwd[2] * sgn); M.col.push(...COL.side); return M.pos.length / 3 - 1; };
        for (let k = 0; k + 1 < top.length; k++) {
          const [ua, va] = top[k], [ub, vb] = top[k + 1];
          if (Math.abs(ua - ub) < 1e-4) continue;          // vertical wall face: no area in this view
          const a = put(ua, va), b2 = put(ub, vb), c = put(ub, f.bottom), d = put(ua, f.bottom);
          if (sgn > 0) M.idx.push(a, b2, c, a, c, d); else M.idx.push(a, c, b2, a, d, c);
        }
      }
    }
    if (p.type === 'jump' && getp(p, 'rail') && b.info.knuckle) {
      const l = b.info.lip, k = b.info.knuckle, s0 = b.stations[l.i];
      const pts = [];
      for (let i = 0; i <= 24; i++) { const t = i / 24, d = l.d + (k.d - l.d) * t; pts.push([s0.x + (d - l.d) * Math.cos(s0.h * D2R), l.y + (k.y - l.y) * t + 0.5 + Math.sin(Math.PI * t) * Math.max(2, (k.d - l.d) * 0.08), s0.z + (d - l.d) * Math.sin(s0.h * D2R)]); }
      tube(M, pts, 0.18, COL.steel);
    }
    return M;
  }

  function tube(M, pts, r, c) {
    const n = 8; let prev = null;
    for (let i = 0; i < pts.length; i++) {
      const a = pts[Math.max(0, i - 1)], b = pts[Math.min(pts.length - 1, i + 1)];
      let t = [b[0] - a[0], b[1] - a[1], b[2] - a[2]]; const tl = Math.hypot(...t) || 1; t = t.map(v => v / tl);
      let u = [-t[2], 0, t[0]]; const ul = Math.hypot(...u) || 1; u = u.map(v => v / ul);
      const w = [t[1] * u[2] - t[2] * u[1], t[2] * u[0] - t[0] * u[2], t[0] * u[1] - t[1] * u[0]];
      const row = [];
      for (let k = 0; k < n; k++) {
        const an = k / n * 2 * Math.PI, nx = Math.cos(an) * u[0] + Math.sin(an) * w[0], ny = Math.cos(an) * u[1] + Math.sin(an) * w[1], nz = Math.cos(an) * u[2] + Math.sin(an) * w[2];
        M.pos.push(pts[i][0] + r * nx, pts[i][1] + r * ny, pts[i][2] + r * nz); M.nor.push(nx, ny, nz); M.col.push(...c); row.push(M.pos.length / 3 - 1);
      }
      if (prev) for (let k = 0; k < n; k++) { const k1 = (k + 1) % n; M.idx.push(prev[k], prev[k1], row[k], prev[k1], row[k1], row[k]); }
      prev = row;
    }
  }

  function railMesh(p, b, M) {
    const L = num(getp(p, 'len'), 30), rise = num(getp(p, 'rise'), 4), h = b.pose.h * D2R, pts = [];
    for (let i = 0; i <= 32; i++) { const t = i / 32; pts.push([b.pose.x + L * t * Math.cos(h), b.pose.y + rise * Math.sin(Math.PI * t), b.pose.z + L * t * Math.sin(h)]); }
    tube(M, pts, 0.2, [0.85, 0.3, 0.25]);
    return M;
  }

  function boxMesh(M, cx, cz, h, len, wid, yTop, yBot, cTop, cSide) {
    const ch = Math.cos(h * D2R), sh = Math.sin(h * D2R);
    const P = (a, b, y) => [cx + a * ch - b * sh, y, cz + a * sh + b * ch];
    const c = [[-len / 2, -wid / 2], [len / 2, -wid / 2], [len / 2, wid / 2], [-len / 2, wid / 2]];
    const quad = (A, B, C, D, n, col) => { const i = M.pos.length / 3; for (const q of [A, B, C, D]) { M.pos.push(...q); M.nor.push(...n); M.col.push(...col); } M.idx.push(i, i + 2, i + 1, i, i + 3, i + 2); };
    quad(P(...c[0], yTop), P(...c[1], yTop), P(...c[2], yTop), P(...c[3], yTop), [0, 1, 0], cTop);
    for (let k = 0; k < 4; k++) {
      const a = c[k], bb = c[(k + 1) % 4];
      const mx = (a[0] + bb[0]) / 2, mz = (a[1] + bb[1]) / 2, l = Math.hypot(mx, mz) || 1;
      const n = [(mx * ch - mz * sh) / l, 0, (mx * sh + mz * ch) / l];
      quad(P(...a, yBot), P(...bb, yBot), P(...bb, yTop), P(...a, yTop), n, cSide);
    }
  }

  function deckMesh(p, b, M, deckC, opts) {
    const outline = getp(p, 'outline');
    if (outline && outline.length >= 3) {      // free-form platform / island: the outline extruded down by its thickness
      // an outline point may carry its own top and underside heights ([u, v, top, under], relative to y), so an infill
      // between pieces meets each neighbour's deck and underside exactly
      const poly = bowlOutlineWorld(p, b), th = num(getp(p, 'thick'), 2);
      const yT = outline.map(q => b.pose.y + (q.length > 2 ? +q[2] : 0)), yB = outline.map((q, i) => q.length > 3 ? b.pose.y + +q[3] : yT[i] - th);
      const area = poly.reduce((s2, a, i) => { const c = poly[(i + 1) % poly.length]; return s2 + a[0] * c[1] - c[0] * a[1]; }, 0), sgn = area > 0 ? 1 : -1;
      const tris = triangulate(poly);
      const face = (ia, ib, ic, ys, up, col) => {      // one flat-shaded triangle, normal turned to face up (or down)
        const A = [poly[ia][0], ys[ia], poly[ia][1]], B = [poly[ib][0], ys[ib], poly[ib][1]], C = [poly[ic][0], ys[ic], poly[ic][1]];
        const e1 = [B[0] - A[0], B[1] - A[1], B[2] - A[2]], e2 = [C[0] - A[0], C[1] - A[1], C[2] - A[2]];
        let n = [e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0]];
        const l = Math.hypot(...n) || 1, flip = (n[1] < 0) === up; n = n.map(v => v / l * (flip ? -1 : 1));
        const k = M.pos.length / 3;
        for (const q of [A, B, C]) { M.pos.push(...q); M.nor.push(...n); M.col.push(...col); }
        if (flip) M.idx.push(k, k + 2, k + 1); else M.idx.push(k, k + 1, k + 2);
      };
      {   // top: shared vertices with smoothed normals (a flat top stays exactly flat; a ramp shades without facets)
        const nrm = poly.map(() => [0, 0, 0]), tw = [];
        for (const t of tris) {
          const [ia, ib, ic] = t, A = [poly[ia][0], yT[ia], poly[ia][1]], B = [poly[ib][0], yT[ib], poly[ib][1]], C = [poly[ic][0], yT[ic], poly[ic][1]];
          const e1 = [B[0] - A[0], B[1] - A[1], B[2] - A[2]], e2 = [C[0] - A[0], C[1] - A[1], C[2] - A[2]];
          let n = [e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0]];
          const flip = n[1] < 0; if (flip) n = n.map(v => -v);
          for (const i of t) { nrm[i][0] += n[0]; nrm[i][1] += n[1]; nrm[i][2] += n[2]; }
          tw.push(flip ? [ia, ic, ib] : [ia, ib, ic]);
        }
        const top = poly.map((q, i) => { const l = Math.hypot(...nrm[i]) || 1; M.pos.push(q[0], yT[i], q[1]); M.nor.push(nrm[i][0] / l, nrm[i][1] / l, nrm[i][2] / l); M.col.push(...deckC); return M.pos.length / 3 - 1; });
        for (const t of tw) M.idx.push(top[t[0]], top[t[1]], top[t[2]]);
      }
      for (const t of tris) face(t[0], t[1], t[2], yB, false, COL.bottom);
      for (let i = 0; i < poly.length; i++) {
        const j = (i + 1) % poly.length, a = poly[i], c = poly[j], nx = (c[1] - a[1]) * -sgn, nz = (a[0] - c[0]) * -sgn, l = Math.hypot(nx, nz) || 1, k = M.pos.length / 3;
        for (const q of [[a[0], yT[i], a[1]], [c[0], yT[j], c[1]], [c[0], yB[j], c[1]], [a[0], yB[i], a[1]]]) { M.pos.push(...q); M.nor.push(nx / l, 0, nz / l); M.col.push(...COL.side); }
        M.idx.push(k, k + 2, k + 1, k, k + 3, k + 2);
      }
      return M;
    }
    const len = num(getp(p, 'len'), 20), wid = num(getp(p, 'width'), 20), th = num(getp(p, 'thick'), 2);
    let yBot = b.pose.y - th;
    if (getp(p, 'solid') && opts.groundAt) {
      let g = Infinity; const ch = Math.cos(b.pose.h * D2R), sh = Math.sin(b.pose.h * D2R);
      for (const [a, c] of [[-1, -1], [1, -1], [1, 1], [-1, 1], [0, 0]]) { const gg = opts.groundAt(b.pose.x + a * len / 2 * ch - c * wid / 2 * sh, b.pose.z + a * len / 2 * sh + c * wid / 2 * ch); if (gg !== null) g = Math.min(g, gg); }
      if (Number.isFinite(g)) yBot = Math.min(yBot, g - 1);
    }
    boxMesh(M, b.pose.x, b.pose.z, b.pose.h, len, wid, b.pose.y, yBot, deckC, COL.side);
    return M;
  }

  /* bowl: outline = coping line (local coords, rotated by heading about the piece position); y = floor */
  // where the local +u axis (the flow direction) leaves the outline on the far side
  function bowlExitU(p) {
    const o = getp(p, 'outline') || []; let best = 0;
    for (let i = 0; i < o.length; i++) {
      const a = o[i], c = o[(i + 1) % o.length];
      if ((a[1] > 0) !== (c[1] > 0)) best = Math.max(best, a[0] + (0 - a[1]) * (c[0] - a[0]) / (c[1] - a[1]));
    }
    return best || Math.max(0, ...o.map(q => q[0]));
  }
  function bowlOutlineWorld(p, b) {
    const h = b.pose.h * D2R, ch = Math.cos(h), sh = Math.sin(h);
    return ((b.info && b.info.outline) || getp(p, 'outline') || []).map(([u, v]) => [b.pose.x + u * ch - v * sh, b.pose.z + u * sh + v * ch]);
  }
  function offsetPoly(poly, d) {      // inward offset by d (positive = inward)
    const n = poly.length; let area = 0;
    for (let i = 0; i < n; i++) { const a = poly[i], c = poly[(i + 1) % n]; area += a[0] * c[1] - c[0] * a[1]; }
    const sgn = area > 0 ? 1 : -1;
    return poly.map((pt, i) => {
      const a = poly[(i - 1 + n) % n], c = poly[(i + 1) % n];
      let e1 = [pt[0] - a[0], pt[1] - a[1]], e2 = [c[0] - pt[0], c[1] - pt[1]];
      const l1 = Math.hypot(...e1) || 1, l2 = Math.hypot(...e2) || 1; e1 = [e1[0] / l1, e1[1] / l1]; e2 = [e2[0] / l2, e2[1] / l2];
      const n1 = [-e1[1] * sgn, e1[0] * sgn], n2 = [-e2[1] * sgn, e2[0] * sgn];
      let m = [n1[0] + n2[0], n1[1] + n2[1]]; const ml = Math.hypot(...m) || 1; m = [m[0] / ml, m[1] / ml];
      const cosh = Math.max(0.5, m[0] * n1[0] + m[1] * n1[1]);
      return [pt[0] + m[0] * d / cosh, pt[1] + m[1] * d / cosh];
    });
  }
  // inward unit directions (with mitre scale) per outline vertex; a flow bowl's mouth corners offset straight
  // across along their side wall, so the neck walls end flush with the opening
  function offsetDirs(poly, mouthEdges) {
    const n = poly.length; let area = 0;
    for (let i = 0; i < n; i++) { const a = poly[i], c = poly[(i + 1) % n]; area += a[0] * c[1] - c[0] * a[1]; }
    const sgn = area > 0 ? 1 : -1, ME = new Set(mouthEdges || []);
    const nrm = i => { const a = poly[i], c = poly[(i + 1) % n], l = Math.hypot(c[0] - a[0], c[1] - a[1]) || 1; return [-(c[1] - a[1]) / l * sgn, (c[0] - a[0]) / l * sgn]; };
    return poly.map((pt, i) => {
      const ip = (i - 1 + n) % n;
      if (ME.has(ip)) return { d: nrm(i), s: 1 };     // edge before is an opening: follow the next side
      if (ME.has(i)) return { d: nrm(ip), s: 1 };     // edge after is an opening
      const n1 = nrm(ip), n2 = nrm(i);
      let m = [n1[0] + n2[0], n1[1] + n2[1]]; const ml = Math.hypot(...m) || 1; m = [m[0] / ml, m[1] / ml];
      return { d: m, s: 1 / Math.max(0.5, m[0] * n1[0] + m[1] * n1[1]) };
    });
  }
  const offsetBy = (poly, dirs, off) => poly.map((pt, i) => { const o = typeof off === 'number' ? off : off[i]; return [pt[0] + dirs[i].d[0] * o * dirs[i].s, pt[1] + dirs[i].d[1] * o * dirs[i].s]; });

  /* a pool bowl's wall per outline vertex. params.ext = { at: [u, v], half, blend, h, R } raises a stretch of the wall
     (a vert extension, e.g. where a line lands into the bowl): full height for `half` metres either side of the point
     nearest `at` (measured along the coping), easing back to the bowl's own wall over `blend` metres. */
  /* a pool bowl's floor depth below its pose (local [u, v]): params.deep = { from: [u, v], to: [u, v], depth } sinks the
     floor by `depth`, easing in (smoothstep) from `from` to `to` and staying full depth beyond, e.g. deeper pockets. */
  function bowlDepth(p) {
    const e = p.params && p.params.deep;
    if (!e || !Array.isArray(e.from) || !Array.isArray(e.to) || !(num(e.depth, 0) > 0)) return null;
    const ax = e.to[0] - e.from[0], az = e.to[1] - e.from[1], L2 = ax * ax + az * az || 1, D = num(e.depth, 0);
    return (u, v) => { const t = clamp(((u - e.from[0]) * ax + (v - e.from[1]) * az) / L2, 0, 1); return D * t * t * (3 - 2 * t); };
  }
  function bowlWalls(p) {
    const w = bowlWallsOwn(p), dep = bowlDepth(p), o = getp(p, 'outline') || [];
    if (!dep) return w;
    // a deeper floor keeps the coping level: the wall grows by the depth (radius too, so the vert stays the same)
    return w.map((x, i) => { const d = dep(o[i][0], o[i][1]); return { ...x, h: x.h + d, R: x.R + d, dep: d }; });
  }
  function bowlWallsOwn(p) {
    const o = getp(p, 'outline') || [], H = num(getp(p, 'wall_h'), 3), RB = Math.max(0.3, num(getp(p, 'wall_R'), 2.5)), DK = num(getp(p, 'deck'), 2);
    const e = p.params && p.params.ext;
    if (!e || !Array.isArray(e.at) || o.length < 3) return o.map(() => ({ h: H, R: RB, deck: DK }));
    const n = o.length, acc = [0]; for (let i = 1; i < n; i++) acc.push(acc[i - 1] + Math.hypot(o[i][0] - o[i - 1][0], o[i][1] - o[i - 1][1]));
    const per = acc[n - 1] + Math.hypot(o[0][0] - o[n - 1][0], o[0][1] - o[n - 1][1]);
    let k = 0, bd = Infinity; o.forEach((q, i) => { const d = Math.hypot(q[0] - e.at[0], q[1] - e.at[1]); if (d < bd) { bd = d; k = i; } });
    const half = num(e.half, 6), blend = Math.max(0.5, num(e.blend, 10)), EH = num(e.h, H), ER = Math.max(0.3, num(e.R, RB));
    return o.map((q, i) => {
      let d = Math.abs(acc[i] - acc[k]); d = Math.min(d, per - d);
      const x = clamp((d - half) / blend, 0, 1), s = 1 - x * x * (3 - 2 * x);
      return { h: H + (EH - H) * s, R: RB + (ER - RB) * s, deck: DK };
    });
  }
  /* a floor whose height varies (fAt): a 3 m grid clipped to the floor outline F ([x, z, y] per vertex, the walls' feet),
     so it meets every wall foot exactly and follows fAt inside */
  function heightFloor(M, F, fAt, colour) {
    const G = 3, xs = F.map(q => q[0]), zs = F.map(q => q[1]), X0 = Math.floor(Math.min(...xs) / G) * G, Z0 = Math.floor(Math.min(...zs) / G) * G;
    const X1 = Math.max(...xs), Z1 = Math.max(...zs), nrm = (x, z) => { const e = 0.5, gx = (fAt(x + e, z) - fAt(x - e, z)) / (2 * e), gz = (fAt(x, z + e) - fAt(x, z - e)) / (2 * e), l = Math.hypot(gx, 1, gz); return [-gx / l, 1 / l, -gz / l]; };
    const clip = (P, k, c, keepGreater) => {       // Sutherland–Hodgman against x (k = 0) or z (k = 2) = c, heights carried
      const out = [];
      for (let i = 0; i < P.length; i++) { const a = P[i], q = P[(i + 1) % P.length], ia = keepGreater ? a[k] >= c : a[k] <= c, iq = keepGreater ? q[k] >= c : q[k] <= c;
        if (ia) out.push(a);
        if (ia !== iq) { const t = (c - a[k]) / (q[k] - a[k]); out.push([a[0] + (q[0] - a[0]) * t, a[1] + (q[1] - a[1]) * t, a[2] + (q[2] - a[2]) * t]); } }
      return out;
    };
    const S = F.map(q => [q[0], q[2], q[1]]);       // [x, y, z]
    for (let X = X0; X < X1; X += G) for (let Z = Z0; Z < Z1; Z += G) {
      let P = clip(clip(clip(clip(S, 0, X, true), 0, X + G, false), 2, Z, true), 2, Z + G, false);
      if (P.length < 3) continue;
      // a cell corner takes the field's height, so neighbouring cells share it
      P = P.map(q => ((Math.abs(q[0] - X) < 1e-6 || Math.abs(q[0] - X - G) < 1e-6) && (Math.abs(q[2] - Z) < 1e-6 || Math.abs(q[2] - Z - G) < 1e-6)) ? [q[0], fAt(q[0], q[2]), q[2]] : q);
      const tris = triangulate(P.map(q => [q[0], q[2]])); if (!tris.length) continue;
      const ids = P.map(q => { M.pos.push(q[0], q[1], q[2]); M.nor.push(...nrm(q[0], q[2])); M.col.push(...colour); return M.pos.length / 3 - 1; });
      for (const t of tris) M.idx.push(ids[t[0]], ids[t[2]], ids[t[1]]);
    }
  }
  /* a spine in a pool bowl: { a: [u, v], b: [u, v], h, R } (local, like the outline): two transitions back to back along a-b,
     with a flat 0.6 m coping top and rounded ends (an end that stands free in the bowl rides like a hip) */
  function spineMesh(M, b, sp, fAt, rideC, topC, wallR, wallH) {
    if (!Array.isArray(sp.a) || !Array.isArray(sp.b)) return;
    const h = b.pose.h * D2R, ch = Math.cos(h), sh = Math.sin(h), W = (u, v) => [b.pose.x + u * ch - v * sh, b.pose.z + u * sh + v * ch];
    const A = W(...sp.a), B = W(...sp.b), H = Math.max(0.5, num(sp.h, 6)), R = Math.max(0.5, num(sp.R, 6)), c = 0.3;
    const hd = Math.atan2(B[1] - A[1], B[0] - A[0]), N = 14, tmax = H >= R ? Math.PI / 2 : Math.acos(1 - H / R), c0 = R - R * Math.sin(tmax);
    // A spine that ends at the bowl wall runs into it: extend that cap the blend length
    // past its b end, so its free vertical face is buried in the wall instead of
    // standing a metre short of it. The cap top is held at the wall coping height.
    const blend = Math.max(0, num(sp.end_blend_m, 1.6)), far = Math.hypot(B[0] - b.pose.x, B[1] - b.pose.z);
    const into = !!(wallR && wallH && blend && far > wallR - 10);
    const ax = Math.cos(hd), az = Math.sin(hd);
    const Bc = into ? [B[0] + ax * blend, B[1] + az * blend] : B;
    const dirs = [];        // around the capsule: the B end (-90°..90° off the axis), then the A end (90°..270°)
    for (let j = 0; j <= N; j++) dirs.push([Bc, hd - Math.PI / 2 + Math.PI * j / N, into]);
    for (let j = 0; j <= N; j++) dirs.push([A, hd + Math.PI / 2 + Math.PI * j / N, false]);
    const NA = 10, rings = [[c, H, 0, 1, topC]];        // [offset from the axis, height above the floor, nOut, nUp, colour]
    if (H > R) rings.push([c, H, 1, 0, rideC], [c, R, 1, 0, rideC]); else rings.push([c + c0, H, Math.sin(tmax), Math.cos(tmax), rideC]);
    for (let k = 1; k <= NA; k++) { const t = tmax * (1 - k / NA); rings.push([c + R - R * Math.sin(t), R - R * Math.cos(t), Math.sin(t), Math.cos(t), rideC]); }
    rings[rings.length - 1][1] -= 0.003;                  // bury the foot: its rim on the floor made a T-junction
    const row = ([off, y, no, nu, col]) => dirs.map(([P0, a, wallEnd]) => { const x = P0[0] + Math.cos(a) * off, z = P0[1] + Math.sin(a) * off;
      const yy = wallEnd ? Math.min(y, wallH - 0.02) : y;
      M.pos.push(x, fAt(x, z) + yy, z); M.nor.push(Math.cos(a) * no, nu, Math.sin(a) * no); M.col.push(...col); return M.pos.length / 3 - 1; });
    const top = row(rings[0]), n = dirs.length;
    for (const t of triangulate(dirs.map(([P0, a]) => [P0[0] + Math.cos(a) * c, P0[1] + Math.sin(a) * c]))) M.idx.push(top[t[0]], top[t[2]], top[t[1]]);
    let prev = row(rings[1]);
    for (let k = 2; k < rings.length; k++) { const cur = row(rings[k]);
      for (let j = 0; j < n; j++) { const q = (j + 1) % n; M.idx.push(prev[j], prev[q], cur[j], prev[q], cur[q], cur[j]); }
      prev = cur; }
  }
  function bowlMesh(p, b, M, deckC, opts) {
    const poly = bowlOutlineWorld(p, b);
    if (poly.length < 3) return M;
    const rout = Math.max(...poly.map(q => Math.hypot(q[0] - b.pose.x, q[1] - b.pose.z)));
    const n = poly.length, y0 = b.pose.y, mouthEdges = b.info.mouthEdges || [], ME = new Set(mouthEdges);
    const dirs = offsetDirs(poly, mouthEdges);
    // per-vertex wall: a flow bowl blends from the runway's walls in the necks to the bowl wall around the round part
    const H = num(getp(p, 'wall_h'), 3), RB = Math.max(0.3, num(getp(p, 'wall_R'), 2.5)), DK = num(getp(p, 'deck'), 2);
    const own = b.info.wallAt && b.info.wallAt.length === poly.length ? b.info.wallAt : null;
    const wall = poly.map((q, i) => {
      const nw = b.info.neck && b.info.neck[i];
      if (!nw) return own ? own[i] : { h: H, R: RB, deck: DK };
      const s = nw.s;   // 0 = runway wall, 1 = bowl wall
      return { h: nw.h + (H - nw.h) * s, R: Math.max(0.3, nw.R + (RB - nw.R) * s), deck: nw.deck + (DK - nw.deck) * s };
    });
    const NA = 9, rideC = opts.rideC || COL.ride;   // arc steps; the ride surface takes the line's tint like the runways
    const ringAt = (i, r) => {          // [off, y, nIn, nUp, colour] of ring r at vertex i
      // a wall lower than its radius ends its arc a little inside the outline (c0), exactly where a runway's would
      const { h, R, deck } = wall[i], tmax = h >= R ? Math.PI / 2 : Math.acos(1 - h / R), c0 = R - R * Math.sin(tmax), yb = y0 - (wall[i].dep || 0);
      if (r === 0) return [c0 - deck, yb + h, 0, 1, deckC];
      if (r === 1) return [c0, yb + h, 0, 1, deckC];
      if (r === 2) return [c0, yb + h, h > R ? 1 : 0, h > R ? 0 : 1, rideC];
      const t = tmax * (1 - (r - 3) / NA);
      return [R - R * Math.sin(t), yb + R - R * Math.cos(t), Math.sin(t), Math.cos(t), rideC];
    };
    const area = poly.reduce((s, a, i) => { const c = poly[(i + 1) % n]; return s + a[0] * c[1] - c[0] * a[1]; }, 0), sgn = area > 0 ? 1 : -1;
    let prev = null;
    for (let r = 0; r < 3 + NA + 1; r++) {
      const row = poly.map((q, i) => {
        const [off, y, nin, nup, c] = ringAt(i, r), dd = dirs[i];
        M.pos.push(q[0] + dd.d[0] * off * dd.s, y, q[1] + dd.d[1] * off * dd.s);
        const L = Math.hypot(nin, nup) || 1; M.nor.push(dd.d[0] * nin / L, nup / L, dd.d[1] * nin / L); M.col.push(...c);
        return M.pos.length / 3 - 1;
      });
      if (prev) for (let i = 0; i < n; i++) {
        if (ME.has(i)) continue;       // opening onto a runway
        const j = (i + 1) % n;
        if (sgn > 0) M.idx.push(prev[i], row[i], prev[j], prev[j], row[i], row[j]); else M.idx.push(prev[i], prev[j], row[i], prev[j], row[j], row[i]);
      }
      prev = row;
    }
    // floor
    // (a mouth edge gets its midpoint, the runway floor's centreline vertex, so the two floors share every vertex)
    const floor = [];
    offsetBy(poly, dirs, wall.map(w => w.R)).forEach((q, i, F) => { floor.push(q); if (ME.has(i)) { const c = F[(i + 1) % F.length]; floor.push([(q[0] + c[0]) / 2, (q[1] + c[1]) / 2]); } });
    const dep = !b.info.through && bowlDepth(p);
    if (dep) {
      const h = b.pose.h * D2R, ch = Math.cos(h), sh = Math.sin(h);
      const fAt = (x, z) => { const dx = x - b.pose.x, dz = z - b.pose.z; return y0 - dep(dx * ch + dz * sh, -dx * sh + dz * ch); };
      heightFloor(M, floor.map((q, i) => [q[0], q[1], y0 - (wall[i].dep || 0)]), fAt, rideC);
      for (const sp of getp(p, 'spines') || []) spineMesh(M, b, sp, fAt, rideC, deckC, rout, H);
    } else {
      const ids = floor.map(q => { M.pos.push(q[0], y0, q[1]); M.nor.push(0, 1, 0); M.col.push(...rideC); return M.pos.length / 3 - 1; });
      for (const t of triangulate(floor)) M.idx.push(ids[t[0]], ids[t[2]], ids[t[1]]);   // triangulate() is CCW in (x, z) for either outline direction: this faces up
      if (!b.info.through) for (const sp of getp(p, 'spines') || []) spineMesh(M, b, sp, () => y0, rideC, deckC, rout, H);
    }
    // outer skirt: a flow bowl has the runways' 0.8 m underside (flush with them); an in-ground bowl goes below the cut ground (floor − 3 m)
    const thin = !!b.info.through;
    const out = offsetBy(poly, dirs, wall.map(w => (w.h >= w.R ? 0 : w.R - w.R * Math.sin(Math.acos(1 - w.h / w.R))) - w.deck)), bot = y0 - (thin ? 0.8 : 3.5 + Math.max(0, ...wall.map(w => w.dep || 0)));
    if (thin) {        // underside, facing down
      const bids = out.map(q => { M.pos.push(q[0], bot, q[1]); M.nor.push(0, -1, 0); M.col.push(...COL.bottom); return M.pos.length / 3 - 1; });
      for (const t of triangulate(out)) M.idx.push(bids[t[0]], bids[t[1]], bids[t[2]]);
    }
    // its top is the deck's outer edge (ringAt r 0: a deep pocket's wall stands on its lowered floor, y0 - dep)
    const deckY = i => y0 - (wall[i].dep || 0) + wall[i].h;
    for (let i = 0; i < n; i++) {
      if (ME.has(i)) continue;
      const j = (i + 1) % n, a = out[i], c = out[j];
      const nx = (c[1] - a[1]) * -sgn, nz = (a[0] - c[0]) * -sgn, l = Math.hypot(nx, nz) || 1;
      const k = M.pos.length / 3;
      for (const q of [[a[0], deckY(i), a[1]], [c[0], deckY(j), c[1]], [c[0], bot, c[1]], [a[0], bot, a[1]]]) { M.pos.push(...q); M.nor.push(nx / l, 0, nz / l); M.col.push(...COL.side); }
      M.idx.push(k, k + 2, k + 1, k, k + 3, k + 2);
    }
    return M;
  }

  /* flow bowl outline (local u forward, v to the rider's right): a short neck as wide as the runway at each end, a round
     flare (an arc of radius `flare` tangent to the runway wall and to the bowl) and the round bowl of diameter `size`.
     The wall height and radius rise along the flare from the runway's walls to the bowl's. */
  function keyholeOutline(fw, W, size, flare, WX) {
    WX = WX || W;
    const Rn = Math.max(W.wl.R, W.wr.R, WX.wl.R, WX.wr.R), a = fw / 2 + Rn;
    const r = Math.max(a + 2, size / 2), rf = Math.max(2, flare), uf = 1.5;
    const c = uf + Math.sqrt(Math.max(0, (r + rf) ** 2 - (a + rf) ** 2)), Lt = 2 * c;
    const t2u = c + (uf - c) * r / (r + rf);            // where the flare meets the bowl circle
    const vAt = u => {
      const x = u <= c ? u : Lt - u;
      if (x <= uf) return a;
      if (x <= t2u) return a + rf - Math.sqrt(Math.max(0, rf * rf - (x - uf) ** 2));
      return Math.sqrt(Math.max(0, r * r - (x - c) ** 2));
    };
    // fine samples, then even spacing along the coping line (~1.5 m)
    const fine = []; for (let u = 0; u < Lt - 0.05; u += 0.1) fine.push([u, vAt(u)]);
    fine.push([Lt, vAt(Lt)]);          // the exit mouth exactly at Lt, where the next runway starts (no crack)
    const side = [fine[0]]; let acc = 0;
    for (let i = 1; i < fine.length; i++) { acc += Math.hypot(fine[i][0] - fine[i - 1][0], fine[i][1] - fine[i - 1][1]); if (acc >= 1.5 || i === fine.length - 1) { side.push(fine[i]); acc = 0; } }
    const top = side, bot = side.slice().reverse().map(([u, v]) => [u, -v]);
    const outline = top.concat(bot);   // full precision: the mouths meet the runways' sections exactly
    const m = top.length - 1;          // exit opening: edge m (top end -> bottom end); entry opening: last edge (closing)
    // each neck vertex starts from its own runway's wall on its own side (v > 0 is the rider's right)
    const neck = outline.map(([u, v]) => {
      const x = u <= c ? u : Lt - u, t = clamp((x - uf) / Math.max(1, t2u - uf + 6), 0, 1), sd = (u <= c ? W : WX)[v > 0 ? 'wr' : 'wl'];
      return { h: sd.h, R: Rn, deck: W.deck, s: t * t * (3 - 2 * t) };
    });
    return { outline, mouthEdges: [m, outline.length - 1], neck, Lt };
  }

  const minAngle = (a, b, c) => {
    const ang = (p, q, r) => { const u = [q[0] - p[0], q[1] - p[1]], v = [r[0] - p[0], r[1] - p[1]]; return Math.acos(clamp((u[0] * v[0] + u[1] * v[1]) / ((Math.hypot(...u) * Math.hypot(...v)) || 1), -1, 1)); };
    return Math.min(ang(a, b, c), ang(b, c, a), ang(c, a, b));
  };
  /* ear clipping for simple polygons [[u,v]...] -> [[i,j,k]] */
  function triangulate(poly) {
    const n = poly.length; if (n < 3) return [];
    let area = 0; for (let i = 0; i < n; i++) { const a = poly[i], b = poly[(i + 1) % n]; area += a[0] * b[1] - b[0] * a[1]; }
    const idx = []; for (let i = 0; i < n; i++) idx.push(area > 0 ? i : n - 1 - i);
    const out = []; let guard = 0;
    const cross = (a, b, c) => (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
    const inside = (p, a, b, c) => cross(a, b, p) >= 0 && cross(b, c, p) >= 0 && cross(c, a, p) >= 0;
    while (idx.length > 3 && guard++ < 5000) {
      let cut = false;
      // clip the best-shaped ear (largest smallest angle): no long slivers, so heights interpolate cleanly across a strip
      let best = -1, bestQ = -1;
      for (let i = 0; i < idx.length; i++) {
        const i0 = idx[(i - 1 + idx.length) % idx.length], i1 = idx[i], i2 = idx[(i + 1) % idx.length];
        const a = poly[i0], b = poly[i1], c = poly[i2];
        if (cross(a, b, c) <= 1e-9) continue;
        let ok = true;
        for (const j of idx) { if (j === i0 || j === i1 || j === i2) continue; if (inside(poly[j], a, b, c)) { ok = false; break; } }
        if (!ok) continue;
        const q = minAngle(a, b, c);
        if (q > bestQ) { bestQ = q; best = i; }
      }
      if (best >= 0) {
        const i = best;
        out.push([idx[(i - 1 + idx.length) % idx.length], idx[i], idx[(i + 1) % idx.length]]); idx.splice(i, 1); cut = true;
      }
      if (!cut) { // degenerate: fan the rest
        for (let i = 1; i + 1 < idx.length; i++) out.push([idx[0], idx[i], idx[i + 1]]);
        return out;
      }
    }
    if (idx.length === 3) out.push([idx[0], idx[1], idx[2]]);
    return out;
  }

  /* ------------------------------------------------------------------ ride physics along routes */
  /* ground cuts. A bowl is an in-ground pool: the ground inside its coping line (+1 m) is removed down to 3 m below its floor.
     A piece with params.dig cuts a trench: flat under the riding width (+1.5 m), then 45° side slopes up to the ground.
     H is a cell-centred height grid {x0, z0, G, nx, nz} (native y); returns a carved copy. The build uses the same rule. */
  function carveGround(park, built, H, g) {
    const out = Float32Array.from(H);
    const cells = (xa, za, xb, zb, fn) => {
      const i0 = Math.max(0, Math.floor((xa - g.x0) / g.G)), i1 = Math.min(g.nx - 1, Math.ceil((xb - g.x0) / g.G));
      const j0 = Math.max(0, Math.floor((za - g.z0) / g.G)), j1 = Math.min(g.nz - 1, Math.ceil((zb - g.z0) / g.G));
      for (let j = j0; j <= j1; j++) for (let i = i0; i <= i1; i++) fn(j * g.nx + i, g.x0 + (i + 0.5) * g.G, g.z0 + (j + 0.5) * g.G);
    };
    for (const p of park.pieces) {
      const b = built.get(p.id); if (!b) continue;
      if (p.type === 'bowl') {
        const poly = bowlOutlineWorld(p, b); if (poly.length < 3) continue;
        // 3 m under the floor (no shimmer between the two surfaces) and 1 m past the coping (hidden by the bowl's outer skirt)
        const xs = poly.map(q => q[0]), zs = poly.map(q => q[1]), floor = b.pose.y - 3 - Math.max(0, num(p.params && p.params.deep && p.params.deep.depth, 0)), M = 1;
        const nearEdge = (x, z) => poly.some((a, i) => { const c = poly[(i + 1) % poly.length], dx = c[0] - a[0], dz = c[1] - a[1], L2 = dx * dx + dz * dz || 1;
          const t = Math.max(0, Math.min(1, ((x - a[0]) * dx + (z - a[1]) * dz) / L2)); return Math.hypot(x - a[0] - t * dx, z - a[1] - t * dz) < M; });
        cells(Math.min(...xs) - M, Math.min(...zs) - M, Math.max(...xs) + M, Math.max(...zs) + M, (k, x, z) => { if (out[k] > floor && (pointInPoly(x, z, poly) || nearEdge(x, z))) out[k] = floor; });
      } else if (getp(p, 'dig') && b.stations.length) {
        // a cutting: under the floor, just below each deck top out past the deck edge, then a 40° bank
        const edge = wl => { const h = Math.max(0, num(wl && wl.h, 0)), R = Math.max(0.3, num(wl && wl.R, 1)); return { h, e: h >= R ? R : R * Math.sin(Math.acos(1 - h / R)) }; };
        for (const st of b.stations) {
          const hw = (st.w || 8) / 2, floor = st.y - 0.3, L = edge(st.wl), Rt = edge(st.wr), dk = 1.5;
          const sh = Math.sin(st.h * D2R), ch = Math.cos(st.h * D2R), reach = hw + Math.max(L.e, Rt.e) + dk + 60;
          cells(st.x - reach, st.z - reach, st.x + reach, st.z + reach, (k, x, z) => {
            const d = Math.hypot(x - st.x, z - st.z), side = (x - st.x) * sh - (z - st.z) * ch > 0 ? L : Rt;
            // floor level under the whole footprint (floor, walls, deck: the grid blends neighbouring cells, so
            // anything higher would show through the wall's transition), deck height just past the deck edge
            const dd = hw + side.e + num(st.deck, 1.5), de = dd + dk, top = st.y + side.h - 0.3;
            const t = d <= dd ? floor : d <= de ? Math.max(floor, top) : Math.max(floor, top) + (d - de) * 0.84;
            if (t < out[k]) out[k] = t;
          });
        }
      }
    }
    return out;
  }
  function pointInPoly(x, z, poly) {
    let c = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      const a = poly[i], b = poly[j];
      if ((a[1] > z) !== (b[1] > z) && x < (b[0] - a[0]) * (z - a[1]) / (b[1] - a[1]) + a[0]) c = !c;
    }
    return c;
  }

  function integrate(b, i0, i1, v, kappa, rec) {
    const st = b.stations;
    if (rec) rec(i0, v);
    for (let i = i0 + 1; i <= i1; i++) {
      const a = st[i - 1], c = st[i];
      const dd = Math.abs(c.d - a.d), dy = c.y - a.y, ds = Math.hypot(dd, dy);
      const dec = drag(v) + PHYS.turn_loss_c * v * v * (kappa || 0);
      const v2 = v * v - 2 * G * dy - 2 * dec * ds;
      if (v2 <= 0.25) { if (rec) rec(i, 0); return { v: 0, stall: i }; }
      v = Math.sqrt(v2);
      if (rec) rec(i, v);
    }
    return { v, stall: null };
  }

  /* flight from a lip; land on a 1D profile (jump receiver) */
  function flightOnProfile(v, lip, angle, recv, slopeEnd) {
    const th = angle * D2R, vx = v * Math.cos(th), vy = v * Math.sin(th);
    const d0 = recv[0][0];
    let t = 0, k = 0;
    for (let n = 0; n < 2000; n++) {
      t += 0.01;
      const d = lip.d + vx * t, y = lip.y + vy * t - 0.5 * G * t * t;
      if (d < d0) { if (y < recv[0][1] - 1.0) return { short: true, air: d - lip.d, t }; continue; }
      while (k + 1 < recv.length && recv[k + 1][0] < d) k++;
      if (k + 1 >= recv.length) {
        const last = recv[recv.length - 1];
        if (y <= last[1]) return land(d, y, t, 0, recv.length - 1);
        continue;
      }
      const r0 = recv[k], r1 = recv[k + 1], f = (d - r0[0]) / Math.max(1e-9, r1[0] - r0[0]), ys = r0[1] + (r1[1] - r0[1]) * f;
      if (y <= ys) return land(d, y, t, r0[2] + (r1[2] - r0[2]) * f, k + 1);
    }
    return { never: true };
    function land(d, y, t, slope, idx) {
      const vyt = vy - G * t, b = slope * D2R;
      const vt = vx * Math.cos(b) + vyt * Math.sin(b), vn = Math.abs(-vx * Math.sin(b) + vyt * Math.cos(b));
      return { d, y, t, air: d - lip.d, past: d - d0, impact: vn, vt: Math.max(0.5, vt), idx, onSlope: d <= slopeEnd };
    }
  }

  /* flight from a pose into the world: land on any of the target pieces' surfaces (or the ground) */
  function flightWorld(v, exit, lift, targets, groundAt) {
    const th = (exit.a - lift) * D2R, vx = v * Math.cos(th), vy = v * Math.sin(th), hh = exit.h * D2R;
    const ux = Math.cos(hh), uz = Math.sin(hh);
    let t = 0, prevY = exit.y;
    for (let n = 0; n < 800; n++) {
      t += 0.01;
      const dx = vx * t, x = exit.x + ux * dx, z = exit.z + uz * dx, y = exit.y + vy * t - 0.5 * G * t * t;
      if (y < prevY - 0.001 || t > 0.3) {
        for (const tb of targets) {
          if (tb.type === 'bowl' && tb.info.wall) {      // into a pool: land on its transition (or its floor)
            const ch = Math.cos(tb.pose.h * D2R), sh = Math.sin(tb.pose.h * D2R);
            const poly = tb.info.poly || (tb.info.poly = tb.info.outlineLocal.map(([u, w]) => [tb.pose.x + u * ch - w * sh, tb.pose.z + u * sh + w * ch]));
            if (poly.length < 3 || !pointInPoly(x, z, poly)) continue;
            let xi = 1e9, near = 0; for (let i = 0; i < poly.length; i++) { const a = poly[i], c = poly[(i + 1) % poly.length], ddx = c[0] - a[0], ddz = c[1] - a[1], L2 = ddx * ddx + ddz * ddz || 1;
              const tt = clamp(((x - a[0]) * ddx + (z - a[1]) * ddz) / L2, 0, 1), dd = Math.hypot(x - a[0] - tt * ddx, z - a[1] - tt * ddz); if (dd < xi) { xi = dd; near = tt < 0.5 ? i : (i + 1) % poly.length; } }
            const wl = (tb.info.wallAt && tb.info.wallAt[near]) || tb.info.wall;
            const WH = wl.h, WR = Math.max(0.3, wl.R), fl = tb.pose.y - (wl.dep || 0), u = Math.max(0, WR - xi);
            // as meshed: a wall lower than its radius has its coping c0 inside the outline, with the deck in front of it
            const c0 = WH >= WR ? 0 : WR - WR * Math.sin(Math.acos(1 - WH / WR)), dk = num(wl.deck, 2);
            if (xi < c0 - dk) continue;
            let ys = xi < WR ? fl + WR - Math.sqrt(Math.max(0, WR * WR - u * u)) : fl, phi = xi < WR ? Math.atan2(u, Math.sqrt(Math.max(1e-9, WR * WR - u * u))) : 0;
            if (xi < c0) { ys = fl + WH; phi = 0; }       // on the deck
            if (y > ys + 0.05 && !(xi < 0.05 && c0 === 0 && y < fl + WH)) continue;
            const vyt = vy - G * t, vt = vx * Math.cos(phi) - vyt * Math.sin(phi), vn = Math.abs(vx * Math.sin(phi) + vyt * Math.cos(phi));
            return { target: tb.id, idx: 0, air: dx, impact: vn, vt: Math.max(0.5, vt), x, z, y, xi, phi: phi / D2R };
          }
          const st = tb.stations;
          for (let i = 0; i < st.length; i += 1) {
            const s = st[i], ex = x - s.x, ez = z - s.z;
            if (Math.abs(ex) > 60 || Math.abs(ez) > 60) continue;
            const hs = s.h * D2R, along = ex * Math.cos(hs) + ez * Math.sin(hs), lat = -ex * Math.sin(hs) + ez * Math.cos(hs);
            if (Math.abs(along) > 0.8 || Math.abs(lat) > s.w / 2 + 0.5) continue;
            if (y <= s.y + 0.05) {
              const vyt = vy - G * t, b = s.a * D2R, c = Math.cos(hs - hh);
              let vh = vx * c;            // horizontal velocity along the target's heading
              // a run landing fakie: the runtime's contact projects the
              // velocity along the run, so the surface, not the flight, sets
              // the sign of the tangential speed.
              if (vh < 0 && tb.type === 'run') vh = -vh;
              const vt = vh * Math.cos(b) + vyt * Math.sin(b), vn = Math.abs(-vh * Math.sin(b) + vyt * Math.cos(b));
              return { target: tb.id, idx: i, air: dx, impact: vn, vt: Math.max(0.5, vt), x, z, y };
            }
          }
        }
        if (groundAt) { const g = groundAt(x, z); if (g !== null && y < g) return { ground: true, air: dx, x, z, y }; }
      }
      prevY = y;
      if (y < exit.y - 200) break;
    }
    return { never: true };
  }

  function simulate(park, built, ctx) {
    const byId = new Map(park.pieces.map(p => [p.id, p]));
    const res = new Map();
    const R = id => { if (!res.has(id)) res.set(id, { vin: [Infinity, -Infinity], vout: [Infinity, -Infinity], issues: new Map(), jump: null, visited: false, vst: null }); return res.get(id); };
    const span = (a, v) => { a[0] = Math.min(a[0], v); a[1] = Math.max(a[1], v); };
    const issue = (id, level, text) => { const r = R(id); const key = text; const prev = r.issues.get(key); if (!prev || (prev === 'warn' && level === 'fail')) r.issues.set(key, level); };
    const routes = [];
    const starts = park.pieces.filter(p => p.type === 'rollin' || p.start);
    let budget = 20000;
    const J0 = () => ({ vlip: [Infinity, -Infinity], air: [Infinity, -Infinity], past: [Infinity, -Infinity], impact: [Infinity, -Infinity] });
    for (const sp of starts) {
      for (const v0 of PHYS.starts) {
        // broken: an earlier piece failed; the walk goes on with an assumed speed so later problems still show
        const walk = (id, v, path, entry, broken) => {
          if (budget-- <= 0) return;
          const p = byId.get(id), b = built.get(id);
          if (!p || !b) return;
          const tag = broken ? ' (after an earlier problem)' : '';
          const end = (how, vv) => routes.push({ start: sp.id, v0, path: path.concat(id), end: id, how, v: vv, broken: broken || null });
          if (path.includes(id)) { end('loop', v); return; }
          // a rider who already failed on their own line has an assumed speed: don't judge another line's pieces with it
          if (broken && p.line && sp.line && p.line !== sp.line) { end('broken', v); return; }
          const r = R(id); r.visited = true;
          if (!broken) span(r.vin, v); else r.afterFail = true;
          if (!r.vst) { r.vst = new Float32Array(b.stations.length).fill(Infinity); }
          const rec = broken ? null : (i, vv) => { if (vv < r.vst[i]) r.vst[i] = vv; };
          const P2 = path.concat(id);
          const t = p.type;
          let fail = broken;
          if (t === 'bowl' && !b.info.through) {
            if (v > PHYS.bowl_entry_max && !broken) issue(id, 'warn', `arrives at ${v.toFixed(1)} m/s (over ${PHYS.bowl_entry_max})`);
            r.arrive = r.arrive || [Infinity, -Infinity]; if (!broken) span(r.arrive, v);
            end('bowl', v); return;
          }
          if (!TYPES[t].ride) { end('dead end', v); return; }
          let vout, startI = entry ? entry.idx : 0;
          if (t === 'jump') {
            const lip = b.info.lip;
            const k = integrate(b, startI, lip.i, v, 0, rec);
            let vland, iland;
            if (k.stall !== null) { issue(id, 'fail', 'stalls on the kicker' + tag); fail = fail || id; vland = 8; iland = b.segs[1][0]; }
            else {
              const fl = flightOnProfile(k.v, lip, lip.a - b.info.lift, b.info.recv, b.info.slopeEnd);
              const J = r.jump || (r.jump = J0());
              if (!broken) span(J.vlip, k.v);
              if (fl.short || fl.never) {
                issue(id, 'fail', `too slow: falls short of the knuckle (lip ${k.v.toFixed(1)} m/s)` + tag); fail = fail || id;
                vland = Math.max(8, k.v * 0.8); iland = b.segs[1][0];
              } else {
                if (!broken) { span(J.air, fl.air); span(J.past, fl.past); span(J.impact, fl.impact); }
                if (fl.past < PHYS.touch_min) issue(id, 'warn', `lands only ${fl.past.toFixed(1)} m past the knuckle` + tag);
                if (!fl.onSlope) issue(id, fl.impact > PHYS.impact_max ? 'fail' : 'warn', `overshoots the landing slope (${fl.past.toFixed(0)} m past the knuckle)` + tag);
                if (fl.impact > PHYS.impact_max) issue(id, 'fail', `hard landing: ${fl.impact.toFixed(1)} m/s into the slope` + tag);
                vland = fl.vt; iland = Math.min(b.segs[1][0] + fl.idx, b.stations.length - 1);
              }
            }
            const out = integrate(b, iland, b.stations.length - 1, vland, 0, rec);
            if (out.stall !== null) { issue(id, 'fail', 'stalls on the run-out' + tag); fail = fail || id; vout = 8; }
            else vout = out.v;
          } else if (t === 'qp') {
            const air = v * v / (2 * G) - b.info.qp.h;
            r.qp = r.qp || { air: [Infinity, -Infinity] }; if (!broken) span(r.qp.air, air);
            if (air < 0) issue(id, 'warn', `does not reach the coping (${(-air).toFixed(1)} m short)` + tag);
            vout = Math.max(0.5, v - 1.5);
          } else {
            const top = t === 'kicker' ? b.info.lip.i : b.stations.length - 1;
            const kap = b.info.kappa || 0;
            if (b.info.corner && (v < PHYS.qp_window[0] || v > PHYS.qp_window[1]))
              issue(id, 'warn', `vert corner entered at ${v.toFixed(1)} m/s (proven ${PHYS.qp_window[0]}–${PHYS.qp_window[1]})` + tag);
            const o = integrate(b, startI, top, v, b.info.corner ? 0 : kap, rec);
            if (o.stall !== null) { issue(id, 'fail', 'rider stalls here' + tag); fail = fail || id; vout = 8; }
            else vout = b.info.corner ? Math.max(0.5, o.v - PHYS.qp_loss) : o.v;
          }
          if (!broken) span(r.vout, vout);
          const nexts = (p.next || []).filter(n => byId.has(n));
          if (!nexts.length) { issue(id, 'fail', 'dead end: the line stops here' + tag); end(fail ? 'broken' : 'dead end', vout); return; }
          for (const n of nexts) {
            const q = byId.get(n), nb = built.get(n);
            // a run that ends sloping up into a pool bowl launches into it, like a kicker (a vert landing on its wall)
            const launch = t === 'run' && q.type === 'bowl' && b.exit && b.exit.a > 3 && q.attach !== id;
            if (t === 'kicker' || launch) {
              const fl = flightWorld(vout, b.exit, b.info.lift || 0, [nb], ctx && ctx.groundAt);
              const J = r.jump || (r.jump = J0());
              if (!fail) span(J.vlip, vout);
              if (!fl.target) {
                issue(id, 'fail', `misses ${q.name || n}` + (fl.ground ? ' (lands on the ground)' : '') + tag);
                walk(n, Math.max(8, vout), P2, null, fail || id); continue;
              }
              if (!fail) { span(J.air, fl.air); span(J.impact, fl.impact); }
              if (fl.impact > PHYS.impact_max) issue(id, 'fail', `hard landing on ${q.name || n}: ${fl.impact.toFixed(1)} m/s` + tag);
              walk(n, fl.vt, P2, { idx: fl.idx }, fail);
              continue;
            }
            let gapFail = false;
            if (q.attach !== id && nb.stations.length && b.exit && q.type !== 'bowl') {
              const s0 = nb.stations[0], gap = Math.hypot(s0.x - b.exit.x, s0.z - b.exit.z), dy = s0.y - b.exit.y;
              if (gap > 1.5 || Math.abs(dy) > 0.6) { issue(id, 'fail', `not connected to ${q.name || n} (gap ${gap.toFixed(1)} m, step ${dy.toFixed(1)} m)`); gapFail = true; }
            }
            if (q.type === 'bowl' && b.exit && !(nb.info.through && q.attach === id)) {   // a flow bowl attached here starts at this exit
              const poly = bowlOutlineWorld(q, nb), ex = b.exit.x, ez = b.exit.z;
              const mind = Math.min(...poly.map((a, i) => { const c = poly[(i + 1) % poly.length], dx = c[0] - a[0], dz = c[1] - a[1], L2 = dx * dx + dz * dz || 1;
                const t = clamp(((ex - a[0]) * dx + (ez - a[1]) * dz) / L2, 0, 1); return Math.hypot(ex - a[0] - t * dx, ez - a[1] - t * dz); }));
              if (!pointInPoly(b.exit.x, b.exit.z, poly) && mind > 6) { issue(id, 'fail', `ends ${mind.toFixed(0)} m away from ${q.name}`); gapFail = true; }
            }
            walk(n, vout, P2, null, fail || (gapFail ? id : null));
          }
        };
        walk(sp.id, v0, [], null, null);
      }
    }
    // static checks
    for (const p of park.pieces) {
      const b = built.get(p.id); if (!b) continue;
      if (ctx && ctx.groundAt && b.stations.length > 1) {
        let worst = 0;
        for (const s of b.stations) { const g = ctx.groundAt(s.x, s.z); if (g !== null) worst = Math.max(worst, g - s.y); }
        if (worst > 3.0) issue(p.id, 'warn', `${worst.toFixed(1)} m below the ground (more than a 3 m bench cut)`);
      }
      if (TYPES[p.type].ride && !TYPES[p.type].terminal && !R(p.id).visited) issue(p.id, 'warn', 'not on any line from a roll-in');
    }
    return { res, routes };
  }

  /* ---------------------------------------------------------------- jump design helpers */
  // smallest lip speed that lands at least touch_min past the knuckle with the current shape
  function minLipSpeed(b) {
    if (!b.info.recv) return NaN;
    const lip = b.info.lip, ang = lip.a - b.info.lift;
    const ok = v => { const f = flightOnProfile(v, lip, ang, b.info.recv, b.info.slopeEnd); return !f.short && !f.never && f.past >= PHYS.touch_min; };
    if (!ok(70)) return Infinity;
    let lo = 1, hi = 70;
    for (let k = 0; k < 40; k++) { const m = (lo + hi) / 2; if (ok(m)) hi = m; else lo = m; }
    return hi;
  }
  function lipSpeeds(p, pose, vin) {          // lip speed for each entry speed (kicker climb included)
    const b = build(p, pose);
    return { b, v: vin.map(v => { const k = integrate(b, 0, b.info.lip.i, v, 0, null); return k.stall === null ? k.v : 0; }) };
  }
  /* Fit a jump's kicker and landing to its gap for riders arriving at speeds vin (array, slow..fast).
     Picks the gentlest lip angle that carries the slowest rider >= 4 m past the knuckle, a kicker radius that suits
     the speed, then a landing angle matching the fall line and a slope long enough for the fastest rider. */
  function fitJump(p, pose, vin, opts) {
    opts = opts || {};
    const q = Object.assign({}, p, { params: Object.assign({}, TYPES.jump.defaults, p.params) });
    const vmax = Math.max(...vin);
    q.params.kick_R = +clamp(vmax * vmax / (1.4 * G), 8, 70).toFixed(0);
    const evalOne = (deg, land, drop) => {
      q.params.lip_deg = deg; q.params.land_deg = land; q.params.drop = drop; q.params.land_len = 90;
      const { b, v } = lipSpeeds(q, pose, vin);
      if (v[0] <= 0) return null;
      const lip = b.info.lip, ang = lip.a - b.info.lift;
      const fl = v.map(vv => flightOnProfile(vv, lip, ang, b.info.recv, b.info.slopeEnd));
      if (fl.some(f => f.short || f.never) || fl[0].past < 4) return null;
      const kne = vprofile(0, 0, [['arc', num(q.params.knuckle_R, 4), -land]], 0.5), kd = kne[kne.length - 1][0];
      const len = fl[fl.length - 1].past - kd + 6;
      const imp = Math.max(...fl.map(f => f.impact));
      if (imp > PHYS.impact_max || len > (num(q.params.open, 20) >= 40 ? 130 : 80)) return null;
      return { cost: len * 0.5 + 0.5 * Math.abs(deg - 20) + 4 * Math.max(0, imp - 4) + 0.6 * drop, deg, land, drop, len: +Math.max(6, len).toFixed(1), v, fl };
    };
    const drops = opts.keepDrop ? [num(p.params.drop, 3)] : null;
    let best = null;
    const consider = r => { if (r && (!best || r.cost < best.cost)) best = r; };
    for (let deg = 6; deg <= 38; deg += 2) for (let land = 14; land <= 40; land += 2) for (const drop of drops || [0, 2, 4, 6, 8, 10, 12]) consider(evalOne(deg, land, drop));
    if (best) {
      const c = best;
      for (let deg = c.deg - 1.5; deg <= c.deg + 1.5; deg += 0.5) for (let land = c.land - 1.5; land <= c.land + 1.5; land += 0.5) for (const drop of drops || [c.drop - 1, c.drop - 0.5, c.drop, c.drop + 0.5, c.drop + 1]) if (drop >= 0) consider(evalOne(deg, land, drop));
    }
    if (!best) {
      q.params.lip_deg = 30; q.params.land_deg = 30; q.params.drop = num(p.params.drop, 3); q.params.land_len = num(p.params.land_len, 9);
      const b = build(q, pose);
      const need = minLipSpeed(b), have = lipSpeeds(q, pose, vin).v;
      const fastEnough = have.length && Math.min(...have) >= need;
      return { ok: false, need, have, params: null, fastEnough,
        why: fastEnough
          ? `Riders are fast enough, but their speeds (${vin.map(v => v.toFixed(1)).join(', ')} m/s) spread too far apart for one soft landing. Make the run-in more uniform or accept a longer landing.`
          : `Not enough speed: clearing ${num(q.params.open, 0)} m needs at least ${need.toFixed(1)} m/s at the lip.` };
    }
    const out = { lip_deg: best.deg, kick_R: q.params.kick_R, land_deg: best.land, land_len: best.len, drop: best.drop };
    const report = best.fl.map((f, i) => ({ vin: vin[i], vlip: best.v[i], past: f.past, impact: f.impact, air: f.air }));
    Object.assign(q.params, out);
    return { ok: true, params: out, report, need: minLipSpeed(build(q, pose)), have: best.v };
  }
  // extra vertical drop needed to raise speed from v to need (drag ~ 6 % of the drop on a typical run-in)
  const extraDrop = (v, need) => Math.max(0, (need * need - v * v) / (2 * G) * 1.15);

  /* summary of each line: starts, ends, minimum speed */
  function lineSummary(park, sim) {
    const out = {};
    const lineOf = new Map(park.pieces.map(p => [p.id, p.line]));
    for (const L of park.lines) out[L.id] = { routes: 0, bowl: 0, fails: 0, warns: 0, vmin: Infinity };
    for (const r of sim.routes) {
      const L = out[lineOf.get(r.start)]; if (!L) continue;
      L.routes++; if (r.how === 'bowl') L.bowl++;
    }
    for (const p of park.pieces) {
      const r = sim.res.get(p.id), L = out[p.line]; if (!r || !L) continue;
      for (const lvl of r.issues.values()) lvl === 'fail' ? L.fails++ : L.warns++;
      if (r.vst) for (const v of r.vst) if (Number.isFinite(v)) L.vmin = Math.min(L.vmin, v);
    }
    return out;
  }

  const api = { D2R, G, PHYS, TYPES, TEMPLATES, TEMPLATE_NOTE, vprofile, runProfile, planPath, build, layout, mesh, simulate, lineSummary,
    minLipSpeed, fitJump, lipSpeeds, extraDrop, flightOnProfile, flightWorld, bowlWalls, offsetBy, offsetDirs, integrate,
    getp, wrap, triangulate, bowlOutlineWorld, carveGround, pointInPoly, speedColour, poseOf, num };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.Park = api;
})(typeof window !== 'undefined' ? window : globalThis);
