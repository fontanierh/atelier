// GENERATED_WORLD_HELPERS
mod climbing {
use super::*;
mod ledge;
fn ledge(o:&mut Writer,l:ledge::Ledge){
 for v in[l.anchor,l.landing,l.forward,l.palms[0],l.palms[1],l.normals[0],l.normals[1]]{for f in v.to_array(){o.scalar(f)}}
}
fn read_ledge(i:&mut Reader)->ledge::Ledge{let cv=|v:Vector3|bevy::prelude::Vec3::new(v.x,v.y,v.z);ledge::Ledge{anchor:cv(i.vector()),landing:cv(i.vector()),forward:cv(i.vector()),palms:std::array::from_fn(|_|cv(i.vector())),normals:std::array::from_fn(|_|cv(i.vector()))}}
pub(super)fn run(){let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut i=Reader{bytes,at:0};let count=i.word();let mut output=vec![count];
 for c in 0..count{let n=i.word();let triangles=(0..n).map(|_|cached(triangle(&mut i))).collect();let with_metadata=i.word()!=0;let metadata=metadata(&mut i);let world=if with_metadata{BoardWorld::with_query_metadata(triangles,metadata)}else{Ok(BoardWorld::new(triangles))};let mut o=Writer{words:Vec::new()};o.error(world.as_ref().err().copied());let n=i.word();o.word(n);
  for _ in 0..n{let op=i.word();o.word(op);match op{
   0|1=>{let feet=i.vector();let facing=i.vector();let cv=|v:Vector3|bevy::prelude::Vec3::new(v.x,v.y,v.z);let found=world.as_ref().ok().and_then(|w|if op==0{ledge::find(w,cv(feet),cv(facing))}else{ledge::find_air(w,cv(feet),cv(facing))});o.word(found.is_some()as u32);if let Some(l)=found{ledge(&mut o,l);o.word(ledge::clear(world.as_ref().unwrap(),l)as u32);}},
   2=>{let l=read_ledge(&mut i);o.word(world.as_ref().is_ok_and(|w|ledge::clear(w,l))as u32);},
   3=>{let a=i.vector();let b=i.vector();let radius=i.scalar();o.hit(world.as_ref().map_err(|_|"World construction failed").and_then(|w|w.query_swept_line(a,b,radius)));},
   _=>panic!("Climbing world opcode {op}"),
  }}
  output.extend([c,o.words.len()as u32]);output.extend(o.words);
 }
 assert_eq!(i.at,i.bytes.len());std::io::stdout().write_all(&output.into_iter().flat_map(u32::to_le_bytes).collect::<Vec<_>>()).unwrap();
}
}
fn main(){climbing::run()}
