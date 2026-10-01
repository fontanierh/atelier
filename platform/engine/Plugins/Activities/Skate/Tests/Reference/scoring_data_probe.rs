// SPDX-License-Identifier: Apache-2.0
use std::io::Write;
mod collections{pub use skate_data::collections::*;}
mod attrib_hash{pub use skate_data::attrib_hash::*;}
#[path="scoring_fields.rs"]mod scoring_fields;
#[derive(Default)]struct Output(Vec<u32>);
impl Output{
 fn word(&mut self,v:u32){self.0.push(v)}
 fn float(&mut self,v:f32){self.word(v.to_bits())}
 fn string(&mut self,s:&str){self.word(s.len()as u32);for chunk in s.as_bytes().chunks(4){let mut w=[0u8;4];w[..chunk.len()].copy_from_slice(chunk);self.word(u32::from_le_bytes(w))}}
 fn status(&mut self,error:Option<String>){match error{None=>self.word(1),Some(e)=>{self.word(0);self.string(&e)}}}
 fn graph(&mut self,g:&skate_core::point_graph::PointGraph<8>){for x in g.x{self.float(x)}for y in g.y{self.float(y)}}
 fn catalog(&mut self){use skate_core::scoring::{catalog::IDENTIFIERS,conversions::LINKS};self.word(IDENTIFIERS.len()as u32);for(i,&(name,class,typ))in IDENTIFIERS.iter().enumerate(){self.string(name);self.word(class);self.word(typ as u32);self.word(LINKS[i].0 as u32);self.word(LINKS[i].1 as u32)}self.word(scoring_fields::FIELDS.len()as u32);for&(offset,name,size)in scoring_fields::FIELDS{self.word(offset as u32);self.string(name);self.word(size as u32)}}
}
mod original_data{
// ORIGINAL_SCORING_DATA
pub(super) fn observe(o:&mut super::Output,s:&ScoringData){
 let start=o.0.len();o.word(0);o.word(s.definitions.len()as u32);
 for d in&s.definitions{o.word(d.metadata.id as u32);o.word(d.metadata.class);o.word(d.metadata.score_type as u32);o.string(d.identifier);for w in d.encoded_name.0{o.word(w)}o.word(d.points as u32);o.string(&d.label);o.word(d.trick_type);o.float(d.completion_delay);o.word(d.variant as u32);o.word(d.flags)}
 o.word(s.collector.scalars.len()as u32);for(&offset,&value)in&s.collector.scalars{o.word(offset as u32);o.float(value)}
 o.word(s.collector.curves.len()as u32);for(&offset,curve)in&s.collector.curves{o.word(offset as u32);o.graph(curve)}
 o.graph(&s.repetition);o.graph(&s.announcement);for v in[s.line_drain,s.line_capacity,s.combo_drain,s.combo_capacity]{o.float(v)}for(t,m)in s.combo_levels{o.float(t);o.float(m)}for v in[s.combo_refresh_threshold,s.unannounced_factor,s.bail_factor,s.sketchy_side_speed]{o.float(v)}
 let r=s.session_rules();o.float(r.combo_capacity);for(t,m)in r.combo_levels{o.float(t);o.float(m)}for v in[r.combo_refresh_threshold,r.line_capacity,r.bail_factor]{o.float(v)}
 for(id,&(name,_,_))in IDENTIFIERS.iter().enumerate(){o.word(s.by_id(id).map_or(u32::MAX,|d|d.metadata.id as u32));o.word(s.by_name(encode(name.as_bytes())).map_or(u32::MAX,|d|d.metadata.id as u32))}
 o.word(s.by_id(332).is_some()as u32);o.word(s.by_name(encode(b"missing native scorable")).is_some()as u32);
 for w in[0,0x80000000,1,0x80000001,0x3f800000,0xbf800000,0x3eaaaaab,0x41200000,0x42c80000,0x447a0000,0xc47a0000,0x7f7fffff,0xff7fffff,0x7f800000,0xff800000,0x7fc12345,0xffc23456,0x7f812345]{let x=f32::from_bits(w);for&offset in s.collector.scalars.keys(){o.float(s.collector.scalar(offset))}for&offset in s.collector.curves.keys(){o.float(s.collector.curve(offset,x))}o.float(s.repetition.evaluate(x));o.float(s.announcement.evaluate(x))}
 o.0[start]=(o.0.len()-start-1)as u32;
}
}
fn main(){
 let args:Vec<_>=std::env::args().collect();let stock=collections::Collections::load(std::path::Path::new(&args[1])).unwrap();let variant=collections::Collections::load(std::path::Path::new(&args[2])).unwrap();
 let mut data=original_data::ScoringData::load(&stock).unwrap();let mut out=Output::default();out.catalog();original_data::observe(&mut out,&data);
 for _ in 0..2{let error=match original_data::ScoringData::load(&variant){Ok(next)=>{data=next;None},Err(e)=>Some(e)};out.status(error);original_data::observe(&mut out,&data)}
 let error=match original_data::ScoringData::load(&stock){Ok(next)=>{data=next;None},Err(e)=>Some(e)};out.status(error);original_data::observe(&mut out,&data);
 let bytes:Vec<_>=out.0.into_iter().flat_map(u32::to_le_bytes).collect();std::io::stdout().write_all(&bytes).unwrap();
}
