// Labels, limits and values come from the same preferences used by the Esc menu.
const choices={performance:['Quality','Performance'],renderer:['Forward · recommended','Lumen · higher resource use'],tree_optimization:['Off · full detail at every distance','On · lighter distant leaves'],tree_lod_mode:['Automatic · nearby full detail','Full detail · higher GPU cost','Intermediate · comparison','Distant · comparison'],show_fps:['Hidden','Shown'],goofy:['Regular · left foot forward','Goofy · right foot forward'],skate_mode:['Easy','Normal','Hardcore','Custom · tune every value'],skate_difficulty:['Easy · forgiving','Normal','Hardcore · strict'],skate_auto_push:['As the difficulty has it','Off','On'],skate_tight_flicks:['Off','On'],skate_assisted_air:['As the difficulty has it','Off','On']};
const groups=[['Movement',['stamina_rings','goofy']],['Camera',['mouse','cam_dist','fov']],
 ['Skate mode',['skate_mode']],['Skate feel · Custom',['skate_difficulty','skate_trucks','skate_flick_radius','skate_flick_window','skate_flick_pace','skate_pop','skate_boneless','skate_hippy','skate_gravity','skate_spin','skate_assisted_air','skate_vert_assist','skate_rail_magnetism','skate_grind_pop','skate_grind_friction','skate_push_speed','skate_push_power','skate_auto_push','skate_pump','skate_rolling_friction','skate_hill_speed','skate_braking','skate_steering','skate_carve','skate_grip','skate_powerslide','skate_wobble','skate_wobble_onset','skate_manual_drift','skate_landing','skate_impact','skate_get_up']],['Skate controls & camera',['skate_dead_zone','skate_stick_reach','skate_mouse_flick','skate_tight_flicks','skate_cam_dist','skate_cam_fov']],['Graphics',['performance','renderer','tree_optimization','tree_lod_mode','tree_lod_distance','show_fps','render_scale']],['Art & world',['painterly','paint_radius','toon','toon_bands','toon_soft','outline','wind']],['Light',['exposure','saturation','sun_height','sun_yaw','sun_warmth','sun_strength','sky_fill','bounce']]];
export function renderSettings(rows,onChange){
 const root=document.getElementById('settings-rows'),scroll=root.scrollTop;root.replaceChildren();
 const ordered=new Set();
 // The custom skate values only apply in the Custom skating mode (docs/SKATE.md).
 const custom=(rows.find(row=>row.key==='skate_mode')?.value??3)>2.5;
 function addGroup(name,items){
  if(!items.length)return;
  const group=document.createElement('fieldset'),legend=document.createElement('legend');legend.textContent=name;group.append(legend);
  if(name==='Skate feel · Custom'&&!custom){group.disabled=true;legend.textContent+=' (pick Custom to tune)'}
  for(const row of items){
   const label=document.createElement('label');label.className='setting-row';label.htmlFor=`setting-${row.key}`;
   const title=document.createElement('span');title.textContent=row.label;label.append(title);
   const output=document.createElement('output');output.htmlFor=`setting-${row.key}`;
   let input;
   if(choices[row.key]){
    input=document.createElement('select');choices[row.key].forEach((text,value)=>{const option=document.createElement('option');option.value=value;option.textContent=text;input.append(option)});
   }else{
    input=document.createElement('input');input.type='range';input.min=row.min;input.max=row.max;input.step=row.step??(row.key==='stamina_rings'?1:row.max>10?1:.01);
    const digits=row.step?Math.max(0,Math.min(3,Math.ceil(-Math.log10(row.step)-1e-3))):row.max>10?0:2;
    const format=v=>row.key==='stamina_rings'?`${Number(v).toFixed(0)} rings`:Number(v).toFixed(digits);
    output.value=format(row.value);input.oninput=()=>{output.value=format(input.value)};
   }
   input.id=`setting-${row.key}`;input.value=row.value;
   if(row.key.startsWith('tree_lod_')){
    const optimized=(rows.find(r=>r.key==='tree_optimization')?.value??1)>.5;
    const automatic=(rows.find(r=>r.key==='tree_lod_mode')?.value??0)<.5;
    input.disabled=!optimized||(row.key==='tree_lod_distance'&&!automatic);
    title.title=row.key==='tree_lod_distance'?'Higher values keep nearby detail farther away and use more GPU time. Applies live in Automatic mode.':'Forced modes compare the same detail at every distance. Automatic preserves nearby full detail.';
   }
   if(row.key==='renderer'&&row.running!==undefined&&row.running!==row.value)output.value='Restart pending';
   input.onchange=()=>{
    const value=Number(input.value);
    if(value===Number(row.value))return;
    let warning='';
    if(row.key==='renderer'){
     warning=value===1?'Lumen is a resource hog: it uses substantially more GPU time and memory and can lower the frame rate.':'Forward is the recommended default for smooth play.';
     if(value!==row.running)warning+=row.restart_supported?'\n\nThe game must restart. Your settings will be saved, but your current position will be lost. Restart now?':'\n\nThis choice takes effect on the next launch through the game launcher. Save for next launch?';
    }else if(row.key==='tree_optimization'&&value===0)warning='Full-detail trees at every distance use more GPU time and can lower the frame rate. Optimization preserves close trees and collision while simplifying distant leaf outlines. Turn it off now?';
    if(row.key==='tree_lod_mode'&&value===1)warning='Full-detail trees at every distance use more GPU time. Apply this live comparison?';
    if(warning&&!window.confirm(warning)){input.value=row.value;return;}
    onChange(row.key,value);
   };label.append(input,output);group.append(label);ordered.add(row.key);
  }
  root.append(group);
 }
 for(const [name,keys] of groups)addGroup(name,keys.map(key=>rows.find(row=>row.key===key)).filter(Boolean));
 addGroup('More',rows.filter(row=>!ordered.has(row.key)));root.scrollTop=scroll;
}
