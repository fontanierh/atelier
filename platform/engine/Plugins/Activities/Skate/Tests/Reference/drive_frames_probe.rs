use skate_core::{math::{Basis3,Vector3},physics::{drive_frames::*,drive_parameters::RetailDriveFramesRaw,rigid_body::RetailQuaternion}};
use std::io::{Read,Write};
struct Input{words:Vec<u32>,at:usize}
impl Input{
 fn word(&mut self)->u32{let v=self.words[self.at];self.at+=1;v}fn float(&mut self)->f32{f32::from_bits(self.word())}
 fn vector(&mut self)->Vector3{Vector3::new(self.float(),self.float(),self.float())}
 fn basis(&mut self)->Basis3{Basis3{columns:std::array::from_fn(|_|std::array::from_fn(|_|self.float()))}}
 fn frame(&mut self)->RetailAffineTransform{RetailAffineTransform{basis:self.basis(),translation:self.vector()}}
}
fn floats(out:&mut Vec<u32>,v:impl IntoIterator<Item=f32>){out.extend(v.into_iter().map(f32::to_bits));}
fn vector(out:&mut Vec<u32>,v:Vector3){floats(out,[v.x,v.y,v.z]);}
fn quat(out:&mut Vec<u32>,q:RetailQuaternion){floats(out,[q.x,q.y,q.z,q.w]);}
fn frame(out:&mut Vec<u32>,f:RetailAffineTransform){for c in f.basis.columns{floats(out,c);}vector(out,f.translation);}
fn drive(out:&mut Vec<u32>,d:RetailDriveFrames){for f in [d.body_a,d.body_b]{quat(out,f.orientation);vector(out,f.translation);}let raw=RetailDriveFramesRaw::from(d);for f in [raw.body_a,raw.body_b]{out.extend(f.quaternion_lanes);out.extend(f.translation_lanes);}}
fn main(){let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();assert_eq!(bytes.len()%4,0);let mut i=Input{words:bytes.chunks_exact(4).map(|b|u32::from_le_bytes(b.try_into().unwrap())).collect(),at:0};let mut out=Vec::new();let count=i.word();
 for _ in 0..count{match i.word(){
  0=>{let stock=i.word()!=0;let mut a=AuthoredTransformInputs{deck_mid_length:i.float(),wheel_x_distance:i.float(),truck_z_position_front:i.float(),truck_z_position_back:i.float(),truck_y_position:i.float()};let mut t=RetailTruckTransformInputs{deck_mid_length:i.float(),truck_z_position_front:i.float(),truck_z_position_back:i.float(),truck_y_position:i.float(),truck_rotation_axis_angle_degrees:i.float()};if stock{a=AuthoredTransformInputs::STOCK;t=RETAIL_DEFAULT_TRUCK_TRANSFORM_INPUTS;}
   for f in authored_body_transforms(a){frame(&mut out,f);}for words in authored_body_pose_records(a){out.extend(words);}let trucks=calculate_truck_transforms(t);for f in trucks{frame(&mut out,f);}for f in trucks{drive(&mut out,set_drive_frames_2(RetailAffineTransform::IDENTITY,f));}},
  1=>{let parent=i.frame();let child=i.frame();drive(&mut out,set_drive_frames_2(parent,child));},
  2=>{let b=i.basis();quat(&mut out,retail_quaternion_from_basis(b));},
  3=>{for f in default_live_body_transforms(){frame(&mut out,f);}for q in default_live_body_orientations(){quat(&mut out,q);}for d in default_truck_drive_frames(){drive(&mut out,d);}for d in default_wheel_drive_frames(){drive(&mut out,d);}},
  _=>panic!("operation")}}
 assert_eq!(i.at,i.words.len());let mut stdout=std::io::BufWriter::new(std::io::stdout().lock());for word in out{stdout.write_all(&word.to_le_bytes()).unwrap();}
}
