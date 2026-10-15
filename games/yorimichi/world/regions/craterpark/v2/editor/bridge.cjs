'use strict';
// @cc [owner:fontanierh,label:correctness] pinned-editor-geometry
// Compile only the vendored hash. Unknown types/parameters and broken attachment
// graphs MUST fail; never repair a design or bridge an open gap in the adapter.
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const pin = require('./pin.json');
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
if (sha(fs.readFileSync(path.join(__dirname,'pieces.cjs'))) !== pin.pieces_sha256) throw Error('vendored pieces.cjs hash mismatch');
const P = require('./pieces.cjs');
const {loadTerrain}=require('./terrain.cjs');

function object(x, where) {
  if (!x || typeof x !== 'object' || Array.isArray(x)) throw Error(`${where}: expected object`);
}
function keys(x, allowed, where) {
  object(x,where);
  for(const k of Object.keys(x)) if(!allowed.includes(k)) throw Error(`${where}: unknown parameter/field ${k}; update pinned editor adapter`);
}
function number(x, where) {
  if(typeof x!=='number' || !Number.isFinite(x) || Math.abs(x)>100000) throw Error(`${where}: expected bounded finite number`);
}
// Optional parameters the editor reads but does not put in its type defaults (see the editor README).
const EXTRA = { run: ['corner', 'vert_assist_max'], jump: ['vert_assist_max'], bowl: ['ext', 'deep', 'spines', 'exit_wl', 'exit_wr'], deck: ['outline'] };
const WALL_EXTRA = ['level'];
function validate(park) {
  keys(park,['schema','about','frame','terrain','lines','pieces','rev','saved_at','notes'], 'park');
  if(park.schema!=='craterpark-editor/1') throw Error('unsupported editor schema');
  if(!['dug','natural'].includes(park.terrain)) throw Error('unknown terrain choice');
  if(!Array.isArray(park.pieces)||park.pieces.length>2048) throw Error('pieces must be an array of at most 2048 items');
  if(!Array.isArray(park.lines)) throw Error('lines must be an array');
  const lines=new Set(), by=new Map();
  for(const l of park.lines) {
    keys(l,['id','name','color','role'],'line');
    if(typeof l.id!=='string'||!l.id||lines.has(l.id)) throw Error('duplicate/invalid line id');
    if(typeof l.color!=='string'||!/^#[0-9a-f]{6}$/i.test(l.color)) throw Error(`${l.id}: invalid line colour`);
    lines.add(l.id);
  }
  function params(values, defaults, where, extra=[]) {
    keys(values,[...Object.keys(defaults),...extra],where);
    for(const [k,v] of Object.entries(values)) {
      const d=defaults[k], at=`${where}.${k}`;
      if(k==='outline') {
        if(!Array.isArray(v)||v.length<3||v.length>256) throw Error(`${at}: expected 3..256 points`);
        for(const q of v) {
          if(!Array.isArray(q)||(q.length!==2&&q.length!==4)) throw Error(`${at}: expected [u,v] or [u,v,top,under] points`);
          q.forEach(n=>number(n,at));
        }
      } else if(d===undefined) { if(v===null||!['object','boolean','number'].includes(typeof v)) throw Error(`${at}: unexpected value`); }
      else if(d && typeof d==='object') params(v,d,at,WALL_EXTRA);
      else if(k==='width_end' && (v===null||v==='')) continue;
      else if(typeof d==='boolean') { if(typeof v!=='boolean') throw Error(`${at}: expected boolean`); }
      else if(typeof d==='string') {
        if(typeof v!=='string'||(k==='template'&&v!==''&&v!=='custom'&&!Object.hasOwn(P.TEMPLATES,v))) throw Error(`${at}: unknown template`);
      } else number(v,at);
    }
  }
  for(const p of park.pieces) {
    keys(p,['id','type','name','line','attach','next','x','y','z','heading','slope','params','start'],'piece');
    if(typeof p.id!=='string'||!p.id||by.has(p.id)) throw Error('duplicate/invalid piece id');
    if(!Object.hasOwn(P.TYPES,p.type)) throw Error(`${p.id}: unknown piece type ${p.type}; update pinned editor adapter`);
    if(!lines.has(p.line)) throw Error(`${p.id}: unknown line`);
    for(const k of ['x','y','z','heading']) number(p[k],`${p.id}.${k}`);
    if(p.slope!==undefined) number(p.slope,`${p.id}.slope`);
    if(p.start!==undefined && typeof p.start!=='boolean') throw Error(`${p.id}: start must be boolean`);
    if(p.attach!==undefined && p.attach!==null && typeof p.attach!=='string') throw Error(`${p.id}: attach must be a piece id`);
    if(p.next!==undefined && (!Array.isArray(p.next)||p.next.some(n=>typeof n!=='string'))) throw Error(`${p.id}: next must be piece ids`);
    params(p.params||{},P.TYPES[p.type].defaults,`${p.id}.params`,EXTRA[p.type]||[]);
    by.set(p.id,p);
  }
  const visited=new Set(), active=new Set();
  function visit(p) {
    if(active.has(p.id)) throw Error(`attach cycle at ${p.id}`);
    if(visited.has(p.id)) return;
    active.add(p.id);
    for(const id of p.next||[]) if(!by.has(id)) throw Error(`${p.id}: missing next target ${id}`);
    if(p.attach) {
      if(!by.has(p.attach)) throw Error(`${p.id}: missing attach parent ${p.attach}`);
      const parent=by.get(p.attach);
      if(['deck','bowl','rail'].includes(parent.type)&&!(parent.type==='bowl'&&parent.params&&parent.params.through)) throw Error(`${p.id}: attach parent ${parent.id} has no exit`);
      visit(parent);
    }
    active.delete(p.id); visited.add(p.id);
  }
  park.pieces.forEach(visit);
}

function compile(input, terrainDir, out) {
  const bytes=fs.readFileSync(input), park=JSON.parse(bytes);
  validate(park);
  const terrain=loadTerrain(terrainDir,park.terrain), built=P.layout(park);
  terrain.carve(H=>P.carveGround(park,built,H,terrain.meta.inner));
  const index={schema:'craterpark-editor-mesh/1',accepted:false,pieces_sha256:pin.pieces_sha256,
    park_sha256:sha(bytes),terrain:park.terrain,rev:park.rev,lines:park.lines,pieces:[],ground:[]};
  fs.mkdirSync(out,{recursive:true});
  let total=0;
  function array(name, a, type) {
    if(a.some(v=>!Number.isFinite(v))) throw Error(`${name}: nonfinite geometry`);
    const size=type==='u32'||type==='f32'?4:8, buffer=Buffer.alloc(a.length*size);
    for(let i=0;i<a.length;i++) {
      if(type==='u32') buffer.writeUInt32LE(a[i],i*size);
      else if(type==='f32') buffer.writeFloatLE(a[i],i*size);
      else buffer.writeDoubleLE(a[i],i*size);
    }
    fs.writeFileSync(path.join(out,name),buffer); return {file:name,type,count:a.length,sha256:sha(buffer)};
  }
  for(let n=0;n<park.pieces.length;n++) {
    const p=park.pieces[n], b=built.get(p.id), line=park.lines.find(l=>l.id===p.line);
    const m=P.mesh(p,b,{groundAt:terrain.groundAt,lineColour:line.color,speed:null});
    total+=m.pos.length/3;
    if(total>4000000) throw Error('editor mesh exceeds 4 million vertices');
    if(m.pos.length%3||m.idx.length%3||m.pos.length!==m.nor.length||m.pos.length!==m.col.length||
       m.idx.some(i=>!Number.isInteger(i)||i<0||i>=m.pos.length/3)) throw Error(`${p.id}: invalid mesh arrays`);
    const stem=`piece-${String(n).padStart(4,'0')}`;
    const arrays={};
    for(const k of ['pos','nor','col','idx']) arrays[k]=array(`${stem}.${k}.bin`,m[k],k==='idx'?'u32':'f64');
    const center=b.stations.map(s=>[s.x,s.y,s.z]).flat();
    arrays.center=array(`${stem}.center.bin`,center,'f64');
    index.pieces.push({id:p.id,type:p.type,line:p.line,name:p.name,attach:p.attach||null,next:p.next||[],
      start:!!p.start,pose:b.pose,exit:b.exit||null,segs:b.segs,stations:b.stations,info:b.info,len:b.len,arrays});
    if(n%20===0) console.log(`Editor geometry: ${n+1}/${park.pieces.length} pieces, ${total} vertices`);
  }
  terrain.display().forEach((g,n)=>index.ground.push({id:`terrain-${n}`,arrays:{
    pos:array(`terrain-${n}.pos.bin`,g.pos,'f32'),idx:array(`terrain-${n}.idx.bin`,g.idx,'u32')}}));
  const I=terrain.meta.inner;
  index.ground_grid={x0:I.x0,z0:I.z0,G:I.G,nx:I.nx,nz:I.nz,cell_centred:true,heights:array('ground-cut.bin',Array.from(terrain.inner()),'f32')};
  fs.writeFileSync(path.join(out,'index.json'),JSON.stringify(index));
  console.log(`Editor geometry complete: ${park.pieces.length} pieces, ${total} vertices`);
}

if(require.main===module) {
  try {
    const [input,terrain,out]=process.argv.slice(2);
    if(!input||!terrain||!out) throw Error('usage: bridge.cjs SNAPSHOT.json TERRAIN_DIR OUTPUT_DIR');
    compile(input,terrain,out);
  } catch(e) { console.error(e.message); process.exitCode=1; }
}
module.exports={validate,compile};
