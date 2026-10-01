//! Focused bridge world construction and actual platform controller histories.
#![allow(dead_code,unused_imports)]
mod physics;mod graph_host;mod graph_runtime;mod skater_animation;mod animation_pose;mod camera;mod difficulty;mod grind_world;mod input;mod scoring_runtime;mod skate_world;mod animation;mod crash_context;mod tuning;mod session_marker;
pub use physics::bridge;
use std::io::{Read,Write};
use skate_core::{math::{Vector3,Basis3},physics::{board_world::{BoardWorld,WorldTriangle},board_world::query_metadata::{Bounds,QueryMetadata,QueryPool},drive_frames::RetailAffineTransform,contact::RetailContactMaterial,collision::{WorldContactSettings,Sphere},world_contact::{ContactPrimitive,transform_triangle_volume}}};
struct Input{data:Vec<u8>,at:usize}
impl Input{
 fn word(&mut self)->u32{let v=u32::from_le_bytes(self.data[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
 fn wide(&mut self)->u64{u64::from(self.word())|(u64::from(self.word())<<32)}
 fn float(&mut self)->f32{f32::from_bits(self.word())}
 fn floats<const N:usize>(&mut self)->[f32;N]{std::array::from_fn(|_|self.float())}
 fn vector(&mut self)->Vector3{Vector3::new(self.float(),self.float(),self.float())}
 fn bounds(&mut self)->Bounds{Bounds{min:self.vector(),max:self.vector()}}
 fn basis(&mut self)->Basis3{Basis3{columns:std::array::from_fn(|_|self.floats())}}
 fn material(&mut self)->RetailContactMaterial{RetailContactMaterial{static_friction:self.float(),dynamic_friction:self.float(),restitution:self.float()}}
 fn xbox(&mut self)->skate_core::input::xbox::XboxState{skate_core::input::xbox::XboxState{buttons:self.word()as u16,triggers:std::array::from_fn(|_|self.word()as u8),left:std::array::from_fn(|_|self.word()as i16),right:std::array::from_fn(|_|self.word()as i16)}}
 fn primitive(&mut self)->ContactPrimitive{match self.word(){
  0=>ContactPrimitive::Sphere(Sphere{center:self.vector(),radius:self.float()}),
  1=>ContactPrimitive::Capsule{center:self.vector(),axis:self.vector(),half_length:self.float(),radius:self.float()},
  2=>{let vertices=std::array::from_fn(|_|self.vector());let fatness=self.float();let cosines=self.floats();let flags=self.word();let basis=self.basis();let translation=self.vector();ContactPrimitive::Triangle(transform_triangle_volume(vertices,fatness,cosines,flags,basis,translation))},
  3=>ContactPrimitive::RoundedBox{center:self.vector(),basis:self.basis(),half_extents:self.vector(),radius:self.float()},
  _=>panic!("Invalid gameplay world contact primitive")}}
}
struct Output(Vec<u32>);
impl Output{
 fn word(&mut self,v:u32){self.0.push(v)}fn wide(&mut self,v:u64){self.word(v as u32);self.word((v>>32)as u32)}fn float(&mut self,v:f32){self.word(v.to_bits())}
 fn floats<const N:usize>(&mut self,v:[f32;N]){self.0.extend(v.map(f32::to_bits))}
 fn vector(&mut self,v:Vector3){self.floats([v.x,v.y,v.z])}fn bounds(&mut self,v:Bounds){self.vector(v.min);self.vector(v.max)}
 fn text(&mut self,s:&str){self.word(s.len()as u32);self.0.extend(s.bytes().map(u32::from))}
 fn status(&mut self,ok:bool,error:&str){self.word(ok as u32);self.text(error)}
 fn block(&mut self,tag:u32,other:&Output){self.word(tag);self.word(other.0.len()as u32);self.0.extend(&other.0)}
 fn transform(&mut self,t:RetailAffineTransform){for c in t.basis.columns{self.floats(c)}self.vector(t.translation)}
 fn triangle(&mut self,w:WorldTriangle){let t=w.triangle;for v in t.vertices{self.vector(v)}self.vector(t.feature.normal);for e in t.feature.edges{self.vector(e)}self.word(t.feature.flags);self.floats(t.feature.edge_cosines);self.floats(t.edge_lengths);self.float(t.fatness);self.float(w.material.static_friction);self.float(w.material.dynamic_friction);self.float(w.material.restitution);self.word(w.tag)}
 fn metadata(&mut self,m:&QueryMetadata){self.word(m.packed_surfaces.len()as u32);for s in &m.packed_surfaces{self.word(u32::from(*s))}self.word(m.meshes.len()as u32);for q in &m.meshes{self.word(q.triangle_range.start as u32);self.word(q.triangle_range.end as u32);self.transform(q.local_to_world);self.transform(q.world_to_local);self.bounds(q.local_bounds);self.word(q.matching_group as u32);self.word(q.rejection_flags);self.word(q.geometry);self.word(match q.pool{QueryPool::Ground=>0,QueryPool::Island=>1,QueryPool::Conditional=>2})}self.word(m.static_edges.len()as u32);for e in &m.static_edges{self.vector(e.start);self.vector(e.end);self.bounds(e.local_bounds)}self.word(m.island_flags)}
 fn hit(&mut self,r:Result<Option<skate_core::physics::board_world::WorldLineHit>,&str>){match r{Err(e)=>{self.status(false,e);self.word(0)},Ok(h)=>{self.status(true,"");self.word(h.is_some()as u32);if let Some(h)=h{self.vector(h.geometry.position);self.vector(h.geometry.normal);self.float(h.geometry.fraction);self.floats(h.geometry.volume_parameter);self.word(h.tag)}}}}
}
fn observe_provider(o:&mut Output,p:&grind_world::StaticProvider){
 let v=p.primitives();o.word(v.len()as u32);for(n,primitive)in v.iter().enumerate(){o.floats(primitive.start);o.floats(primitive.end);o.wide(primitive.owner);let m=p.metadata(n);o.word(m.is_some()as u32);if let Some(m)=m{for g in m.spline_guids{o.wide(g)}o.word(m.segment_index);o.word(m.flags)}let g=p.spline_guids(primitive.owner);o.word(g.is_some()as u32);if let Some(g)=g{for w in g{o.wide(w)}}let s=p.source(n);o.word(s.is_some()as u32);if let Some(s)=s{o.text(&s.stream_file);o.text(&s.asset_id);o.wide(s.section_index);o.wide(s.section_offset)}let r=p.source_rail_index(n);o.word(r.is_some()as u32);if let Some(r)=r{o.wide(r)}let b=p.bounds(n);o.word(b.is_some()as u32);if let Some((min,max))=b{o.floats(min);o.floats(max)}}
 for owner in[0,1,2,0xffffffff,u64::MAX]{let g=p.spline_guids(owner);o.word(g.is_some()as u32);if let Some(g)=g{for v in g{o.wide(v)}}}for n in[v.len(),v.len()+1]{o.word(p.metadata(n).is_some()as u32);o.word(p.source(n).is_some()as u32);o.word(p.source_rail_index(n).is_some()as u32);o.word(p.bounds(n).is_some()as u32)}
}
fn observe_world(o:&mut Output,w:&BoardWorld,p:&grind_world::StaticProvider){
 let(bounds,fatness,seams)=w.migration_gameplay_world_storage();o.word(seams as u32);o.word(w.triangles().len()as u32);for t in w.triangles(){o.triangle(*t)}match w.query_metadata(){Ok(m)=>{o.status(true,"");o.metadata(m)},Err(e)=>o.status(false,e)}o.float(fatness);o.word(bounds.len()as u32);for b in bounds{o.bounds(*b)}observe_provider(o,p);
}
fn query(i:&mut Input,o:&mut Output,p:Option<(&BoardWorld,&grind_world::StaticProvider)>){
 let start=i.vector();let end=i.vector();let radius=i.float();let has=i.word()!=0;let bounds=i.bounds();let min=i.floats();let max=i.floats();let Some((w,g))=p else{o.status(false,"Fixture has no prepared world");return};o.status(true,"");let b=w.line_candidate_bounds(start,end,radius);o.word(b.is_some()as u32);if let Some(b)=b{o.bounds(b)}let ranges=w.candidate_ranges(has.then_some(bounds));o.word(ranges.len()as u32);for r in ranges{o.word(r.start as u32);o.word(r.end as u32)}let ids:Vec<_>=w.line_candidates(start,end,radius).map(|(n,_)|n).collect();o.word(ids.len()as u32);for n in ids{o.word(n as u32)}match w.candidate_mesh_indices(has.then_some(bounds)){Ok(v)=>{o.status(true,"");o.word(v.len()as u32);for n in v{o.word(n as u32)}},Err(e)=>{o.status(false,e);o.word(0)}}o.hit(w.query_thin_line(start,end));o.hit(w.query_swept_line(start,end,radius));match g.query(min,max){Ok(v)=>{o.status(true,"");o.word(v.len()as u32);for n in v{o.word(n as u32)}},Err(e)=>{o.status(false,&e);o.word(0)}}
}
fn contacts(i:&mut Input,o:&mut Output,p:Option<&mut BoardWorld>){
 use skate_core::physics::{board_world::{BoardWorldVolume,ContactRetentionSettings},board_step::CollisionBody};let n=i.word();let v:Vec<_>=(0..n).map(|_|BoardWorldVolume{body:CollisionBody::from_contact_id(i.word()),primitive:i.primitive(),linear_velocity:i.vector(),material:i.material()}).collect();let q=WorldContactSettings{volume_padding:i.float(),maximum_separating_distance:i.float(),edge_cos_bend_normal_threshold:i.float(),convexity_epsilon:i.float(),is_object:i.word()!=0};let r=ContactRetentionSettings{capacity:i.word(),duplicate_distance_squared:i.float(),deferred_reduction:i.word()!=0};let Some(w)=p else{o.status(false,"Fixture has no prepared world");return};o.status(true,"");let contacts=w.query_primitives(&v,q,r).to_vec();o.word(w.dropped_contacts());o.word(contacts.len()as u32);for collision in contacts{let c=collision.contact;let mut row=[0;64];for(offset,v)in[(0,c.position_on_a),(4,c.position_on_b),(8,c.normal)]{row[offset..offset+3].copy_from_slice(&[v.x.to_bits(),v.y.to_bits(),v.z.to_bits()])}row[3]=collision.body_a.contact_id();row[7]=collision.body_b.contact_id();row[11]=c.restitution.to_bits();row[15]=c.static_friction.to_bits();row[19]=c.dynamic_friction.to_bits();row[23]=c.tag;o.0.extend(row)}
}
fn main(){let mut data=Vec::new();std::io::stdin().read_to_end(&mut data).unwrap();let mut i=Input{data,at:0};let count=i.word();let mut total=Output(Vec::new());for index in 0..count{let kind=i.word();let commands=i.word();let mut body=Output(vec![commands]);match kind{0=>physics::bridge::migration_gameplay_world_run(&mut i,&mut body,commands),1=>input::migration_gameplay_input_run(&mut i,&mut body,commands),_=>panic!("Gameplay world/input kind")};total.word(index);total.word(kind);total.word(body.0.len()as u32);total.0.extend(body.0)}assert_eq!(i.at,i.data.len());for w in total.0{std::io::stdout().write_all(&w.to_le_bytes()).unwrap()}}
