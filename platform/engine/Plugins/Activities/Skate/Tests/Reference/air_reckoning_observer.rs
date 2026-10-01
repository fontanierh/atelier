// Appended after the entire frozen host physics/air_reckoning.rs. Only explicit
// fixture inputs and field observations are new; all called bodies are original.
mod migration{
use super::*;use crate::{Input as Reader,Output};
use skate_core::{air::{body_spin::{self,BodySpinState},body_flip::{self,BodyFlipState,BodyFlipInput,BodyFlipSettings}},riding::reckoning_frames::ReckoningFrames};
fn graph(i:&mut Reader)->skate_core::point_graph::PointGraph<8>{skate_core::point_graph::PointGraph{x:i.floats(),y:i.floats()}}
fn optional(i:&mut Reader)->Option<f32>{if i.word()!=0{Some(i.float())}else{None}}
fn flip_settings(i:&mut Reader)->BodyFlipSettings{BodyFlipSettings{smoothing:optional(i),maximum_speed:optional(i),spin_scale:optional(i),missing_attribute_value:i.float()}}
fn state(i:&mut Reader)->AirState{AirState{spin_angle:i.float(),spin_speed:i.float(),secondary_lean_angle:i.float(),flip_angle:i.float(),flip_speed:i.float(),flip_requested_speed:i.float(),spin_transform:i.matrix(),flip_axis:i.floats(),flip_active:i.word()!=0,flip_side:i.word()!=0}}
fn frames(i:&mut Reader)->ReckoningFrames{ReckoningFrames{ground:i.matrix(),system:i.matrix(),unflipped:i.matrix(),inverse_system:i.matrix(),body_flip:i.matrix(),heading:i.floats(),target_lean_angle:i.float(),lateral_tilt:i.floats()}}
fn out_state(o:&mut Output,s:&AirState){o.floats([s.spin_angle,s.spin_speed,s.secondary_lean_angle,s.flip_angle,s.flip_speed,s.flip_requested_speed]);o.matrix(s.spin_transform);o.floats(s.flip_axis);o.word(s.flip_active as u32);o.word(s.flip_side as u32);}
fn out_frames(o:&mut Output,f:&ReckoningFrames){for m in [f.ground,f.system,f.unflipped,f.inverse_system,f.body_flip]{o.matrix(m)}o.floats(f.heading);o.float(f.target_lean_angle);o.floats(f.lateral_tilt);}
fn out_settings(o:&mut Output,s:&Settings){o.floats(s.ground_normal_smoothing);for g in [&s.max_up_angle_delta,&s.tilt_vs_rotation,&s.tilt_vs_slope]{o.floats(g.x);o.floats(g.y)}o.floats([s.body_spin.derivative_floor,s.body_spin.acceleration_limit]);for g in &s.body_spin.curves{o.floats(g.x);o.floats(g.y)}o.floats(s.body_spin.input_fade_threshold);o.optional(s.body_flip.smoothing);o.optional(s.body_flip.maximum_speed);o.optional(s.body_flip.spin_scale);o.float(s.body_flip.missing_attribute_value);}
fn out_runtime(o:&mut Output,a:&AirReckoning,r:&RidingOutputs){out_state(o,&a.state);o.words(*r.body_spin.words());o.words(r.reckoning.migration_air_reckoning_words());out_frames(o,&r.reckoning_frames);out_settings(o,&a.settings);for mode in a.modes{o.word(mode.easy_body_spins as u32);o.word(mode.perfect_body_flips as u32)}for g in &a.stock_spin_curves{o.floats(g.x);o.floats(g.y)}o.float(a.stock_spin_acceleration);}
fn core_input(i:&mut Reader)->Input{Input{landing_normal:i.floats(),normal_blend:i.float(),target_spin:i.float(),flip_request:i.float(),com_to_deck:i.floats(),timestep:i.float(),physical_body_spin:i.float(),grind_adjusted_body_spin:i.float(),additive_spin:i.word()!=0,direct_spin:i.word()!=0,reverse_stance:i.word()!=0,easy_body_spins:i.word()!=0,perfect_body_flips:i.word()!=0}}
fn out_fields(o:&mut Output,f:PhysicsAirReckoningFields){o.floats(f.current_landing_normal_1152);o.floats(f.collision_reference_normal_1216);o.floats([f.body_spin_angle_1568,f.body_spin_speed_1572]);}
pub(super) fn run(assets:&std::path::Path,fixtures:&std::path::Path,i:&mut Reader,o:&mut Output)->Result<(),String>{
 let count=i.word();o.word(count);
 for case in 0..count{
  let rows=i.word();o.word(rows);let data=Collections::load(&fixtures.join(format!("case-{case}"))).map_err(|e|e.to_string())?;
  let mut a=match AirReckoning::load(&data){Ok(a)=>{o.status(Ok(()));a},Err(e)=>{o.status(Err(e));assert_eq!(rows,0);continue;}};
  let mut physical=super::super::GamePhysics::load_with_terrain(assets,super::super::ground::Terrain::Flat)?;
  let r=&mut physical.riding;out_runtime(o,&a,r);
  for _ in 0..rows{let op=i.word();o.word(op);match op{
   0=>{a.state=state(i);r.body_spin=BodySpinState::from_words(i.words());r.reckoning.migration_air_reckoning_set(i.words());r.reckoning_frames=frames(i);},
   1=>{let mut p=ProcessedPhysicsInput::default();p.flags_2468=i.word();p.flags_2472=i.word();p.flags_2484=i.word();p.state_variant_index_2528=i.word();p.timestep_2604=i.float();p.grind_adjusted_body_spin_2644=i.float();p.animation_com_to_deck_752=i.words();let body=i.float();let normal=i.floats();let blend=i.float();let target=i.float();let flip=i.float();match a.update(r,&p,body,normal,blend,target,flip){Ok(f)=>{o.status(Ok(()));out_fields(o,f)},Err(e)=>o.status(Err(e))}},
   2=>{let mut p=ProcessedPhysicsInput::default();p.flags_2468=i.word();let up=i.floats();let heading=i.floats();a.update_plant(r,&p,up,heading)},
   3=>a.set_spin_scale(i.float()),4=>a.state.reset_spin(),
   5=>{let input=i.float();let auto=i.float();let air=i.word()!=0;let mode=i.word()as u8;body_spin::update(&mut r.body_spin,&a.settings.body_spin,input,auto,air,mode)},
   6=>body_spin::update_ground(&mut r.body_spin,i.float()),
   7=>{let words=i.words();let result=std::panic::catch_unwind(||BodySpinState::from_words(words));match result{Ok(s)=>{r.body_spin=s;o.status(Ok(()))},Err(payload)=>{let message=if let Some(s)=payload.downcast_ref::<&str>(){(*s).to_owned()}else if let Some(s)=payload.downcast_ref::<String>(){s.clone()}else{panic!("unrecognized original panic payload")};o.status(Err(message))}}},
   8=>{let mut s=BodyFlipState{angle:i.float(),speed:i.float(),requested_speed:i.float(),spin_transform:i.matrix(),combined_transform:i.matrix()};let settings=flip_settings(i);let input=BodyFlipInput{requested_speed:i.float(),spin_angle:i.float(),normal:i.floats(),flip_axis:i.floats(),timestep:i.float(),perfect_body_flips:i.word()!=0};body_flip::update(&mut s,&settings,&input);o.floats([s.angle,s.speed,s.requested_speed]);o.matrix(s.spin_transform);o.matrix(s.combined_transform);},
   9=>{let target=i.floats();let from=i.floats();let maximum=i.float();o.floats(reckoning::clamp_vector_within_max_angle(target,from,maximum))},
   10=>{a.settings.body_spin.derivative_floor=i.float();a.settings.body_spin.acceleration_limit=i.float();a.settings.body_spin.curves=core::array::from_fn(|_|graph(i));a.settings.body_spin.input_fade_threshold=i.floats()},
   11=>{let input=core_input(i);reckoning::update(&mut r.reckoning,&mut r.reckoning_frames,&mut r.body_spin,&mut a.state,&a.settings,&input)},
   12=>a.settings.body_flip=flip_settings(i),
   13=>{let f=a.fields(r);out_fields(o,f)},
   _=>panic!("air reckoning operation")
  }out_runtime(o,&a,r);}
 }Ok(())
}
}
pub(crate) fn migration_air_reckoning_run(assets:&std::path::Path,fixtures:&std::path::Path,i:&mut crate::Input,o:&mut crate::Output)->Result<(),String>{migration::run(assets,fixtures,i,o)}
