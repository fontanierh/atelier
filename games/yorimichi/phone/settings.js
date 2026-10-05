// Labels, limits and values come from the same preferences used by the Esc menu.
const choices={performance:['Quality','Performance'],show_fps:['Hidden','Shown'],goofy:['Regular · left foot forward','Goofy · right foot forward'],shield:['Off · the sword parries','Carried · it parries'],moveset:['Merged','Cairo (legacy)','Breath of the Wild (legacy)']};
const groups=[['Movement',['moveset','shield','stamina_rings','goofy']],['Camera',['mouse','cam_dist','fov']],['Graphics',['performance','show_fps','render_scale']],['Art & world',['painterly','paint_radius','toon','toon_bands','toon_soft','outline','wind']],['Light',['exposure','saturation','sun_height','sun_yaw','sun_warmth','sun_strength','sky_fill','bounce']]];
export function renderSettings(rows,onChange){
 const root=document.getElementById('settings-rows'),scroll=root.scrollTop;root.replaceChildren();
 const ordered=new Set();
 function addGroup(name,items){
  if(!items.length)return;
  const group=document.createElement('fieldset'),legend=document.createElement('legend');legend.textContent=name;group.append(legend);
  for(const row of items){
   const label=document.createElement('label');label.className='setting-row';label.htmlFor=`setting-${row.key}`;
   const title=document.createElement('span');title.textContent=row.label;label.append(title);
   const output=document.createElement('output');output.htmlFor=`setting-${row.key}`;
   let input;
   if(choices[row.key]){
    input=document.createElement('select');choices[row.key].forEach((text,value)=>{const option=document.createElement('option');option.value=value;option.textContent=text;input.append(option)});
   }else{
    input=document.createElement('input');input.type='range';input.min=row.min;input.max=row.max;input.step=row.key==='stamina_rings'?1:row.max>10?1:.01;
    const format=v=>row.key==='stamina_rings'?`${Number(v).toFixed(0)} rings`:Number(v).toFixed(row.max>10?0:2);
    output.value=format(row.value);input.oninput=()=>{output.value=format(input.value)};
   }
   input.id=`setting-${row.key}`;input.value=row.value;
   input.onchange=()=>onChange(row.key,Number(input.value));label.append(input,output);group.append(label);ordered.add(row.key);
  }
  root.append(group);
 }
 for(const [name,keys] of groups)addGroup(name,keys.map(key=>rows.find(row=>row.key===key)).filter(Boolean));
 addGroup('More',rows.filter(row=>!ordered.has(row.key)));root.scrollTop=scroll;
}
