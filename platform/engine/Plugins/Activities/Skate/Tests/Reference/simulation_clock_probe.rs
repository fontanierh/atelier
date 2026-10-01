// SPDX-License-Identifier: Apache-2.0
use std::io::{Read,Write};
use skate_core::camera::SimulationRateRequest;
mod clock;
fn word(i:&mut &[u8])->u32{let(a,b)=i.split_at(4);*i=b;u32::from_le_bytes(a.try_into().unwrap())}
fn out(o:&mut Vec<u8>,v:u32){o.extend(v.to_le_bytes());}
fn status(o:&mut Vec<u8>,r:Result<(),String>){match r{Ok(())=>{out(o,1);out(o,0)},Err(e)=>{out(o,0);out(o,e.len()as u32);o.extend(e.as_bytes())}}}
fn owner(o:&mut Vec<u8>,c:&clock::SimulationClock){let ticks=c.migration_ticks();out(o,ticks);let ns=c.period().as_nanos()as u64;out(o,ns as u32);out(o,(ns>>32)as u32)}
fn main(){let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut i=bytes.as_slice();let mut o=Vec::new();let cases=word(&mut i);out(&mut o,cases);for _ in 0..cases{let mut clock=clock::SimulationClock::default();owner(&mut o,&clock);let n=word(&mut i);out(&mut o,n);for _ in 0..n{let op=word(&mut i);out(&mut o,op);let r=match op{0=>{clock=clock::SimulationClock::default();Ok(())},1=>{let timestep=f32::from_bits(word(&mut i));let ticks=word(&mut i);clock.apply(SimulationRateRequest{timestep,ticks})},2=>{clock.finish_tick();Ok(())},3=>{let count=word(&mut i);let requests=(0..count).map(|_|SimulationRateRequest{timestep:f32::from_bits(word(&mut i)),ticks:word(&mut i)}).collect::<Vec<_>>();requests.into_iter().try_for_each(|request|clock.apply(request))},4=>{let count=word(&mut i);for _ in 0..count{clock.finish_tick()}Ok(())},_=>panic!("Clock opcode {op}")};status(&mut o,r);owner(&mut o,&clock);}}assert!(i.is_empty());std::io::stdout().write_all(&o).unwrap();}
