//! Temporary migration oracle: compile the unmodified reference recognizer and PAT reader directly.
//! No C++ code, converted input tables, or expected-output implementation is shared with this oracle.
extern crate self as skate_core;
#[path = "../../ThirdParty/skate-runtime/crates/skate-core/src/input/gesture.rs"]
pub mod reference_gesture;
pub mod input { pub use crate::reference_gesture as gesture; }
#[path = "../../ThirdParty/skate-runtime/crates/skate-data/src/gesture_patterns.rs"]
mod reference_patterns;
use reference_gesture::{Pattern, Recognizer, Settings};
use std::{io::{Read, Write}, path::Path};

const SETS: [(&str, u32, &str); 7] = [
    ("main",1,"skater.pat"), ("rotated90",1,"skater90.pat"),
    ("rotated_minus90",1,"skaterN90.pat"), ("air",1,"skater_air.pat"),
    ("fingerflip",1,"skater_fingerflip.pat"), ("left",0,"skaterls.pat"), ("step",0,"skaterstep.pat"),
];
fn word(out: &mut Vec<u8>, value: u32) { out.extend(value.to_le_bytes()); }
fn string(out: &mut Vec<u8>, value: &str) {
    word(out,value.len() as u32); out.extend(value.as_bytes());
}
fn run() -> Result<(), String> {
    let args: Vec<_> = std::env::args().collect();
    if args.len()!=3 { return Err("usage: reference-gesture-probe ORIGINAL_PAT_FOLDER dump|replay".into()); }
    let patterns: Vec<Vec<Pattern>> = SETS.iter().map(|(_,_,file)|
        reference_patterns::load(&Path::new(&args[1]).join(file))).collect::<Result<_,_>>()?;
    let mut out = Vec::new();
    if args[2]=="dump" {
        out.extend(b"ATGEST01"); word(&mut out,SETS.len() as u32);
        for ((name,stick,_),patterns) in SETS.iter().zip(&patterns) {
            string(&mut out,name);word(&mut out,*stick);word(&mut out,patterns.len() as u32);
            for pattern in patterns {
                string(&mut out,&pattern.name);word(&mut out,pattern.tolerance_squared.to_bits());
                word(&mut out,pattern.points.len() as u32);
                for point in &pattern.points { for value in point {word(&mut out,value.to_bits());} }
            }
        }
    } else if args[2]=="replay" {
        let mut recognizers: Vec<_> = patterns.iter().map(|p|Recognizer::new(p.clone())).collect::<Result<_,_>>()?;
        let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).map_err(|e|e.to_string())?;
        if bytes.len()%24!=0 { return Err("partial input record".into()); }
        for record in bytes.chunks_exact(24) {
            let u=|offset|u32::from_le_bytes(record[offset..offset+4].try_into().unwrap());
            let (set,op,difficulty,misses)=(u(0) as usize,u(4),u(8),u(12));
            let sample=[f32::from_bits(u(16)),f32::from_bits(u(20))];
            if set>=SETS.len() || op>1 || misses>255 { return Err("invalid input record".into()); }
            if op==0 {
                recognizers[set]=Recognizer::new(patterns[set].clone())?;
                for value in [u32::MAX,u32::MAX,0,0,0] {word(&mut out,value);}
                continue;
            }
            let held=recognizers[set].held(sample);
            let matched=recognizers[set].sample(sample,Settings{maximum_misses:misses as u8,difficulty});
            word(&mut out,held.map_or(u32::MAX,|i|i as u32));
            if let Some(value)=matched {
                for field in [value.pattern as u32,value.strength.to_bits(),value.distance.to_bits(),value.elapsed.to_bits()] {
                    word(&mut out,field);
                }
            } else { for field in [u32::MAX,0,0,0] {word(&mut out,field);} }
        }
    } else { return Err("unknown command".into()); }
    std::io::stdout().write_all(&out).map_err(|e|e.to_string())
}
fn main() {
    if let Err(error)=run() { eprintln!("{error}");std::process::exit(2); }
}
