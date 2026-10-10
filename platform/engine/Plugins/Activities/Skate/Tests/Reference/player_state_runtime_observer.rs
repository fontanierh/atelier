// Appended to the complete original physics/player_state.rs. Only fixture
// initialization and read-only observation are authored; load/reset unchanged.
mod migration_player_state {
use super::*;
use crate::{Input,Output};
fn snapshot(o:&mut Output,s:&PlayerState){
    let active=s.lifecycle.active();o.word(s.current()as u32);o.word(active.state as u32);o.word(active.owner_offset);
    o.word(s.requested_state as u32);crate::observe_StateSelector(o,&s.selector);
    o.state(&s.filtered);o.filtered(s.filtered_output);
    o.word(s.ground_output.is_some()as u32);if let Some(g)=&s.ground_output{crate::observe_PhysicsGroundOutput(o,g);}
    for w in s.post.jump_reference{o.word(w)}
    for w in [s.post.jump_fix_frames,s.post.latch_frames,s.post.state_frames]{o.word(w)}
    o.float(s.post.heading_adjust);for v in [s.post.complete,s.post.trajectory_pending,s.post.trajectory_valid,s.post.trajectory_available,s.post.trajectory_new_candidate]{o.word(v as u32)}
    for v in s.state_flags{o.word(v as u32)}o.word(s.state_count);o.word(s.update_count);
    crate::observe_TwoStageThresholds(o,&s.normal_off_ground);crate::observe_TwoStageThresholds(o,&s.skitching_off_ground);
    o.float(s.animated_board_threshold);o.word(s.initialized as u32);
    for id in PhysicalStateId::ALL{let c=s.registry.capability(id);o.word(c.id as u32);o.word(c.supported as u32);o.word(c.has_enter as u32);o.word(c.has_exit as u32);}
}
fn seed(i:&mut Input,s:&mut PlayerState){
    s.lifecycle=PhysicalPlayerStateLifecycle::new(PhysicalStateId::try_from(i.word()).unwrap());
    s.requested_state=PhysicalStateId::try_from(i.word()).unwrap();s.selector=crate::read_StateSelector(i);
    let head=std::array::from_fn(|_|i.word());let grind=i.grind();s.filtered.migration_player_state_seed(head,grind);
    s.filtered_output=if i.word()!=0{Some(crate::read_FilteredStateOutput(i))}else{None};
    s.ground_output=if i.word()!=0{Some(crate::read_PhysicsGroundOutput(i))}else{None};
    s.post.jump_reference=std::array::from_fn(|_|i.word());s.post.jump_fix_frames=i.word();s.post.latch_frames=i.word();s.post.state_frames=i.word();
    s.post.heading_adjust=i.float();s.post.complete=i.word()!=0;s.post.trajectory_pending=i.word()!=0;
    s.post.trajectory_valid=i.word()!=0;s.post.trajectory_available=i.word()!=0;s.post.trajectory_new_candidate=i.word()!=0;
    s.state_flags=std::array::from_fn(|_|i.word()!=0);s.state_count=i.word();s.update_count=i.word();
    s.normal_off_ground=crate::read_TwoStageThresholds(i);s.skitching_off_ground=crate::read_TwoStageThresholds(i);
    s.animated_board_threshold=i.float();s.initialized=i.word()!=0;
}
pub(super)fn run(stock:&Collections,fixture:&Collections,i:&mut Input,o:&mut Output)->Result<(),String>{
    let count=i.word();o.word(count);
    for c in 0..count{let mut owner=PlayerState::load(stock,"initial")?;o.word(c);snapshot(o,&owner);let commands=i.word();o.word(commands);
        for n in 0..commands{let op=i.word();let mut error=String::new();let mut loaded=true;
            match op{0|4=>{let mode=i.string();match PlayerState::load(if op==0{stock}else{fixture},&mode){Ok(replacement)=>owner=replacement,Err(e)=>{loaded=false;error=e;}}},1=>seed(i,&mut owner),2=>owner.reset_for_teleport(),3=>{let _=owner.current();},_=>return Err("invalid opcode".into())}
            o.word(c);o.word(n);o.word(op);o.word(loaded as u32);o.string(&error);snapshot(o,&owner);
        }
    }Ok(())
}
}
pub(crate)fn migration_player_state_run(stock:&Collections,fixture:&Collections,i:&mut crate::Input,o:&mut crate::Output)->Result<(),String>{migration_player_state::run(stock,fixture,i,o)}
