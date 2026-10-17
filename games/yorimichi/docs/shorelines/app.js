'use strict';
const $ = s => document.querySelector(s);
const ns = 'http://www.w3.org/2000/svg';
const routes = {
spawn:[[-380,-160],[-250,-180],[0,-165],[300,-170]],
harbor:[[300,-170],[600,-200],[950,-180],[1420,-140]],
'east-city':[[1420,-140],[2100,-30],[3200,0],[3200,900]],
'east-volcano':[[3200,900],[3200,2200],[3200,3600]],
'belmonte-east':[[3090,3600],[3010,5000],[2950,6500]],
north:[[2950,6500],[2800,7000],[0,7050],[-2800,7000],[-2950,6500]],
'belmonte-west':[[-2950,6500],[-3010,5000],[-3090,3600]],
'west-volcano':[[-3200,3600],[-3200,2200],[-3200,900]],
southwest:[[-3200,900],[-3200,0],[-1800,0],[-700,-20],[-380,-160]],
islet:[[-290,-500],[-250,-400],[-100,-390],[0,-500],[-60,-660],[-220,-670],[-290,-500]]
};
function svgElement(name, attrs){const e=document.createElementNS(ns,name);Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,v));return e;}
let sectors=[];
function expand(s){$('#lightbox-image').src=s.image;$('#lightbox-image').alt=`Proposed ${s.title.toLowerCase()}: ${s.tagline.toLowerCase()}`;$('#lightbox-title').textContent=`${s.id} / ${s.title}`;$('#download').href=s.image;$('#download').setAttribute('download',`${s.key}.jpg`);$('#lightbox').showModal();}
function select(s){
 document.querySelectorAll('[data-key]').forEach(e=>{const active=e.dataset.key===s.key;e.classList.toggle('selected',active);e.classList.toggle('active',active);if(e.matches('button')||e.getAttribute('role')==='button')e.setAttribute('aria-pressed',String(active));});
 $('#selected').innerHTML=`<button class="selected-image" type="button" aria-label="Expand ${s.title} concept"><img src="${s.image}" alt="Sunburst concept for ${s.title}: ${s.tagline}"><span class="image-zoom">Expand ↗</span></button><div class="meta"><span>${s.id} / ${s.kind.toUpperCase()}</span><span class="pill">${s.priority==='P1'?'FIRST PASS':'COMPLETE THE LOOP'}</span></div><h3>${s.title}</h3><p class="tagline">${s.tagline}</p><p>${s.where}</p><p class="definition"><strong>PROPOSED TREATMENT</strong>${s.proposal}</p><a class="jump" href="#concept-${s.key}">See the full location brief ↓</a>`;
 $('#selected .selected-image').addEventListener('click',()=>expand(s));
 $('#selected .jump').addEventListener('click',()=>applyFilter('all'));
}
function applyFilter(value){document.querySelectorAll('[data-filter]').forEach(b=>{const active=b.dataset.filter===value;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});document.querySelectorAll('.concept').forEach(c=>c.hidden=value!=='all'&&c.dataset.kind!==value&&c.dataset.priority!==value);}
function initialize(data){
 sectors=data;
 data.forEach(s=>{
  const color=s.kind==='Cliff'?'#b6c6c0':'#e5c689';
  const p=svgElement('path',{d:routes[s.key].map((q,i)=>`${i?'L':'M'}${q[0]},${-q[1]}`).join(' '),stroke:color,'data-key':s.key});$('#map-routes').append(p);
  const g=svgElement('g',{'data-key':s.key,role:'button',tabindex:0,'aria-label':`${s.id}: ${s.title}`,'aria-pressed':'false'});
  g.append(svgElement('circle',{cx:s.pin[0],cy:-s.pin[1],r:130}));const t=svgElement('text',{x:s.pin[0],y:-s.pin[1]+39});t.textContent=s.id;g.append(t);g.addEventListener('click',()=>select(s));g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select(s);}});$('#map-pins').append(g);
  const b=document.createElement('button');b.type='button';b.dataset.key=s.key;b.innerHTML=`<b>${s.id}</b>${s.title}`;b.setAttribute('aria-pressed','false');b.addEventListener('click',()=>select(s));$('#sector-list').append(b);
  const c=document.createElement('article');c.className='concept';c.id=`concept-${s.key}`;c.dataset.kind=s.kind;c.dataset.priority=s.priority;c.innerHTML=`<button class="image-button" type="button" aria-label="Expand ${s.title} concept"><img src="${s.image}" alt="Proposed ${s.title.toLowerCase()}: ${s.tagline.toLowerCase()}" loading="lazy" width="1536" height="1024"></button><p class="image-label">SUNBURST CONCEPT · PROPOSED · HIGH QUALITY</p><div class="meta"><span>${s.id} / ${s.kind.toUpperCase()}</span><span class="priority">${s.priority==='P1'?'FIRST PASS':'COMPLETE THE LOOP'}</span></div><h3>${s.title}</h3><p class="subtitle">${s.tagline}</p><p class="treatment">${s.proposal}</p><details><summary>Surveyed condition, access & location</summary><p><strong>SURVEY FINDING</strong>${s.problem}</p><p><strong>ACCESS & CONSTRAINTS</strong>${s.access}</p><p><strong>SURVEY ENVELOPE · METRES</strong>x ${s.bounds[0]} to ${s.bounds[2]} · y ${s.bounds[1]} to ${s.bounds[3]}<br>Regional envelope, not a final construction boundary.</p></details><a class="provenance" href="${s.provenance}">Full prompt & Sunburst provenance ↗</a>`;c.querySelector('.image-button').addEventListener('click',()=>expand(s));$('#gallery').append(c);
 });
 select(data.find(s=>s.key==='belmonte-east'));
}
fetch('assets/sectors.json').then(r=>{if(!r.ok)throw Error('Briefs unavailable');return r.json();}).then(initialize).catch(()=>{$('#selected').innerHTML='<p class="error">The location briefs could not load. Please reload the page.</p>';});
const zoomButtons=['whole','south'];
zoomButtons.forEach(id=>$('#'+id).addEventListener('click',()=>{
 $('#coast-map').setAttribute('viewBox',id==='whole'?'-3450 -7350 6900 8250':'-650 -750 2300 1600');
 zoomButtons.forEach(k=>{$('#'+k).classList.toggle('active',k===id);$('#'+k).setAttribute('aria-pressed',String(k===id));});
 const isSouth=id==='south';document.querySelectorAll('#map-pins circle').forEach(e=>e.setAttribute('r',isSouth?48:130));document.querySelectorAll('#map-pins text').forEach(e=>{e.style.fontSize=isSouth?'42px':'';const s=sectors.find(s=>s.key===e.parentElement.dataset.key);e.setAttribute('y',-s.pin[1]+(isSouth?15:39));});document.querySelectorAll('#map-routes path').forEach(e=>e.style.strokeWidth=isSouth?'18':'');$('#landmarks').style.display=isSouth?'none':'';
}));
document.querySelectorAll('[data-filter]').forEach(b=>b.addEventListener('click',()=>applyFilter(b.dataset.filter)));
$('#lightbox .close').addEventListener('click',()=>$('#lightbox').close());$('#lightbox').addEventListener('click',e=>{if(e.target===$('#lightbox')){const r=$('#lightbox').getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)$('#lightbox').close();}});
