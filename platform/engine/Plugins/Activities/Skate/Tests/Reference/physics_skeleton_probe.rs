use skate_data::physics_skeleton::PhysicsSkeleton;
use std::{io::{self,Write},path::Path};
fn word(out:&mut impl Write,w:u32){out.write_all(&w.to_le_bytes()).unwrap();}
fn wide(out:&mut impl Write,w:u64){out.write_all(&w.to_le_bytes()).unwrap();}
fn string(out:&mut impl Write,v:&str){word(out,v.len() as u32);out.write_all(v.as_bytes()).unwrap();}
fn main(){
 let args:Vec<_>=std::env::args().collect();
 let value=match PhysicsSkeleton::load(Path::new(&args[1]),&args[2],&args[3]){Ok(v)=>v,Err(e)=>{eprintln!("{e}");std::process::exit(2);}};
 let mut out=io::BufWriter::new(io::stdout().lock());string(&mut out,&value.name);wide(&mut out,value.source_offset);word(&mut out,value.bones.len() as u32);
 for bone in &value.bones{string(&mut out,&bone.name);wide(&mut out,bone.source_offset);for v in bone.words{word(&mut out,v);}for v in bone.size().into_iter().chain(bone.rotation()).chain(bone.translation()){word(&mut out,v.to_bits());}}
}
