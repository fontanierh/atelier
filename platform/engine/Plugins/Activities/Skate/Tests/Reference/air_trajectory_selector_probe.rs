// Original numerical modules remain byte-identical; this child supplies
// transport, complete retained-state observations and required service bindings.
use super::{*,launch,scoring,math as m,grind::*};
use crate::physics::{board_world::{BoardWorld,WorldTriangle,query_metadata::{QueryMetadata,QueryMesh,QueryPool,Bounds}},world_contact::triangle_from_volume,contact::RetailContactMaterial,drive_frames::RetailAffineTransform,grind_contact::Primitive};
use super::grind_surface::{self,InvestigationInput,LandingOrientation,GeometryType};
use crate::point_graph::PointGraph;
use std::cell::{Cell,RefCell};
#[path="migration_air_world.rs"]mod air_world;
#[path="migration_grind_world.rs"]mod grind_world;
struct Input{words:Vec<u32>,at:usize}
impl Input{
 fn word(&mut self)->u32{let w=self.words[self.at];self.at+=1;w}
 fn float(&mut self)->f32{f32::from_bits(self.word())}
 fn vector(&mut self)->[f32;4]{std::array::from_fn(|_|self.float())}
 fn matrix(&mut self)->[[f32;4];4]{std::array::from_fn(|_|self.vector())}
 fn trajectory(&mut self)->Trajectory{Trajectory{position:self.vector(),velocity:self.vector(),acceleration:self.vector(),duration:self.float()}}
 fn request(&mut self)->QueryRequest{QueryRequest{trajectory:self.trajectory(),radius:self.float(),start_error:self.float(),end_error:self.float()}}
 fn launch(&mut self)->LaunchInfo{LaunchInfo{reckoning_transform:self.matrix(),reckoning_inverse:self.matrix(),start_velocity:self.vector(),com_velocity:self.vector(),skeleton_vector_160:self.vector(),skeleton_vector_176:self.vector(),board_position:self.vector(),animation_com_position:self.vector(),start_position_override:self.vector(),board_position_override:self.vector(),cone_angle_x:self.float(),cone_angle_z:self.float(),timestep:self.float(),player_jumped:self.word()!=0,use_position_override:self.word()!=0,trajectory_count:self.word()as u16}}
 fn input(&mut self)->SelectorInput{SelectorInput{gravity:self.vector(),ground_normal:self.vector(),contact_position:self.vector(),heading_direction:self.vector(),reference_up:self.vector(),board_vertical_velocity:self.float(),directional_input:self.float(),previous_physics_state:self.word(),flags_2472:self.word(),flags_2476:self.word(),offboard_flags_1776:self.word(),grind_lock_distance:self.float()}}
 fn graph(&mut self)->PointGraph<8>{PointGraph{x:std::array::from_fn(|_|self.float()),y:std::array::from_fn(|_|self.float())}}
 fn limits(&mut self)->GrindAssistLimits{GrindAssistLimits{lock_distance:self.float(),max_speed_squared_ledge:self.float(),max_speed_squared_rail:self.float(),max_downward_speed:self.float(),ledge_scalars:std::array::from_fn(|_|self.float()),tip_scalar:self.float(),maximum_adjust_angle:self.float(),deck_dimensions:std::array::from_fn(|_|self.float())}}
 fn world(&mut self)->BoardWorld{let n=self.word()as usize;let mut surfaces=Vec::new();let triangles=(0..n).map(|_|{let vertices=std::array::from_fn(|_|crate::math::Vector3::new(self.float(),self.float(),self.float()));let fat=self.float();let flags=self.word();let tag=self.word();surfaces.push(self.word()as u16);WorldTriangle{triangle:triangle_from_volume(vertices,fat,[1.;3],flags),material:RetailContactMaterial{static_friction:0.,dynamic_friction:0.,restitution:0.},tag}}).collect();let meshes=if n==0{vec![]}else{vec![QueryMesh{triangle_range:0..n,local_to_world:RetailAffineTransform::IDENTITY,world_to_local:RetailAffineTransform::IDENTITY,local_bounds:Bounds{min:crate::math::Vector3::new(-100.,-100.,-100.),max:crate::math::Vector3::new(100.,100.,100.)},matching_group:-1,rejection_flags:0,geometry:0,pool:QueryPool::Ground}]};BoardWorld::with_query_metadata(triangles,QueryMetadata{packed_surfaces:surfaces,meshes,static_edges:vec![],island_flags:0}).unwrap()}
 fn edges(&mut self)->Vec<Primitive>{let n=self.word();(0..n).map(|_|{let start=self.vector();let end=self.vector();let lo=self.word();let hi=self.word();Primitive{start,end,owner:u64::from(lo)|(u64::from(hi)<<32)}}).collect()}
}
pub fn floats<const N:usize>(o:&mut Vec<u32>,v:[f32;N]){o.extend(v.map(f32::to_bits));}
pub fn status(o:&mut Vec<u32>,e:Option<&str>){let s=e.unwrap_or("");o.extend([e.is_none()as u32,s.len()as u32]);o.extend(s.bytes().map(u32::from));}
fn matrix(o:&mut Vec<u32>,m:[[f32;4];4]){for v in m{floats(o,v);}}
fn trajectory(o:&mut Vec<u32>,t:Trajectory){floats(o,t.position);floats(o,t.velocity);floats(o,t.acceleration);o.push(t.duration.to_bits());}
fn request(o:&mut Vec<u32>,q:QueryRequest){trajectory(o,q.trajectory);floats(o,[q.radius,q.start_error,q.end_error]);}
fn result(o:&mut Vec<u32>,v:QueryResult){floats(o,v.contact_position);floats(o,v.contact_normal);floats(o,v.landing_normal);o.push(v.contact_time.to_bits());matrix(o,v.contact_transform);o.extend([v.contact_frame as u32,v.surface,v.geometry]);}
fn prediction(o:&mut Vec<u32>,v:Prediction){result(o,v.result);request(o,v.request);}
fn edge(o:&mut Vec<u32>,v:Primitive){floats(o,v.start);floats(o,v.end);o.extend([v.owner as u32,(v.owner>>32)as u32]);}
fn orientation(o:&mut Vec<u32>,v:LandingOrientation){o.extend([v.kind as u32,v.garbage as u32]);floats(o,v.boardslide_dir);floats(o,v.tipslide_dir);floats(o,v.backslash_dir);floats(o,v.high_side);}
fn target(o:&mut Vec<u32>,v:GrindTarget){edge(o,v.edge);o.extend([v.provider_index as u32,v.primitive_flags]);orientation(o,v.orientation);floats(o,v.point);floats(o,v.vertical_normal);}
fn grind_candidate(o:&mut Vec<u32>,v:GrindTrajectoryCandidate){floats(o,v.point);floats(o,v.trajectory_point);floats(o,v.direction);floats(o,v.approach);floats(o,[v.distance,v.time,v.angle]);o.extend([v.frame as u32,v.primitive as u32]);}
pub(super)fn candidate(o:&mut Vec<u32>,c:scoring::Candidate){prediction(o,c.prediction);floats(o,c.start_velocity);floats(o,c.normal);floats(o,c.collision_velocity);floats(o,c.collision_position);floats(o,[c.score,c.wall_score]);o.push(c.wall_ride as u32);o.push(c.grind.is_some()as u32);if let Some(t)=c.grind{target(o,t);}}
pub(super)fn launch_info(o:&mut Vec<u32>,v:LaunchInfo){matrix(o,v.reckoning_transform);matrix(o,v.reckoning_inverse);floats(o,v.start_velocity);floats(o,v.com_velocity);floats(o,v.skeleton_vector_160);floats(o,v.skeleton_vector_176);floats(o,v.board_position);floats(o,v.animation_com_position);floats(o,v.start_position_override);floats(o,v.board_position_override);floats(o,[v.cone_angle_x,v.cone_angle_z,v.timestep]);o.extend([v.player_jumped as u32,v.use_position_override as u32,u32::from(v.trajectory_count)]);}
fn graph<const N:usize>(o:&mut Vec<u32>,v:&PointGraph<N>){floats(o,v.x);floats(o,v.y);}
pub fn settings(o:&mut Vec<u32>,s:&SelectorSettings){
    o.push(s.cone_x.to_bits());
    o.push(s.cone_z.to_bits());
    o.push(s.trajectory_max_time.to_bits());
    o.push(s.trajectory_max_drop.to_bits());
    o.push(s.trajectory_error_start.to_bits());
    o.push(s.trajectory_error_end.to_bits());
    o.push(s.speed_factor_min.to_bits());
    o.push(s.speed_factor_max.to_bits());
    graph(o,&s.cone_angle_z_vs_speed);
    o.push(s.cone_x_second_pass.to_bits());
    o.push(s.cone_z_second_pass.to_bits());
    graph(o,&s.landing_time_bonus);
    graph(o,&s.landing_com_scalar_vs_slope);
    graph(o,&s.landing_force_scalar);
    graph(o,&s.grind_penalty_vs_distance);
    o.push(s.score_middle_bonus.to_bits());
    o.push(s.score_landing_force.to_bits());
    o.push(s.score_landing_direction.to_bits());
    o.push(s.score_transition.to_bits());
    o.push(s.surface_unrideable_score.to_bits());
    o.push(s.surface_dont_align_score.to_bits());
    o.push(s.natural_air_off_verts_scalar.to_bits());
    o.push(s.minimum_valid_time.to_bits());
    o.push(s.minimum_time_after_apex.to_bits());
    o.push(s.minimum_normal_delta_second_pass.to_bits());
    o.push(s.maximum_trajectory_adjust.to_bits());
    o.push(s.wall_ride_test_distance.to_bits());
    o.push(s.wall_ride_minimum_height.to_bits());
    o.push(s.wall_ride_angle_allow_landing.to_bits());
    o.push(s.wall_ride_height_score.to_bits());
    graph(o,&s.wall_ride_boost);
    o.push(s.wall_ride_normal_dot_limit.to_bits());
    graph(o,&s.displacement_vs_speed);
    graph(o,&s.displacement_vs_ground_normal);
    o.push(s.trajectory_radius.to_bits());
    o.push(s.trajectory_displacement.to_bits());
    o.push(s.minimum_trajectory_frames as u32);
    o.push(s.vert_jump_align_factor.to_bits());
    o.push(s.vert_jump_align_max_ground_normal_y.to_bits());
    o.push(s.vert_jump_align_min_direction_y.to_bits());
    o.push(s.vert_jump_align_max_angle.to_bits());
}
pub(super)fn batch(o:&mut Vec<u32>,b:&launch::LaunchBatch){o.push(b.requests.len()as u32);for &q in &b.requests{request(o,q);}o.push(b.velocities.len()as u32);for &v in &b.velocities{floats(o,v);}floats(o,b.origin);floats(o,b.board_position);floats(o,b.local_board_position);floats(o,b.local_com_position);floats(o,b.com_displacement);}
pub(super)fn selection(o:&mut Vec<u32>,v:Selection){o.push(v.candidate_index as u32);prediction(o,v.prediction);floats(o,v.start_velocity);floats(o,v.landing_normal);floats(o,v.collision_velocity);floats(o,v.collision_position);trajectory(o,v.com_trajectory);o.extend([v.surface_category,v.wall_ride as u32]);o.push(v.grind.is_some()as u32);if let Some(t)=v.grind{target(o,t);}}
pub(super)fn optional_vector(o:&mut Vec<u32>,v:Option<[f32;4]>){o.push(v.is_some()as u32);if let Some(v)=v{floats(o,v);}}
fn optional_float(o:&mut Vec<u32>,v:Option<f32>){o.push(v.is_some()as u32);if let Some(v)=v{o.push(v.to_bits());}}
fn query_prediction(o:&mut Vec<u32>,w:&BoardWorld,q:QueryRequest)->Prediction{let r=query_trajectory(q,|a,b,r|air_world::line(w,a,b,r),|c,r|air_world::nearby(w,c,r));let prediction_result=match r{Ok(v)=>{status(o,None);v},Err(e)=>{status(o,Some(&e));QueryResult::miss()}};result(o,prediction_result);Prediction{result:prediction_result,request:q}}
struct Evaluator<'a>{world:&'a BoardWorld,edges:&'a[Primitive],limits:GrindAssistLimits,height:PointGraph<8>,board:[f32;4],body:[f32;4],padding:f32,maximum:f32,velocity_scalar:f32,max_angle:f32,score:f32,penalty_domain:f32,truck_distance:f32,failure:Cell<u32>,calls:Cell<u32>,trace:RefCell<Vec<u32>>}
impl<'a>Evaluator<'a>{
 fn new(i:&mut Input,world:&'a BoardWorld,edges:&'a[Primitive])->Self{Self{world,edges,limits:i.limits(),height:i.graph(),board:i.vector(),body:i.vector(),padding:i.float(),maximum:i.float(),velocity_scalar:i.float(),max_angle:i.float(),score:i.float(),penalty_domain:i.float(),truck_distance:i.float(),failure:Cell::new(0),calls:Cell::new(0),trace:RefCell::new(vec![])}}
 fn capture(&self,p:Prediction){prediction(&mut self.trace.borrow_mut(),p);}
 fn evaluate(&self,p:&mut Prediction,middle:bool)->Result<GrindEvaluation,String>{
  self.calls.set(self.calls.get()+1);self.trace.borrow_mut().extend([1,middle as u32]);self.capture(*p);
  if self.failure.get()==1||(self.failure.get()==4&&self.calls.get()==2){self.capture(*p);return Err("Explicit grind producer failure".into());}
  let mut e=GrindEvaluation{target:None,score:0.,distance:1000.,effective_lock_distance:None,penalty_domain:self.penalty_domain};let indices:Vec<_>=(0..self.edges.len()).collect();let indices=trajectory_box_filter(&indices,self.edges,self.board);let mut candidates=Vec::new();
  for i in indices{if let Some(c)=consider_grind_primitive(*p,self.edges[i],i,self.padding){e.distance=e.distance.min(c.distance);candidates.push(c);}}
  if middle{while let Some(c)=take_best_grind(&mut candidates,self.limits.lock_distance,&self.height){
   let edge=self.edges[c.primitive];let query=InvestigationInput{start:edge.start,end:edge.end,reference:c.point,optional_probe:None,deck_center_to_truck:self.truck_distance};if grind_surface::prepare(query).is_none(){continue;}
   let surface=match grind_surface::investigate(query,|i,probe|grind_world::surface_probe(self.world,[17,0xffffffff],i,probe)){Ok(s)=>s,Err(e)=>{self.capture(*p);return Err(e)}};
   let mut orientation=LandingOrientation{kind:GeometryType::Impossible,garbage:false,boardslide_dir:[0.;4],tipslide_dir:[0.;4],backslash_dir:[0.;4],high_side:[0.;4]};let mut support=[0.;4];grind_surface::update_landing_orientation(Some(&surface),self.board,c.point,&mut support,&mut orientation);
   let Some(correction)=admitted_displacement(*p,c,edge,p.collision_velocity(),self.body,GrindSurfaceEvidence{kind:orientation.kind as u32,side:orientation.high_side},&self.limits,&mut e.effective_lock_distance)else{continue;};let reference=p.request.trajectory.velocity;apply_admitted_target(p,c,correction,support,reference,self.maximum,self.velocity_scalar,self.max_angle);
   let mut vertical=m::cross(m::cross(c.direction,m::UP),c.direction);if vertical[1]<0.{vertical=m::scale(vertical,-1.);}vertical=if m::length(vertical)>f32::from_bits(0x358637bd){m::normalize(vertical)}else{m::UP};e.target=Some(GrindTarget{edge,provider_index:c.primitive,primitive_flags:0x40000000|c.primitive as u32,orientation,point:c.point,vertical_normal:vertical});e.score=self.score;break;
  }}self.capture(*p);if self.failure.get()==2{return Err("Explicit grind failure after prediction mutation".into());}Ok(e)
 }
 fn line(&self,a:[f32;4],b:[f32;4],r:f32)->Result<Option<SurfaceHit>,String>{let mut t=self.trace.borrow_mut();t.push(2);floats(&mut t,a);floats(&mut t,b);t.push(r.to_bits());drop(t);if self.failure.get()==3{return Err("Explicit wall line producer failure".into());}air_world::line(self.world,a,b,r)}
 fn observe_trace(&self,o:&mut Vec<u32>){let mut t=self.trace.borrow_mut();o.push(t.len()as u32);o.extend(t.iter());t.clear();self.calls.set(0);}
}
fn variant(i:&mut Input,stock:&SelectorSettings)->SelectorSettings{let mut s=stock.clone();let mode=i.word();if mode&1!=0{s.minimum_trajectory_frames=0;s.minimum_valid_time=0.;s.minimum_normal_delta_second_pass=0.;}if mode&2!=0{s.vert_jump_align_max_ground_normal_y=2.;s.vert_jump_align_min_direction_y=-2.;s.vert_jump_align_factor=0.5;}if mode&4!=0{s.score_middle_bonus=0.;s.wall_ride_minimum_height=0.;s.wall_ride_angle_allow_landing=100.;s.wall_ride_normal_dot_limit=1.;}if mode&8!=0{s.minimum_trajectory_frames=100000;}s}
pub fn run(bytes:Vec<u8>,stock:&SelectorSettings)->Vec<u32>{let mut i=Input{words:bytes.chunks_exact(4).map(|b|u32::from_le_bytes(b.try_into().unwrap())).collect(),at:0};let mut o=Vec::new();let count=i.word();for index in 0..count{let world=i.world();let edges=i.edges();let op=i.word();let s=variant(&mut i,stock);o.extend([index,op,0]);let mark=o.len()-1;
 match op{
  0=>{let mut info=i.launch();let input=i.input();o.push(launch::adjust_velocity(&mut info,input,&s)as u32);launch_info(&mut o,info);batch(&mut o,&launch::batch(info,input,&s));},
  1=>{let takeoff=i.vector();let n=i.word();let indices=(0..n).map(|_|i.word()as usize).collect::<Vec<_>>();let result=trajectory_box_filter(&indices,&edges,takeoff);o.push(result.len()as u32);o.extend(result.into_iter().map(|v|v as u32));},
  2=>{let t=i.trajectory();let p=i.vector();let n=i.vector();optional_float(&mut o,descending_plane_time(t,p,n));},
  3=>{let q=i.request();let p=query_prediction(&mut o,&world,q);let padding=i.float();let difficulty=i.float();let height=i.graph();let mut cs=Vec::new();for (index,&edge)in edges.iter().enumerate(){let c=consider_grind_primitive(p,edge,index,padding);o.push(c.is_some()as u32);if let Some(c)=c{grind_candidate(&mut o,c);cs.push(c);}}o.push(cs.len()as u32);while let Some(c)=take_best_grind(&mut cs,difficulty,&height){grind_candidate(&mut o,c);}o.push(cs.len()as u32);},
  4=>{let services=Evaluator::new(&mut i,&world,&edges);let mut selector=TrajectorySelector::new();let n=i.word();o.push(n);selector.migration_observe(&mut o);for _ in 0..n{let command=i.word();o.push(command);let r=match command{0=>{let info=i.launch();let input=i.input();selector.launch(info,input,&s)},1|5=>{let input=i.input();services.failure.set(i.word());let mut results=selector.requests().iter().map(|&q|query_trajectory(q,|a,b,r|air_world::line(&world,a,b,r),|c,r|air_world::nearby(&world,c,r)).unwrap()).collect::<Vec<_>>();if command==5{results.push(QueryResult::miss());}selector.complete_batch(&results,input,&s,|p,m|services.evaluate(p,m),|a,b,r|services.line(a,b,r))},2=>Ok(selector.update_without_completion()),3=>{selector.cancel_pending();Ok(true)},4=>{selector.reset();Ok(true)},_=>panic!("command")};match r{Ok(v)=>{status(&mut o,None);o.push(v as u32)},Err(e)=>{status(&mut o,Some(&e));o.push(1)}}selector.migration_observe(&mut o);services.observe_trace(&mut o);}},
  5=>{let info=i.launch();let input=i.input();let pass=i.word()as u16;let adjusted=i.word()!=0;let services=Evaluator::new(&mut i,&world,&edges);services.failure.set(i.word());let batch=launch::batch(info,input,&s);let mut cs=Vec::new();for request in batch.requests{let p=query_prediction(&mut o,&world,request);cs.push(scoring::Candidate{prediction:p,start_velocity:[0.137,0.317,0.731,0.517],normal:[0.17,0.31,0.73,0.51],collision_velocity:[0.73,0.13,0.17,0.31],collision_position:[0.31,0.73,0.51,0.17],score:0.317,wall_score:0.731,wall_ride:true,grind:None});}let r=scoring::score(&mut cs,pass,adjusted,input,&s,|p,m|services.evaluate(p,m),|a,b,r|services.line(a,b,r));match r{Ok(v)=>{status(&mut o,None);o.push(v as u32)},Err(e)=>{status(&mut o,Some(&e));o.push(1)}}o.push(cs.len()as u32);for c in cs{candidate(&mut o,c);}services.observe_trace(&mut o);},
  _=>panic!("operation")
 }o[mark]=(o.len()-mark-1)as u32;}assert_eq!(i.at,i.words.len());o}
