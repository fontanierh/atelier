// SPDX-License-Identifier: Apache-2.0
// Appended to the full frozen core and its root/board value transport.
use crate::physics::{board_animation::{BoardAnimation,BoardAnimationSettings,target_velocity},skeleton_air_frames::{self,AirDismountRevert}};
fn air_settings(i:&mut ProbeInput)->BoardAnimationSettings{
 let mut curve=||crate::point_graph::PointGraph{x:i.floats(),y:i.floats()};BoardAnimationSettings{slow:curve(),fast:curve()}
}
fn air_snapshot(out:&mut Vec<u32>,r:&SkeletonRootFrames,b:&SkeletonBoardFrames,a:&BoardAnimation){root(out,r);board(out,b);floats(out,a.rotation_error);out.push(a.blending as u32);}
fn main(){
 let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();assert_eq!(bytes.len()%4,0);
 let mut i=ProbeInput{words:bytes.chunks_exact(4).map(|b|u32::from_le_bytes(b.try_into().unwrap())).collect(),at:0};let mut out=Vec::new();let count=i.word();
 for c in 0..count{
  let mut r=i.root();let mut b=i.board();let settings=air_settings(&mut i);let mut a=BoardAnimation{rotation_error:i.floats(),blending:i.word()!=0};let n=i.word();out.extend([c,n,0]);let size_at=out.len()-1;let start=out.len();air_snapshot(&mut out,&r,&b,&a);
  for _ in 0..n{
   let op=i.word();out.push(op);match op{
    0=>a.reset(),1=>{let target=i.matrix();let deck=i.matrix();a.capture_physics_error(&target,&deck);},2=>{let target=i.matrix();let fast=i.word()!=0;matrix(&mut out,a.apply(&target,fast,&settings));},
    3=>{let target=i.floats();let position=i.floats();let dt=i.float();floats(&mut out,target_velocity(target,position,dt));},
    4=>{let mapped=i.matrix();let mut flags=i.word();matrix(&mut out,skeleton_air_frames::prepare_animated(&r,&mut b,&mapped,&mut flags));out.push(flags);},
    5=>{let reckoning=i.matrix();let target=i.floats();let local=i.floats();let requested=i.word()!=0;let frames=i.word();let goofy=i.word()!=0;skeleton_air_frames::update_known_air_roots(&mut r,&reckoning,target,local,AirDismountRevert{requested,frames,goofy});},
    6=>{let mapped=i.matrix();let mut flags=i.word();matrix(&mut out,skeleton_air_frames::prepare_known_air(&r,&mut b,&mapped,&mut flags));out.push(flags);},
    7=>skeleton_air_frames::finish_known_air(&mut r,&mut b,i.matrix()),8=>{let reckoning=i.matrix();let world=i.floats();let local=i.floats();skeleton_air_frames::update_plant_roots(&mut r,&reckoning,world,local);},
    9=>{a.rotation_error=i.floats();a.blending=i.word()!=0;},_=>panic!("Air frame command")
   }air_snapshot(&mut out,&r,&b,&a);
  }out[size_at]=(out.len()-start)as u32;
 }assert_eq!(i.at,i.words.len());let mut stdout=std::io::BufWriter::new(std::io::stdout().lock());for word in out{stdout.write_all(&word.to_le_bytes()).unwrap();}
}
