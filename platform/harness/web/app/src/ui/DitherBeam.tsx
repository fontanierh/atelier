import { useMemo, type FC } from 'react';

export type BeamPreset = 'sweep' | 'edge' | 'floor' | 'floor-mirrored';

interface BeamShape {
  angle: number;
  bend: number;
  spread: number;
  warm: number;
  length: number;
  heat: number;
  haze: number;
  anchorX: number;
  anchorY: number;
  beam: number;
}

const PRESETS: Record<BeamPreset, BeamShape> = {
  sweep: { angle: 0.46, bend: 0.2, spread: 0.28, warm: 0.018, length: 0.82, heat: 1.25, haze: 0.18, anchorX: 0.62, anchorY: 0.24, beam: 0.68 },
  edge: { angle: -0.62, bend: 0.24, spread: 0.22, warm: 0.024, length: 1.1, heat: 1.35, haze: 0.22, anchorX: 0.72, anchorY: 0.92, beam: 0.64 },
  floor: { angle: -0.28, bend: 0.28, spread: 0.21, warm: 0.028, length: 1.25, heat: 1.4, haze: 0.28, anchorX: 0.52, anchorY: 0.96, beam: 0.62 },
  'floor-mirrored': { angle: 0.26, bend: 0.3, spread: 0.19, warm: 0.028, length: 1.2, heat: 1.45, haze: 0.25, anchorX: 0.54, anchorY: 0.97, beam: 0.58 },
};

const BAYER_4X4 = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5].map((v) => (v + 0.5) / 16);

interface RGB { r: number; g: number; b: number; }
const hexRgb = (hex: number): RGB => ({ r: ((hex >> 16) & 0xff) / 255, g: ((hex >> 8) & 0xff) / 255, b: (hex & 0xff) / 255 });
const mixRgb = (a: RGB, b: RGB, t: number): RGB => ({ r: a.r * (1 - t) + b.r * t, g: a.g * (1 - t) + b.g * t, b: a.b * (1 - t) + b.b * t });
const scaleRgb = (a: RGB, k: number): RGB => ({ r: a.r * k, g: a.g * k, b: a.b * k });

const STOPS: [number, RGB][] = [
  [0.0, hexRgb(0xd96538)],
  [0.04, hexRgb(0xe89654)],
  [0.11, hexRgb(0xf5d5a8)],
  [0.22, hexRgb(0xaecbfa)],
  [0.44, hexRgb(0x4f83d9)],
  [0.72, hexRgb(0x213f82)],
  [1.0, hexRgb(0x0d1833)],
];

function ramp(t: number): RGB {
  const clamped = Math.min(1, Math.max(0, t));
  let prev: [number, RGB] = STOPS[0]!;
  for (const stop of STOPS.slice(1)) {
    if (clamped <= stop[0]) return mixRgb(prev[1], stop[1], (clamped - prev[0]) / (stop[0] - prev[0]));
    prev = stop;
  }
  return prev[1];
}

function smoothstep(a: number, b: number, x: number): number {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
}

const BASE = hexRgb(0x07090d);
const URL_CACHE = new Map<string, string>();

function buildDataUrl(w: number, h: number, preset: BeamPreset): string {
  const key = `${preset}:${w}x${h}`;
  const hit = URL_CACHE.get(key);
  if (hit) return hit;

  const offscreen = document.createElement('canvas');
  offscreen.width = w;
  offscreen.height = h;
  const ctx = offscreen.getContext('2d');
  if (!ctx) return '';

  const img = ctx.createImageData(w, h);
  const pixels = img.data;
  const br = Math.round(BASE.r * 255);
  const bg = Math.round(BASE.g * 255);
  const bb = Math.round(BASE.b * 255);
  for (let i = 0; i < pixels.length; i += 4) {
    pixels[i] = br; pixels[i + 1] = bg; pixels[i + 2] = bb; pixels[i + 3] = 255;
  }

  const shape = PRESETS[preset];
  const cell = 2;
  const dot = 1;
  const diag = Math.hypot(w, h);
  const dirX = Math.cos(shape.angle), dirY = Math.sin(shape.angle);
  const nX = -dirY, nY = dirX;
  const ax = shape.anchorX * w, ay = shape.anchorY * h;

  let state = 0x7f4a7c15;
  const rand = () => {
    state ^= state << 13; state ^= state >>> 17; state ^= state << 5;
    return (state >>> 0) / 4294967296;
  };

  const cols = Math.floor(w / cell) + 1;
  const rows = Math.floor(h / cell) + 1;

  for (let row = 0; row < rows; row++) {
    const py = row * cell;
    const dy = py + 1 - ay;
    for (let col = 0; col < cols; col++) {
      const px = col * cell;
      const dx = px + 1 - ax;
      const along = (dx * dirX + dy * dirY) / diag;
      const across = (dx * nX + dy * nY) / diag - shape.bend * along * along;
      const reach = Math.pow(Math.max(0, 1 - Math.pow((along - 0.02) / shape.length, 2)), 0.65);
      const t = Math.min(1, Math.max(0, -across / shape.spread));
      const hue = Math.pow(t, shape.heat);
      const fringe = 0.7 * Math.exp(-Math.pow(across / shape.warm, 2)) + 0.24 * Math.exp(-across / (shape.warm * 3.2));
      const light = (across > 0 ? Math.min(0.7, fringe) : Math.pow(1 - t, 0.9)) * reach * shape.beam;

      if (light < 0.012) continue;

      const threshold = 0.38 * rand() + 0.62 * (BAYER_4X4[(row & 3) * 4 + (col & 3)] ?? 0.5);
      const tone = ramp(hue);
      const bloom = (across > 0 ? Math.exp(-across / (shape.warm * 7.5)) : Math.exp(-(-across) / (shape.spread * 0.85))) * reach * shape.beam;
      const glow = 0.48 * Math.pow(light, 1.05) + 0.12 * bloom;
      const smooth = mixRgb(BASE, tone, Math.min(1, glow));
      const dotted = smoothstep(0.18, 0.62, light);
      const gap = mixRgb(smooth, BASE, 0.48 * dotted);
      const shine = Math.exp(-Math.pow((hue - 0.11) / 0.07, 2)) * dotted;

      let lit: RGB | null = null;
      if (dotted > 0 && light > threshold) {
        const c = scaleRgb(tone, 0.94 + 0.1 * rand());
        const ink = scaleRgb(mixRgb(c, { r: 1, g: 0.98, b: 0.94 }, 0.32 * shine), 1 + 0.1 * shine);
        lit = mixRgb(gap, ink, Math.min(1, dotted * 1.15));
      }

      const gr = Math.min(255, Math.max(0, (gap.r * 255) | 0));
      const gg = Math.min(255, Math.max(0, (gap.g * 255) | 0));
      const gb = Math.min(255, Math.max(0, (gap.b * 255) | 0));
      const lr = lit ? Math.min(255, Math.max(0, (lit.r * 255) | 0)) : gr;
      const lg = lit ? Math.min(255, Math.max(0, (lit.g * 255) | 0)) : gg;
      const lb = lit ? Math.min(255, Math.max(0, (lit.b * 255) | 0)) : gb;

      const maxY = Math.min(h, py + cell);
      const maxX = Math.min(w, px + cell);
      for (let yy = py; yy < maxY; yy++) {
        let idx = (yy * w + px) * 4;
        const dotRow = yy < py + dot;
        for (let xx = px; xx < maxX; xx++) {
          const onDot = dotRow && xx < px + dot;
          pixels[idx] = onDot ? lr : gr;
          pixels[idx + 1] = onDot ? lg : gg;
          pixels[idx + 2] = onDot ? lb : gb;
          idx += 4;
        }
      }
    }
  }
  ctx.putImageData(img, 0, 0);
  const url = offscreen.toDataURL('image/png');
  URL_CACHE.set(key, url);
  return url;
}

export const DitherBeam: FC<{ preset: BeamPreset }> = ({ preset }) => {
  const bgUrl = useMemo(() => {
    const rawW = typeof window !== 'undefined' ? window.innerWidth : 1440;
    const rawH = typeof window !== 'undefined' ? Math.max(window.innerHeight, 900) : 900;
    const w = Math.min(1664, Math.ceil(rawW / 256) * 256);
    const h = Math.min(1152, Math.ceil(rawH / 256) * 256);
    return buildDataUrl(w, h, preset);
  }, [preset]);

  return (
    <div
      className="dither-beam-canvas"
      aria-hidden="true"
      style={bgUrl ? { backgroundImage: `url(${bgUrl})` } : undefined}
    />
  );
};
