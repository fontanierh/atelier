//! Production evaluator oracle, using the untouched frozen host module.
#[path="../../crates/skate-host/src/animation_pose.rs"] mod animation_pose;
use skate_core::animation::{output::Sqt,playback_tree::PoseCommand,pose_add,pose_mirror,pose_trajectory::{self,LoopTransform}};
use std::io::{Read,Write};
struct Input {bytes:Vec<u8>,at:usize}
impl Input {
 fn word(&mut self)->u32 {let v=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
 fn float(&mut self)->f32 {f32::from_bits(self.word())}
 fn string(&mut self)->String {let n=self.word() as usize;let s=String::from_utf8(self.bytes[self.at..self.at+n].to_vec()).unwrap();self.at+=n;s}
 fn pose(&mut self)->Sqt {Sqt{scale:core::array::from_fn(|_|self.float()),rotation:core::array::from_fn(|_|self.float()),translation:core::array::from_fn(|_|self.float())}}
 fn commands(&mut self)->Vec<PoseCommand> {let n=self.word();(0..n).map(|_|match self.word() {0=>PoseCommand::Clip{name:self.string(),time:self.float(),previous_time:self.float(),loops:self.word()},1=>PoseCommand::Blend{weight:self.float()},2=>{let n=self.word();PoseCommand::WeightedBlend{weights:(0..n).map(|_|self.float()).collect()}},3=>PoseCommand::ChannelBlend{weight:self.float(),use_channels_from_weights:self.word()!=0},4=>PoseCommand::Pose{name:self.string()},5=>PoseCommand::Add{motion_is_a:self.word()!=0},6=>PoseCommand::Mirror{trajectory_mode:self.word()},_=>unreachable!()}).collect()}
}
fn word(out:&mut Vec<u8>,v:u32) {out.extend(v.to_le_bytes());}
fn string(out:&mut Vec<u8>,s:&str) {word(out,s.len() as u32);out.extend(s.as_bytes());}
fn pose(out:&mut Vec<u8>,s:Sqt) {for v in s.scale.into_iter().chain(s.rotation).chain(s.translation) {word(out,v.to_bits());}}
fn status(out:&mut Vec<u8>,r:Result<(),String>)->bool {match r {Ok(())=>{word(out,1);true},Err(e)=>{word(out,0);string(out,&e);false}}}
fn run()->Result<(),String> {
 let args:Vec<_>=std::env::args().collect();let banks=skate_data::animation_banks::AnimationBanks::load(std::path::Path::new(&args[1]))?;let mut evaluator=animation_pose::PoseEvaluator::from_banks(&banks)?;
 let root=std::path::Path::new(&args[2]);let authored_path=root.join("private/custom/crouch-treflip.json");std::fs::create_dir_all(authored_path.parent().unwrap()).unwrap();
 let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut input=Input{bytes,at:8};let n=input.word();let clips=input.word();for _ in 0..clips {input.string();}let mut out=Vec::new();
 for _ in 0..n {match input.word() {
  0=>{std::fs::write(&authored_path,input.string()).unwrap();status(&mut out,evaluator.load_authored_clips(root));},
  1=>{let owner=input.string();let text=input.string();status(&mut out,evaluator.install_mod_clips(&owner,&text));},
  2=>{evaluator.remove_mod_clips(&input.string());status(&mut out,Ok(()));},
  3=>{evaluator.clear_mod_clips();status(&mut out,Ok(()));},
  4=>{let commands=input.commands();match evaluator.evaluate(&commands) {Ok(p)=>{word(&mut out,1);word(&mut out,p.len() as u32);for &s in &p {pose(&mut out,s);}match evaluator.hierarchy(&p) {Ok(m)=>{word(&mut out,1);word(&mut out,m.len() as u32);for matrix in m {for v in matrix.into_iter().flatten() {word(&mut out,v.to_bits());}}},Err(e)=>{word(&mut out,0);string(&mut out,&e);}}},Err(e)=>{word(&mut out,0);string(&mut out,&e);}}},
  5=>{let n=input.word();let mut p:Vec<_>=(0..n).map(|_|input.pose()).collect();let n=input.word();let parents:Vec<_>=(0..n).map(|_|input.word() as i32).collect();let n=input.word();let mirrors:Vec<_>=(0..n).map(|_|input.word() as i32).collect();let mode=input.word();status(&mut out,pose_mirror::mirror(&mut p,&parents,&mirrors,mode));word(&mut out,p.len() as u32);for s in p {pose(&mut out,s);}},
  6=>{let current=input.pose();let previous=input.pose();let l=if input.word()!=0 {Some(LoopTransform{rotation:core::array::from_fn(|_|input.float()),translation:core::array::from_fn(|_|input.float())})}else {None};pose(&mut out,pose_trajectory::delta(current,previous,l));},
  7=>{let a=input.pose();let b=input.pose();pose(&mut out,pose_add::add(a,b,input.word()!=0));},
  _=>unreachable!(),
 }}assert_eq!(input.at,input.bytes.len());std::io::stdout().write_all(&out).map_err(|e|e.to_string())?;Ok(())
}
fn main() {if let Err(e)=run() {eprintln!("{e}");std::process::exit(2);}}
