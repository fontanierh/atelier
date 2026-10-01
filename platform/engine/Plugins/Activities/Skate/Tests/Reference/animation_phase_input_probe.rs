// SPDX-License-Identifier: Apache-2.0
use std::io::{Read,Write};
use skate_core::{player::input_phase::*,animation::output::{actor_packet::{ExternalPhysicsInput,ExternalReset},attributes::AttributeName,physics_packet::PhysicsPosePacket,packet_reset},input::animation_packet::AnimationPacketFields};
mod original_host {
// ORIGINAL_HOST
pub(super) fn snapshot(out:&mut crate::Output,profile:&AnimationProfile,phase:&AnimationPhaseOutput,pose:&PhysicsPosePacket){let mut row=crate::Output(Vec::new());crate::observe_AnimationProfile(&mut row,profile);crate::observe_AnimationAdditionalResetFields(&mut row,&phase.reset);crate::observe_AnimationPacketFields(&mut row,&phase.publication);crate::observe_ExternalPhysicsInput(&mut row,&phase.external);row.word(phase.mirrored as u32);row.word(phase.weight_forwards as u32);row.word(phase.flags);crate::observe_AnimationInputPacket(&mut row,&phase.packet());crate::observe_pose(&mut row,pose);out.block(row);}
}
use original_host::AnimationProfile;
struct Input{bytes:Vec<u8>,at:usize}
impl Input{fn word(&mut self)->u32{let v=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap());self.at+=4;v}fn wide(&mut self)->u64{let lo=self.word();lo as u64|((self.word() as u64)<<32)}fn float(&mut self)->f32{f32::from_bits(self.word())}fn words<const N:usize>(&mut self)->[u32;N]{std::array::from_fn(|_|self.word())}fn floats<const N:usize>(&mut self)->[f32;N]{std::array::from_fn(|_|self.float())}fn string(&mut self)->String{let n=self.word() as usize;let s=std::str::from_utf8(&self.bytes[self.at..self.at+n]).unwrap().into();self.at+=n;s}}
struct Output(Vec<u8>);
impl Output{fn word(&mut self,w:u32){self.0.extend(w.to_le_bytes());}fn wide(&mut self,w:u64){self.word(w as u32);self.word((w>>32) as u32);}fn float(&mut self,f:f32){self.word(f.to_bits());}fn string(&mut self,s:&str){self.word(s.len() as u32);self.0.extend(s.as_bytes());}fn block(&mut self,row:Self){self.word((row.0.len()/4) as u32);self.0.extend(row.0);}}
// GENERATED_PROTOCOL
fn pose(i:&mut Input)->PhysicsPosePacket{let bone_count=i.word();let n=i.word();let hierarchy=(0..n).map(|_|std::array::from_fn(|_|i.floats())).collect();let n=i.word();let local=(0..n).map(|_|std::array::from_fn(|_|i.floats())).collect();PhysicsPosePacket{bone_count,hierarchy,local,timestep:i.float(),foot_surface_ids:i.words(),flags:i.word(),board_flipped:i.word()!=0,mirrored:i.word()!=0,riding_switch:i.word()!=0,riding_fakie:i.word()!=0,weight_forwards:i.word()!=0,regular_stance:i.word()!=0,air_dismount_revert_frames:i.word() as i32}}
fn observe_pose(o:&mut Output,p:&PhysicsPosePacket){o.word(p.bone_count);o.word(p.hierarchy.len() as u32);for m in &p.hierarchy{for c in m{for f in c{o.float(*f);}}}o.word(p.local.len() as u32);for m in &p.local{for c in m{for f in c{o.float(*f);}}}o.float(p.timestep);for v in p.foot_surface_ids{o.word(v);}o.word(p.flags);for b in [p.board_flipped,p.mirrored,p.riding_switch,p.riding_fakie,p.weight_forwards,p.regular_stance]{o.word(b as u32);}o.word(p.air_dismount_revert_frames as u32);}
fn run()->Result<(),String>{
    let args:Vec<_>=std::env::args().collect();let data=skate_data::collections::Collections::load(std::path::Path::new(&args[1]))?;let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).map_err(|e|e.to_string())?;let mut i=Input{bytes,at:0};let cases=i.word();let mut out=Output(Vec::new());
    for c in 0..cases{
        let mode=i.string();let loaded=AnimationProfile::load(&data,&mode);out.word(c);out.word(loaded.is_ok() as u32);out.string(loaded.as_ref().err().map_or("",String::as_str));let commands=i.word();let mut profile=match loaded{Ok(p)=>p,Err(_)=>{assert_eq!(commands,0);continue}};let mut phase=original_host::AnimationPhaseOutput::new();let mut p=PhysicsPosePacket{bone_count:0,hierarchy:Vec::new(),local:Vec::new(),timestep:0.,foot_surface_ids:[0;2],flags:0,board_flipped:false,mirrored:false,riding_switch:false,riding_fakie:false,weight_forwards:false,regular_stance:false,air_dismount_revert_frames:0};original_host::snapshot(&mut out,&profile,&phase,&p);
        for n in 0..commands{
            let op=i.word();let result:Result<(),String>=match op{
                0=>{phase.reset=read_AnimationAdditionalResetFields(&mut i);Ok(())},1=>{profile=read_AnimationProfile(&mut i);Ok(())},2=>{p=pose(&mut i);phase.publish(&p,&profile,i.word());Ok(())},3=>{let reply=ExternalReset{transform:std::array::from_fn(|_|i.words()),byte64:i.word() as u8};phase.publish_external_reset(reply);Ok(())},4=>packet_reset::reset(&mut p,&mut phase.reset).map_err(|e|format!("{e:?}")),5=>{let mode=i.string();match AnimationProfile::load(&data,&mode){Ok(next)=>{profile=next;Ok(())},Err(e)=>Err(e)}},_=>return Err("Invalid phase packet operation".into())};out.word(c);out.word(n);out.word(op);out.word(result.is_ok() as u32);out.string(result.as_ref().err().map_or("",String::as_str));original_host::snapshot(&mut out,&profile,&phase,&p);
        }
    }
    assert_eq!(i.at,i.bytes.len());std::io::stdout().write_all(&out.0).map_err(|e|e.to_string())?;Ok(())
}
fn main(){if let Err(error)=run(){eprintln!("{error}");std::process::exit(2);}}
