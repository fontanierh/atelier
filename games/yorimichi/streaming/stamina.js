// Native stamina is authoritative; the phone only draws it.
const NS='http://www.w3.org/2000/svg';
export function updateStamina(state){
 const gauge=document.getElementById('stamina');
 gauge.hidden=!state.ready||state.skating||state.sailboat;
 const rings=Math.max(1,Math.min(5,Math.round(state.staminaRings||2)));
 if(gauge.dataset.rings!==String(rings)){
  gauge.dataset.rings=String(rings);gauge.replaceChildren();
  const svg=document.createElementNS(NS,'svg');svg.setAttribute('viewBox','0 0 88 88');svg.setAttribute('aria-hidden','true');
  for(let i=0;i<rings;i++){
   for(const fill of [false,true]){
    const c=document.createElementNS(NS,'circle');c.setAttribute('cx','44');c.setAttribute('cy','44');c.setAttribute('r',12+i*7);c.setAttribute('fill','none');c.setAttribute('stroke-width','4');c.setAttribute('pathLength','1');c.setAttribute('transform','rotate(-90 44 44)');c.classList.add(fill?'stamina-fill':'stamina-track');if(fill)c.dataset.ring=i;svg.append(c);
   }
  }
  gauge.append(svg);
 }
 const units=Math.max(0,Math.min(rings,state.stamina??rings));
 gauge.setAttribute('aria-valuemax',String(rings));gauge.setAttribute('aria-valuenow',units.toFixed(2));
 gauge.classList.toggle('exhausted',!!state.exhausted);gauge.classList.toggle('sprinting',!!state.sprinting);
 for(const c of gauge.querySelectorAll('[data-ring]')){const fill=Math.max(0,Math.min(1,units-Number(c.dataset.ring)));c.setAttribute('stroke-dasharray',`${fill} 1`);}
}
