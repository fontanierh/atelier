// Appended to original physics.rs after the complete Biped transport factory.
mod migration_landing_host{
use super::*;use crate::{Input,Output};
fn block(o:&mut Output,f:impl FnOnce(&mut Output)){let at=o.0.len();o.word(0);f(o);o.0[at]=(o.0.len()-at-1)as u32;}
pub(super)fn snapshot(o:&mut Output,s:&SkaterRuntime){
 o.word(3);block(o,|o|landing_on_deck::migration_landing_observe(o,&s.landing_on_deck));
 block(o,|o|{let p=&s.animation.packet;o.word(p.bone_count);o.word(p.hierarchy.len()as u32);for m in &p.hierarchy{o.matrix(*m)}o.word(p.local.len()as u32);for m in &p.local{o.matrix(*m)}o.float(p.timestep);o.words(p.foot_surface_ids);o.word(p.flags);for b in [p.board_flipped,p.mirrored,p.riding_switch,p.riding_fakie,p.weight_forwards,p.regular_stance]{o.word(b as u32)}o.word(p.air_dismount_revert_frames as u32)});
 block(o,|o|{let w=&s.skeleton_output.wobble;o.word(w.active as u32);o.word(w.landing as u32);o.floats([w.time,w.amplitude,w.direction]);o.word(w.migration_landing_selected()as u32)});
}
pub(super)fn pose(i:&mut Input,p:&GamePhysics,s:&mut SkaterRuntime)->Result<(),String>{
 let kind=i.word();s.animation.packet.hierarchy.clear();s.animation.packet.local.clear();
 if kind!=4{const POSES:[&str;4]=["RIG_TPOSE","POSTURE_STIFF_POSE","POSTURE_SLOUCH_POSE","POSTURE_BUFF_POSE"];let e=&s.animation.evaluator;let local=e.evaluate(&[skate_core::animation::playback_tree::PoseCommand::Pose{name:POSES[kind as usize].into()}])?;s.animation.packet.hierarchy=e.hierarchy(&local)?;s.animation.packet.local=local.iter().copied().map(skate_core::animation::output::sqt_to_matrix).collect();}
 let x=&mut s.player_input.processed;let deck=solve::deck_frame(&p.board);let input=skate_core::physics::skeleton_landing::LandingInput{filtered_state:0,flags_2468:x.flags_2468,flags_2472:x.flags_2472,flags_2476:x.flags_2476,balance:0.,physical_com_velocity_along_up:s.skeleton.record.centre_of_mass_velocity[1],physical_com_height:s.skeleton.record.centre_of_mass[1]-deck[3][1],animation_com_height:0.};
 s.animated_skeleton.process_pose(&s.animation.packet.hierarchy,input,x.timestep_2604,&mut x.flags_2468,&mut x.flags_2472,None)
}
}
