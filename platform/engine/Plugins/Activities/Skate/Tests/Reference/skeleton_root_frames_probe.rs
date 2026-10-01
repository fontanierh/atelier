// Appended to frozen crate root; the original producers remain unchanged.
use std::io::{Read,Write};
use crate::physics::{skeleton_animation_record::AnimationPartTransform as Transform,skeleton_root::{SkeletonRootFrames,orthonormalize,inverse_rigid},skeleton_board_frames::SkeletonBoardFrames};
struct ProbeInput{words:Vec<u32>,at:usize}
impl ProbeInput{
 fn word(&mut self)->u32{let w=self.words[self.at];self.at+=1;w}
 fn float(&mut self)->f32{f32::from_bits(self.word())}
 fn floats<const N:usize>(&mut self)->[f32;N]{std::array::from_fn(|_|self.float())}
 fn matrix(&mut self)->Transform{std::array::from_fn(|_|self.floats())}
 fn root(&mut self)->SkeletonRootFrames{
  let board=self.matrix();let inverse_board=self.matrix();let previous_board_position=self.floats();let predicted_board_position=self.floats();let supplied=self.word()!=0;let prediction=self.floats();
  SkeletonRootFrames{board,inverse_board,previous_board_position,predicted_board_position,supplied_prediction:if supplied{Some(prediction)}else{None},animation_to_board:self.matrix(),animation_to_world:self.matrix(),world_to_animation:self.matrix(),heading_alignment:self.matrix(),initialize_heading:self.word()!=0}
 }
 fn board(&mut self)->SkeletonBoardFrames{SkeletonBoardFrames{physical_board:self.matrix(),skate_root:self.matrix(),animation_target:self.matrix(),com_frame:self.matrix(),lifted_com_frame:self.matrix(),centre_of_mass:self.floats(),previous_centre_of_mass:self.floats(),com_velocity:self.floats(),local_centre_of_mass:self.floats(),local_board_position:self.floats(),lift_height:self.float()}}
}
fn floats(out:&mut Vec<u32>,v:[f32;4]){out.extend(v.map(f32::to_bits));}
fn matrix(out:&mut Vec<u32>,m:Transform){for c in m{floats(out,c);}}
fn root(out:&mut Vec<u32>,r:&SkeletonRootFrames){matrix(out,r.board);matrix(out,r.inverse_board);floats(out,r.previous_board_position);floats(out,r.predicted_board_position);out.push(r.supplied_prediction.is_some() as u32);floats(out,r.supplied_prediction.unwrap_or([0.;4]));matrix(out,r.animation_to_board);matrix(out,r.animation_to_world);matrix(out,r.world_to_animation);matrix(out,r.heading_alignment);out.push(r.initialize_heading as u32);}
fn board(out:&mut Vec<u32>,b:&SkeletonBoardFrames){for m in [b.physical_board,b.skate_root,b.animation_target,b.com_frame,b.lifted_com_frame]{matrix(out,m);}for v in [b.centre_of_mass,b.previous_centre_of_mass,b.com_velocity,b.local_centre_of_mass,b.local_board_position]{floats(out,v);}out.push(b.lift_height.to_bits());}
fn main(){
 let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();assert_eq!(bytes.len()%4,0);let mut i=ProbeInput{words:bytes.chunks_exact(4).map(|b|u32::from_le_bytes(b.try_into().unwrap())).collect(),at:0};let mut out=Vec::new();let count=i.word();
 for index in 0..count{
  let(mut r,mut b)=if i.word()!=0{(i.root(),i.board())}else{(SkeletonRootFrames::default(),SkeletonBoardFrames::default())};let n=i.word();out.extend([index,n,0]);let size_at=out.len()-1;let start=out.len();root(&mut out,&r);board(&mut out,&b);
  for _ in 0..n{let op=i.word();out.push(op);match op{
   0=>{let physical=i.matrix();let velocity=i.floats();let dt=i.float();let animation=i.matrix();let reckoning=i.matrix();r.update(physical,velocity,dt,&animation,&reckoning);},
   1=>{let physical=i.matrix();let animation=i.matrix();let reckoning=i.matrix();r.update_teleport(physical,&animation,&reckoning);},
   2=>r.reset_initial_alignment(i.matrix()),
   3=>{let supplied=i.word()!=0;let prediction=i.floats();r.supplied_prediction=if supplied{Some(prediction)}else{None};},
   4=>{r.initialize_heading=i.word()!=0;r.heading_alignment=i.matrix();},
   5=>b.reset(i.matrix()),6=>b.publish_local_observations(&r,&i.matrix()),
   7=>{let com=i.floats();let dt=i.float();let flags=i.word();b.publish_centre_of_mass(com,dt,flags);},
   8|9=>{let mapped=i.matrix();let actual=i.matrix();let mut flags=i.word();let target=if op==8{b.prepare_ground(&r,&mapped,actual,&mut flags)}else{b.prepare_teleport(&r,&mapped,actual,&mut flags)};out.push(flags);matrix(&mut out,target);},
   10=>{let frame=i.matrix();let position=i.floats();let height=i.float();b.update_com_lift(&frame,position,height);},
   11=>{let frame=i.matrix();matrix(&mut out,orthonormalize(frame));matrix(&mut out,inverse_rigid(&frame));},_=>panic!("Root frame operation")}
   root(&mut out,&r);board(&mut out,&b);
  }out[size_at]=(out.len()-start) as u32;
 }assert_eq!(i.at,i.words.len());let mut stdout=std::io::BufWriter::new(std::io::stdout().lock());for w in out{stdout.write_all(&w.to_le_bytes()).unwrap();}
}
