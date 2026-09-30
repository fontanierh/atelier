// Original contact preparation/publication is the independent oracle.
use skate_core::{math::Vector3,physics::solver::contact_build::*};
use std::io::{Read,Write};
struct Response{kind:u32,inverse:[f32;3],seen:[f32;3],calls:u32}
impl ContactMassResponse for Response {
 fn inverse_effective_mass(&mut self,effective_mass:[f32;3])->Result<[f32;3],ContactBuildError>{
  self.calls+=1;self.seen=effective_mass;
  if self.kind==2{Err(ContactBuildError::ReciprocalEstimateUnavailable{effective_mass})}else{Ok(self.inverse)}
 }
}
struct Input{words:Vec<u32>,at:usize}
impl Input{fn word(&mut self)->u32{let v=self.words[self.at];self.at+=1;v}fn float(&mut self)->f32{f32::from_bits(self.word())}fn words<const N:usize>(&mut self)->[u32;N]{std::array::from_fn(|_|self.word())}}
fn vector(out:&mut Vec<u32>,v:Vector3){out.extend([v.x,v.y,v.z].map(f32::to_bits));}
fn main(){
 let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();assert_eq!(bytes.len()%4,0);
 let mut input=Input{words:bytes.chunks_exact(4).map(|b|u32::from_le_bytes(b.try_into().unwrap())).collect(),at:0};let mut out=Vec::new();
 let count=input.word();for _ in 0..count{
  let kind=input.word();let mut record=input.words::<64>();let dt=input.float();let inverse=std::array::from_fn(|_|input.float());
  let p=prepare_contact(&record,dt);
  for v in p.arms{vector(&mut out,v);}for v in p.axes{vector(&mut out,v);}for v in p.active{out.push(u32::from(v));}
  out.extend(p.inverse_mass.map(f32::to_bits));for v in p.point_acceleration{vector(&mut out,v);}
  for rows in [p.angular_response_a,p.angular_response_b]{for row in rows{out.extend(row.map(f32::to_bits));}}
  for values in [p.effective_mass,p.separation_projection,p.restitution_projection,p.predicted_separation_projection]{out.extend(values.map(f32::to_bits));}
  let mut response=Response{kind,inverse,seen:[0.;3],calls:0};
  let ok=if kind==0{build_with_response(&mut record,dt,&mut NativeContactMassResponse).is_ok()}else{build_with_response(&mut record,dt,&mut response).is_ok()};
  out.push(u32::from(ok));out.push(response.calls);out.extend(response.seen.map(f32::to_bits));out.extend(record);
 }
 assert_eq!(input.at,input.words.len());let mut stdout=std::io::BufWriter::new(std::io::stdout().lock());for word in out{stdout.write_all(&word.to_le_bytes()).unwrap();}
}
