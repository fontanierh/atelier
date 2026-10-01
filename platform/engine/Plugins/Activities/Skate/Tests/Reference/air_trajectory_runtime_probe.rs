// Full original active host runtime/provider composition. No completed hits or
// neutral services are supplied; raw rails/WMET and actual triangle worlds are
// the explicit engine geometry input boundary.
#![allow(dead_code)]
use std::io::{Read,Write};
use std::sync::Arc;
use skate_core::air::trajectory::{LaunchInfo,SelectorInput,QueryResult,QueryRequest,Trajectory};
use skate_core::physics::{board_world::{BoardWorld,WorldTriangle,query_metadata::{QueryMetadata,QueryMesh,QueryPool,Bounds}},world_contact::triangle_from_volume,contact::RetailContactMaterial,drive_frames::RetailAffineTransform};
use skate_core::math::Vector3;
// GENERATED_ORIGINAL_HOST
struct Input{words:Vec<u32>,at:usize}
impl Input{
 fn word(&mut self)->u32{let w=self.words[self.at];self.at+=1;w}
 fn float(&mut self)->f32{f32::from_bits(self.word())}
 fn wide(&mut self)->u64{let lo=self.word();u64::from(lo)|(u64::from(self.word())<<32)}
 fn text(&mut self)->String{let n=self.word();String::from_utf8((0..n).map(|_|self.word()as u8).collect()).unwrap()}
 fn vector(&mut self)->[f32;4]{std::array::from_fn(|_|self.float())}
 fn matrix(&mut self)->[[f32;4];4]{std::array::from_fn(|_|self.vector())}
 fn launch(&mut self)->LaunchInfo{LaunchInfo{reckoning_transform:self.matrix(),reckoning_inverse:self.matrix(),start_velocity:self.vector(),com_velocity:self.vector(),skeleton_vector_160:self.vector(),skeleton_vector_176:self.vector(),board_position:self.vector(),animation_com_position:self.vector(),start_position_override:self.vector(),board_position_override:self.vector(),cone_angle_x:self.float(),cone_angle_z:self.float(),timestep:self.float(),player_jumped:self.word()!=0,use_position_override:self.word()!=0,trajectory_count:self.word()as u16}}
 fn input(&mut self)->SelectorInput{SelectorInput{gravity:self.vector(),ground_normal:self.vector(),contact_position:self.vector(),heading_direction:self.vector(),reference_up:self.vector(),board_vertical_velocity:self.float(),directional_input:self.float(),previous_physics_state:self.word(),flags_2472:self.word(),flags_2476:self.word(),offboard_flags_1776:self.word(),grind_lock_distance:self.float()}}
 fn request(&mut self)->QueryRequest{QueryRequest{trajectory:Trajectory{position:self.vector(),velocity:self.vector(),acceleration:self.vector(),duration:self.float()},radius:self.float(),start_error:self.float(),end_error:self.float()}}
 fn context(&mut self)->physics::air_trajectory::GrindContext{let board=self.vector();let body=self.vector();let actor=self.word();let matching=self.word();let mut p=skate_core::player::input_phase::ProcessedPhysicsInput::default();p.vectors_544_560_592_608[2]=body.map(f32::to_bits);p.actor_query_2948=actor;p.actor_query_2952=matching;physics::air_trajectory::GrindContext::from_processed(&p,board)}
}
struct Output{words:Vec<u32>}
impl Output{
 fn word(&mut self,w:u32){self.words.push(w);}
 fn float(&mut self,f:f32){self.word(f.to_bits());}
 fn wide(&mut self,w:u64){self.word(w as u32);self.word((w>>32)as u32);}
 fn error(&mut self,e:Option<&str>){let e=e.unwrap_or("");self.word(e.len()as u32);self.words.extend(e.bytes().map(u32::from));}
 fn status(&mut self,e:Option<&str>){skate_core::air::trajectory::migration_probe::status(&mut self.words,e);}
}
// GENERATED_PROVIDER_TRANSPORT
fn mutate_settings(r:&mut physics::air_trajectory::AirTrajectoryRuntime,field:u32,word:u32){let v=f32::from_bits(word);let s=&mut r.settings;match field{0=>s.trajectory_radius=v,1=>s.minimum_valid_time=v,2=>s.minimum_trajectory_frames=word as i32,3=>s.minimum_normal_delta_second_pass=v,4=>s.trajectory_max_time=v,5=>s.trajectory_error_start=v,6=>s.trajectory_error_end=v,7=>s.cone_x_second_pass=v,8=>s.cone_z_second_pass=v,9=>s.score_middle_bonus=v,10=>s.maximum_trajectory_adjust=v,11=>s.wall_ride_minimum_height=v,12=>s.trajectory_max_drop=v,13=>s.vert_jump_align_max_ground_normal_y=v,14=>s.speed_factor_min=v,15=>s.speed_factor_max=v,_=>panic!("field")}}
fn runtime_world(kind:u32)->BoardWorld{if kind<6{return fixture_world(kind);}let w=fixture_world(if kind==8{2}else{1});let triangles=w.triangles().to_vec();if kind==6{return BoardWorld::new(triangles);}let mut metadata=w.query_metadata().unwrap().clone();if kind==7{for m in &mut metadata.meshes{m.matching_group=17;}}if kind==8{metadata.island_flags=0;for m in &mut metadata.meshes{m.pool=QueryPool::Conditional;}}BoardWorld::with_query_metadata(triangles,metadata).unwrap()}
fn main(){let assets=std::path::PathBuf::from(std::env::args().nth(1).unwrap());let data=skate_data::collections::Collections::load(&assets).unwrap();let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut i=Input{words:bytes.chunks_exact(4).map(|b|u32::from_le_bytes(b.try_into().unwrap())).collect(),at:0};let mut out=Output{words:vec![]};let count=i.word();
 for index in 0..count{out.word(index);let case_mark=out.words.len();out.word(0);let loaded=physics::air_trajectory::AirTrajectoryRuntime::load(&data);let mut runtime=match loaded{Ok(r)=>{out.status(None);r},Err(e)=>{out.status(Some(&e));assert_eq!(count,1);out.words[case_mark]=(out.words.len()-case_mark-1)as u32;continue;}};let mut world=runtime_world(i.word());let initial=out.words.len();out.word(0);runtime.migration_observe(&mut out);out.words[initial]=(out.words.len()-initial-1)as u32;let commands=i.word();out.word(commands);
 for _ in 0..commands{let op=i.word();out.word(op);let mark=out.words.len();out.word(0);let r=match op{
  0=>{let info=i.launch();let input=i.input();runtime.launch(info,input,&world)},
  1=>{let input=i.input();let context=i.context();runtime.update(input,&world,context)},
  2=>{runtime.selector.reset();Ok(true)},3=>{runtime.selector.cancel_pending();Ok(true)},4=>Ok(runtime.selector.update_without_completion()),
  5=>{runtime.bind_grind_world(Arc::new(read_provider(&mut i)));Ok(true)},6=>{let f=i.word();let w=i.word();mutate_settings(&mut runtime,f,w);Ok(true)},7=>{world=runtime_world(i.word());Ok(true)},
  8=>{let q=i.request();match physics::air_trajectory::AirTrajectoryRuntime::query(&world,q){Ok(v)=>{out.status(None);out.words.extend(skate_core::air::trajectory::migration_probe::runtime_result_words(v));Ok(true)},Err(e)=>{out.status(Some(&e));out.words.extend(skate_core::air::trajectory::migration_probe::runtime_result_words(QueryResult::miss()));Err(e)}}},
  9=>{let n=i.vector();let v=i.vector();let d=i.float();out.words.extend(physics::air_trajectory::migration_departure(n,v,d).map(f32::to_bits));Ok(true)},_=>panic!("operation")};
 match r{Ok(value)=>{out.status(None);out.word(value as u32)},Err(e)=>{out.status(Some(&e));out.word(1)}}let state_mark=out.words.len();out.word(0);runtime.migration_observe(&mut out);out.words[state_mark]=(out.words.len()-state_mark-1)as u32;out.words[mark]=(out.words.len()-mark-1)as u32;
 }out.words[case_mark]=(out.words.len()-case_mark-1)as u32;
 }assert_eq!(i.at,i.words.len());let mut stdout=std::io::BufWriter::new(std::io::stdout().lock());for w in out.words{stdout.write_all(&w.to_le_bytes()).unwrap();}}
