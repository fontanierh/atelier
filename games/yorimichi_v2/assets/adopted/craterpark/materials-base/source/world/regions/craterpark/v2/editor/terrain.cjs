'use strict';
// Sampling and display grid semantics copied from the pinned editor app.js.
// @cc [owner:fontanierh,label:correctness] editor-terrain-frame
// Inner samples MUST be cell-centred, outer samples corner-centred. The display
// underlay offsets MUST NOT modify the heights used to build piece geometry.
const fs = require('node:fs');
const path = require('node:path');

function loadTerrain(directory, active) {
  const meta = JSON.parse(fs.readFileSync(path.join(directory, 'terrain.json'), 'utf8'));
  function load(grid, file) {
    if (typeof file !== 'string' || path.basename(file) !== file) throw Error('terrain filename must be a basename');
    if (![grid.x0, grid.z0, grid.G].every(Number.isFinite) || grid.G <= 0 ||
        ![grid.nx, grid.nz].every(n => Number.isInteger(n) && n >= 2 && n <= 4096) ||
        grid.nx * grid.nz > 2000000) throw Error('invalid or excessive terrain grid');
    const bytes = fs.readFileSync(path.join(directory, file));
    if (bytes.length !== grid.nx * grid.nz * 4) throw Error('terrain byte count mismatch');
    const a = new Float32Array(grid.nx * grid.nz);
    for (let i = 0; i < a.length; i++) {
      a[i] = bytes.readFloatLE(4 * i);
      if (!Number.isFinite(a[i])) throw Error('nonfinite terrain');
    }
    return a;
  }
  if (!['natural', 'dug'].includes(active)) throw Error('unknown terrain choice');
  if (meta.inner.cell_centred !== true || meta.outer.cell_centred !== false) throw Error('unsupported terrain sample convention');
  let inner = load(meta.inner, meta.inner.layers[active]);
  const outer = load(meta.outer, meta.outer.file);
  function sample(H, g, fi, fj) {
    const i = Math.floor(fi), j = Math.floor(fj), a = fi - i, b = fj - j;
    const h = (jj, ii) => H[jj * g.nx + ii];
    return (1-a)*(1-b)*h(j,i) + a*(1-b)*h(j,i+1) + (1-a)*b*h(j+1,i) + a*b*h(j+1,i+1);
  }
  function groundAt(x, z) {
    for (const [g, H, shift] of [[meta.inner, inner, .5], [meta.outer, outer, 0]]) {
      const fi = (x-g.x0)/g.G-shift, fj = (z-g.z0)/g.G-shift;
      if (fi >= 0 && fj >= 0 && fi < g.nx-1 && fj < g.nz-1) return sample(H,g,fi,fj);
    }
    return null;
  }
  function grid(H, g, centred, yOff) {
    const nx = Math.floor((g.nx-1)/2)+1, nz = Math.floor((g.nz-1)/2)+1;
    const pos = new Float32Array(nx*nz*3), idx = new Uint32Array((nx-1)*(nz-1)*6);
    let k = 0;
    for (let j=0; j<nz; j++) for (let i=0; i<nx; i++) {
      pos[k++] = g.x0+(i*2+(centred?.5:0))*g.G;
      pos[k++] = H[j*2*g.nx+i*2]+yOff;
      pos[k++] = g.z0+(j*2+(centred?.5:0))*g.G;
    }
    k=0;
    for (let j=0; j<nz-1; j++) for (let i=0; i<nx-1; i++) {
      const a=j*nx+i, b=a+1, c=a+nx, d=c+1;
      for (const v of [a,c,b,b,c,d]) idx[k++]=v;
    }
    return {pos,idx};
  }
  function display() {
    const O=meta.outer, I=meta.inner, OH=Float32Array.from(outer);
    for (let j=0;j<O.nz;j++) for (let i=0;i<O.nx;i++) {
      const fi=(O.x0+i*O.G-I.x0)/I.G-.5, fj=(O.z0+j*O.G-I.z0)/I.G-.5;
      if(fi>=1 && fj>=1 && fi<I.nx-2 && fj<I.nz-2) OH[j*O.nx+i]=sample(inner,I,fi,fj)-4;
    }
    return [grid(inner,I,true,0),grid(OH,O,false,-1)];
  }
  // the editor's cut ground (bowls, dug pieces) replaces the inner heights, as the editor displays it
  function carve(fn) { inner = Float32Array.from(fn(inner)); }
  return {groundAt,display,meta,carve,inner:()=>inner};
}
module.exports={loadTerrain};
